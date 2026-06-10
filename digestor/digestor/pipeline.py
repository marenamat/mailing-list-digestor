import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from digestor.config import Config
from digestor.email_parser import parse_eml
from digestor.rules import check_rules
from digestor.triage import classify_urgency
from digestor.classifier import classify_urgent
from digestor.archive import fetch_from_archive

log = logging.getLogger(__name__)


def _lookup_wg(list_addr: str, lists: dict[str, list[str]]) -> str:
    for wg, addrs in lists.items():
        if list_addr in addrs:
            return wg
    return "General"


def process_eml(path: Path, cfg: Config, db: sqlite3.Connection) -> None:
    parsed = parse_eml(path)

    # Skip duplicates
    existing = db.execute(
        "SELECT id FROM emails WHERE message_id=?", (parsed.message_id,)
    ).fetchone()
    if existing:
        log.debug("Skipping duplicate %s", parsed.message_id)
        return

    # Fetch missing referenced emails
    for ref_id in parsed.references:
        if not db.execute("SELECT id FROM emails WHERE message_id=?", (ref_id,)).fetchone():
            archived = fetch_from_archive(ref_id)
            if archived:
                _store_email(archived, "archive", {}, db)

    lists = cfg.load_lists()
    wg = _lookup_wg(parsed.list_addr, lists)

    # Rules check
    urgency_override, notif_type = check_rules(parsed)

    if urgency_override == "urgent":
        urgency_local = "urgent"
        urgency_claude, rationale, in_tok, out_tok = "urgent", "rule match", 0, 0
    else:
        urgency_local = classify_urgency(
            parsed.subject, parsed.body_text, cfg.ollama_model, cfg.ollama_base_url
        )
        if urgency_local == "urgent":
            context = cfg.load_context()
            urgency_claude, rationale, in_tok, out_tok = classify_urgent(
                parsed.subject, parsed.body_text, context, cfg.anthropic_api_key
            )
            if in_tok:
                db.execute(
                    "INSERT INTO token_usage(model, input_tokens, output_tokens, purpose) VALUES(?,?,?,?)",
                    ("claude-sonnet-4-6", in_tok, out_tok, "classification"),
                )
        else:
            urgency_claude, rationale = "not_urgent", ""

    db.execute("""
        INSERT INTO emails
            (message_id, date, from_addr, subject, list_addr, working_group,
             body_text, urgency_local, urgency_claude, rationale, processed_at, source)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        parsed.message_id, parsed.date, parsed.from_addr, parsed.subject,
        parsed.list_addr, wg, parsed.body_text,
        urgency_local, urgency_claude, rationale,
        datetime.now(timezone.utc).isoformat(), "smtp",
    ))

    if urgency_claude == "urgent":
        content = f"**{parsed.subject}**\nFrom: {parsed.from_addr}\n\n{rationale}"
        db.execute(
            "INSERT INTO notifications(type, content, status, next_fire_at) VALUES(?,?,?,?)",
            ("urgent", content, "pending", datetime.now(timezone.utc).isoformat()),
        )

    db.commit()
    log.info("Processed %s → %s/%s", parsed.message_id, urgency_local, urgency_claude)


def _store_email(parsed, source, lists, db):
    wg = _lookup_wg(parsed.list_addr, lists)
    try:
        db.execute("""
            INSERT OR IGNORE INTO emails
                (message_id, date, from_addr, subject, list_addr, working_group, body_text, source)
            VALUES (?,?,?,?,?,?,?,?)
        """, (parsed.message_id, parsed.date, parsed.from_addr, parsed.subject,
              parsed.list_addr, wg, parsed.body_text, source))
        db.commit()
    except Exception:
        log.exception("Failed to store archived email %s", parsed.message_id)
