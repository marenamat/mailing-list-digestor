import logging
import anthropic

log = logging.getLogger(__name__)

_SYSTEM = """You are generating a daily digest for the {wg_name} working group of an IETF mailing list.

User context:
{context}

Summarize email threads from the past day. Group by topic. Note action items, decisions, and deadlines.
If nothing important happened, say "Nothing to report."
If you notice another mailing list that seems highly relevant based on the discussion, recommend subscribing.
"""


def _format_emails(emails: list[dict]) -> str:
    if not emails:
        return "(no emails)"
    parts = []
    for e in emails:
        parts.append(
            f"From: {e.get('from_addr','?')}\n"
            f"Date: {e.get('date','?')}\n"
            f"Subject: {e.get('subject','?')}\n\n"
            f"{e.get('body_text','')[:1500]}\n"
            f"{'─'*40}"
        )
    return "\n".join(parts)


def generate_digest(
    emails: list[dict], wg_name: str, context: str, api_key: str
) -> tuple[str, int, int]:
    """Returns (content, input_tokens, output_tokens)."""
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_SYSTEM.format(wg_name=wg_name, context=context),
        messages=[{"role": "user", "content": _format_emails(emails)}],
    )
    return msg.content[0].text, msg.usage.input_tokens, msg.usage.output_tokens
