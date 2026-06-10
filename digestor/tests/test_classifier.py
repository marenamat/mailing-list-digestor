import json
from unittest.mock import MagicMock, patch
import pytest
from digestor.classifier import classify_urgent

def _mock_anthropic(json_body: dict):
    mock_content = MagicMock()
    mock_content.text = json.dumps(json_body)
    mock_msg = MagicMock()
    mock_msg.content = [mock_content]
    mock_msg.usage.input_tokens = 100
    mock_msg.usage.output_tokens = 50
    return mock_msg

def test_returns_urgent_verdict():
    with patch("digestor.classifier.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_anthropic(
            {"verdict": "urgent", "rationale": "CFP deadline in 3 days"}
        )
        verdict, rationale, in_tok, out_tok = classify_urgent(
            "CFP", "Submit by Friday", "I care about QUIC", "sk-test"
        )
    assert verdict == "urgent"
    assert "CFP" in rationale or "deadline" in rationale.lower()
    assert in_tok == 100
    assert out_tok == 50

def test_returns_not_urgent_verdict():
    with patch("digestor.classifier.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_anthropic(
            {"verdict": "not_urgent", "rationale": "Routine discussion thread"}
        )
        verdict, rationale, _, _ = classify_urgent("Re: draft", "comments", "context", "key")
    assert verdict == "not_urgent"

def test_defaults_to_urgent_on_bad_json():
    with patch("digestor.classifier.anthropic.Anthropic") as MockA:
        mock_content = MagicMock()
        mock_content.text = "not json"
        mock_msg = MagicMock()
        mock_msg.content = [mock_content]
        mock_msg.usage.input_tokens = 10
        mock_msg.usage.output_tokens = 5
        MockA.return_value.messages.create.return_value = mock_msg
        verdict, _, _, _ = classify_urgent("subject", "body", "ctx", "key")
    assert verdict == "urgent"
