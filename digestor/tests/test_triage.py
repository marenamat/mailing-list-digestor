from unittest.mock import MagicMock, patch
import pytest
from digestor.triage import classify_urgency

def _mock_ollama(response_text: str):
    mock_msg = MagicMock()
    mock_msg.content = response_text
    mock_resp = MagicMock()
    mock_resp.message = mock_msg
    return mock_resp

def test_returns_urgent_on_urgent_response():
    with patch("digestor.triage.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = _mock_ollama("URGENT")
        result = classify_urgency("CFP deadline", "Submit by Friday", "m", "http://x")
    assert result == "urgent"

def test_returns_not_urgent_on_not_urgent_response():
    with patch("digestor.triage.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = _mock_ollama("NOT_URGENT")
        result = classify_urgency("Re: draft", "Some discussion", "m", "http://x")
    assert result == "not_urgent"

def test_defaults_to_urgent_on_unexpected_response():
    with patch("digestor.triage.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = _mock_ollama("I'm not sure")
        result = classify_urgency("subject", "body", "m", "http://x")
    assert result == "urgent"

def test_prompt_includes_subject_and_body():
    with patch("digestor.triage.ollama.Client") as MockClient:
        MockClient.return_value.chat.return_value = _mock_ollama("NOT_URGENT")
        classify_urgency("my subject", "my body text", "model", "http://base")
        call_args = MockClient.return_value.chat.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "my subject" in user_msg
        assert "my body text" in user_msg
