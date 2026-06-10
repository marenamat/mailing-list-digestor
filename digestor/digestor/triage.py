import logging
import ollama

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an email urgency classifier for IETF mailing lists.
Classify each email as URGENT or NOT_URGENT.
When uncertain, classify as URGENT — missing something important is worse than a false positive.
Respond with exactly one token: URGENT or NOT_URGENT."""


def classify_urgency(subject: str, body: str, model: str, base_url: str) -> str:
    """Returns 'urgent' or 'not_urgent'. Defaults to 'urgent' on any error."""
    try:
        client = ollama.Client(host=base_url)
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Subject: {subject}\n\n{body[:2000]}"},
            ],
        )
        text = response.message.content.strip().upper()
        if "NOT_URGENT" in text:
            return "not_urgent"
        return "urgent"
    except Exception:
        log.exception("Ollama triage failed; defaulting to urgent")
        return "urgent"
