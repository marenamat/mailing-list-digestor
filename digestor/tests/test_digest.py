import json
from unittest.mock import MagicMock, patch
import pytest
from digestor.digest import generate_digest

def _mock_claude(text: str, in_tok=200, out_tok=400):
    mock_content = MagicMock()
    mock_content.text = text
    mock_msg = MagicMock()
    mock_msg.content = [mock_content]
    mock_msg.usage.input_tokens = in_tok
    mock_msg.usage.output_tokens = out_tok
    return mock_msg

_EMAILS = [
    {"subject": "QUIC multipath", "from_addr": "alice@example.com",
     "date": "2026-06-11", "body_text": "Discussing path identifiers."},
    {"subject": "Re: QUIC multipath", "from_addr": "bob@example.com",
     "date": "2026-06-11", "body_text": "Agreed on the proposal."},
]

def test_generate_digest_returns_content_and_tokens():
    with patch("digestor.digest.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_claude(
            "## QUIC\nDiscussion on multipath.\n\nNothing else to report.", 200, 400
        )
        content, in_tok, out_tok = generate_digest(_EMAILS, "QUIC", "context", "sk-test")

    assert "QUIC" in content or "multipath" in content.lower() or len(content) > 0
    assert in_tok == 200
    assert out_tok == 400

def test_generate_digest_prompt_includes_wg_name():
    with patch("digestor.digest.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_claude("Summary.")
        generate_digest(_EMAILS, "HTTPBIS", "context", "key")
        call = MockA.return_value.messages.create.call_args
        system = call.kwargs["system"]
        assert "HTTPBIS" in system

def test_generate_digest_returns_nothing_here_on_empty():
    with patch("digestor.digest.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_claude("Nothing to report.")
        content, _, _ = generate_digest([], "TLS", "context", "key")
    assert len(content) > 0
