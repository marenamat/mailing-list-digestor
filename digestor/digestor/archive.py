import email, io, logging, mailbox
import httpx
from digestor.email_parser import ParsedEmail, parse_eml

log = logging.getLogger(__name__)

_ARCHIVE_URL = "https://mailarchive.ietf.org/arch/search/?qdr=a&q=msgid:{msgid}&format=mbox"


def fetch_from_archive(message_id: str) -> ParsedEmail | None:
    """Fetch an email by Message-ID from IETF mailarchive. Returns None on failure."""
    clean_id = message_id.strip("<>")
    url = _ARCHIVE_URL.format(msgid=clean_id)
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            log.warning("Archive returned %d for %s", resp.status_code, message_id)
            return None
        return _parse_mbox(resp.content, message_id)
    except Exception:
        log.exception("Failed to fetch %s from archive", message_id)
        return None


def _parse_mbox(data: bytes, original_id: str) -> ParsedEmail | None:
    try:
        lines = data.decode("utf-8", errors="replace")
        messages = []
        current: list[str] = []
        for line in lines.splitlines(keepends=True):
            if line.startswith("From ") and current:
                messages.append("".join(current))
                current = []
            current.append(line)
        if current:
            messages.append("".join(current))

        for raw in messages:
            msg = email.message_from_string(raw, policy=email.policy.compat32)
            if not msg.get("Message-ID"):
                continue
            import tempfile, pathlib
            with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as f:
                f.write(raw.encode())
                tmp = pathlib.Path(f.name)
            try:
                parsed = parse_eml(tmp)
                return parsed
            finally:
                tmp.unlink(missing_ok=True)
        return None
    except Exception:
        log.exception("Failed to parse mbox data")
        return None
