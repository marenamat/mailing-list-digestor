import json, logging
import anthropic

log = logging.getLogger(__name__)

_SYSTEM = """You are evaluating whether an IETF mailing list email requires immediate attention.

User context:
{context}

Respond with JSON only:
{{"verdict": "urgent" | "not_urgent", "rationale": "<one sentence>"}}"""


def classify_urgent(
    subject: str, body: str, context: str, api_key: str
) -> tuple[str, str, int, int]:
    """Returns (verdict, rationale, input_tokens, output_tokens).
    verdict is 'urgent' or 'not_urgent'. Defaults to 'urgent' on failure."""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=_SYSTEM.format(context=context),
            messages=[{"role": "user", "content": f"Subject: {subject}\n\n{body[:4000]}"}],
        )
        data = json.loads(msg.content[0].text)
        verdict = data.get("verdict", "urgent")
        if verdict not in ("urgent", "not_urgent"):
            verdict = "urgent"
        return verdict, data.get("rationale", ""), msg.usage.input_tokens, msg.usage.output_tokens
    except Exception:
        log.exception("Claude classifier failed; defaulting to urgent")
        return "urgent", "classifier error", 0, 0
