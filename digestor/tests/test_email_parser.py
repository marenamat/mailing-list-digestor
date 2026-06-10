from pathlib import Path
import pytest
from digestor.email_parser import parse_eml, ParsedEmail

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_basic_fields():
    result = parse_eml(FIXTURES / "sample.eml")
    assert result.message_id == "<sample-001@example.com>"
    assert result.from_addr == "alice@example.com"
    assert result.subject == "Re: QUIC multipath latest revision"
    assert "quic.ietf.org" in result.list_addr

def test_parse_reply_headers():
    result = parse_eml(FIXTURES / "sample.eml")
    assert result.in_reply_to == "<original-001@example.com>"
    assert "<original-001@example.com>" in result.references

def test_parse_body_text():
    result = parse_eml(FIXTURES / "sample.eml")
    assert "multipath" in result.body_text

def test_parse_date_is_iso():
    result = parse_eml(FIXTURES / "sample.eml")
    assert "2026" in result.date

def test_parse_cfp():
    result = parse_eml(FIXTURES / "cfp.eml")
    assert "Call for Presentations" in result.subject
    assert result.in_reply_to is None
    assert result.references == []
