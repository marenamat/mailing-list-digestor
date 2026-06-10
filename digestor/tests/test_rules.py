from pathlib import Path
import pytest
from digestor.email_parser import parse_eml
from digestor.rules import check_rules

FIXTURES = Path(__file__).parent / "fixtures"

def test_cfp_is_urgent():
    parsed = parse_eml(FIXTURES / "cfp.eml")
    urgency, notif_type = check_rules(parsed)
    assert urgency == "urgent"
    assert notif_type == "cfp"

def test_interim_is_regular():
    parsed = parse_eml(FIXTURES / "interim.eml")
    urgency, notif_type = check_rules(parsed)
    assert urgency == "not_urgent"
    assert notif_type == "interim"

def test_subscription_confirm_is_urgent():
    from digestor.email_parser import ParsedEmail
    parsed = ParsedEmail(
        message_id="<sub@1>", date="2026-06-11", from_addr="list@ietf.org",
        subject="You have been subscribed to quic@ietf.org",
        list_addr="quic@ietf.org", body_text="Welcome.", in_reply_to=None, references=[],
    )
    urgency, notif_type = check_rules(parsed)
    assert urgency == "urgent"
    assert notif_type == "subscription_confirm"

def test_last_call_not_irrelevant():
    from digestor.email_parser import ParsedEmail
    parsed = ParsedEmail(
        message_id="<lc@1>", date="2026-06-11", from_addr="rfc-editor@ietf.org",
        subject="Last Call: draft-ietf-quic-multipath",
        list_addr="ietf-announce@ietf.org", body_text="Last call for comments.",
        in_reply_to=None, references=[],
    )
    urgency, notif_type = check_rules(parsed)
    assert urgency is not None  # must not be skipped
    assert notif_type == "last_call"

def test_normal_email_returns_none():
    from digestor.email_parser import ParsedEmail
    parsed = ParsedEmail(
        message_id="<n@1>", date="2026-06-11", from_addr="dev@example.com",
        subject="Re: implementation question",
        list_addr="quic@ietf.org", body_text="Good point.", in_reply_to="<x@1>", references=[],
    )
    urgency, notif_type = check_rules(parsed)
    assert urgency is None
    assert notif_type is None
