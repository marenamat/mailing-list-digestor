from unittest.mock import patch, MagicMock
import pytest
from digestor.archive import fetch_from_archive

_SAMPLE_MBOX = b"""From MAILER-DAEMON Wed Jun 11 08:00:00 2026
From: alice@example.com
To: quic@ietf.org
Subject: QUIC multipath original
Message-ID: <original-001@example.com>
Date: Wed, 11 Jun 2026 08:00:00 +0200
List-Id: QUIC Working Group <quic.ietf.org>

Original message body here.
"""

def test_fetch_returns_parsed_email():
    with patch("digestor.archive.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _SAMPLE_MBOX
        mock_get.return_value = mock_resp

        result = fetch_from_archive("<original-001@example.com>")

    assert result is not None
    assert result.message_id == "<original-001@example.com>"
    assert result.subject == "QUIC multipath original"
    assert "Original message" in result.body_text

def test_fetch_returns_none_on_404():
    with patch("digestor.archive.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = fetch_from_archive("<nonexistent@example.com>")

    assert result is None

def test_fetch_returns_none_on_network_error():
    with patch("digestor.archive.httpx.get", side_effect=Exception("network error")):
        result = fetch_from_archive("<any@example.com>")
    assert result is None
