import email
import email.policy
import email.utils
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path


@dataclass
class ParsedEmail:
    message_id: str
    date: str
    from_addr: str
    subject: str
    list_addr: str
    body_text: str
    in_reply_to: str | None
    references: list[str]


def _extract_list_addr(msg: email.message.Message) -> str:
    list_id = msg.get("List-Id", "")
    if "<" in list_id:
        return list_id.split("<")[1].rstrip(">").strip()
    to = msg.get("To", "")
    return to.split(",")[0].strip()


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def _parse_refs(header: str) -> list[str]:
    if not header:
        return []
    return [r.strip() for r in header.split() if r.strip()]


def parse_eml(path: Path) -> ParsedEmail:
    with open(path, "rb") as f:
        msg = email.message_from_bytes(f.read(), policy=email.policy.compat32)

    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
        date_str = dt.isoformat()
    except Exception:
        date_str = msg.get("Date", "")

    from_addr = email.utils.parseaddr(msg.get("From", ""))[1]

    return ParsedEmail(
        message_id=msg.get("Message-ID", "").strip(),
        date=date_str,
        from_addr=from_addr,
        subject=msg.get("Subject", ""),
        list_addr=_extract_list_addr(msg),
        body_text=_extract_body(msg),
        in_reply_to=msg.get("In-Reply-To", None),
        references=_parse_refs(msg.get("References", "")),
    )
