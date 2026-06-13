import hashlib
import logging
import sqlite3
from datetime import datetime, timezone

import anthropic

from digestor.config import Config
from digestor.crawler import fetch_rendered_text

log = logging.getLogger(__name__)

_MAX_CONTENT_LEN = 100_000
_LLM_SNIPPET_LEN = 4_000

_PROMPT = """You are monitoring a webpage for changes.
Tracking goal: {label}
URL: {url}

PREVIOUS CONTENT (truncated):
{prev_text}

CURRENT CONTENT (truncated):
{new_text}

Summarise what changed in 2-3 sentences, focusing on what is relevant to the tracking goal."""


def check_tracking(row: sqlite3.Row, cfg: Config, db: sqlite3.Connection) -> None:
    url = row["url"]
    label = row["label"] or url
    now = datetime.now(timezone.utc).isoformat()

    try:
        text = fetch_rendered_text(url)
    except Exception:
        log.exception("Failed to fetch %s", url)
        return

    new_hash = hashlib.sha256(text.encode()).hexdigest()

    if new_hash == row["last_content_hash"]:
        db.execute("UPDATE trackings SET last_checked_at=? WHERE id=?", (now, row["id"]))
        db.commit()
        return

    if row["last_content_text"] is None:
        db.execute(
            "UPDATE trackings SET last_content_hash=?, last_content_text=?, last_checked_at=? WHERE id=?",
            (new_hash, text[:_MAX_CONTENT_LEN], now, row["id"]),
        )
        db.execute(
            "INSERT INTO notifications(type, content, status) VALUES(?,?,?)",
            ("tracking", f"Now tracking: {label}\n{url}", "pending"),
        )
        db.commit()
        return

    summary, in_tok, out_tok = _summarise_change(
        label, url, row["last_content_text"], text, cfg.anthropic_api_key
    )

    db.execute(
        "UPDATE trackings SET last_content_hash=?, last_content_text=?, last_checked_at=?, last_changed_at=? WHERE id=?",
        (new_hash, text[:_MAX_CONTENT_LEN], now, now, row["id"]),
    )
    db.execute(
        "INSERT INTO notifications(type, content, status) VALUES(?,?,?)",
        ("tracking", f"**Change detected: {label}**\n{url}\n\n{summary}", "pending"),
    )
    db.execute(
        "INSERT INTO token_usage(model, input_tokens, output_tokens, purpose) VALUES(?,?,?,?)",
        ("claude-sonnet-4-6", in_tok, out_tok, f"tracking:{url}"),
    )
    db.commit()


def _summarise_change(
    label: str, url: str, prev_text: str, new_text: str, api_key: str
) -> tuple[str, int, int]:
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": _PROMPT.format(
                    label=label,
                    url=url,
                    prev_text=prev_text[:_LLM_SNIPPET_LEN],
                    new_text=new_text[:_LLM_SNIPPET_LEN],
                ),
            }],
        )
        return msg.content[0].text, msg.usage.input_tokens, msg.usage.output_tokens
    except Exception:
        log.exception("Claude summarise failed for %s", url)
        return "(summary unavailable)", 0, 0
