import re
from digestor.email_parser import ParsedEmail

_CFP_RE = re.compile(r"call for (presentations?|papers?|participation)", re.I)
_INTERIM_RE = re.compile(r"interim (meeting|session)", re.I)
_LAST_CALL_RE = re.compile(r"\blast call\b", re.I)
_WG_ADOPTION_RE = re.compile(r"(working group|wg) adoption call", re.I)
_SUBSCRIPTION_RE = re.compile(r"(you have been subscribed|subscription confirm)", re.I)


def check_rules(parsed: ParsedEmail) -> tuple[str | None, str | None]:
    """Returns (urgency_override, notification_type).
    urgency_override: 'urgent' | 'not_urgent' | None
    notification_type: str | None
    """
    subj = parsed.subject or ""

    if _CFP_RE.search(subj):
        return "urgent", "cfp"

    if _INTERIM_RE.search(subj):
        return "not_urgent", "interim"

    if _LAST_CALL_RE.search(subj):
        return "not_urgent", "last_call"

    if _WG_ADOPTION_RE.search(subj):
        return "not_urgent", "wg_adoption"

    if _SUBSCRIPTION_RE.search(subj):
        return "urgent", "subscription_confirm"

    return None, None
