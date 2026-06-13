import hashlib
from unittest.mock import MagicMock, patch

import pytest

from digestor.config import Config
from digestor.db import init_db
from digestor.tracker import check_tracking


@pytest.fixture
def db(tmp_path):
    return init_db(str(tmp_path / "test.db"))


@pytest.fixture
def cfg():
    c = Config()
    c.anthropic_api_key = "sk-test"
    return c


def _insert_tracking(db, url="https://example.com", label="test label",
                     interval_h=24.0, last_hash=None, last_text=None):
    db.execute(
        "INSERT INTO trackings(url, label, interval_h, last_content_hash, last_content_text)"
        " VALUES(?,?,?,?,?)",
        (url, label, interval_h, last_hash, last_text),
    )
    db.commit()
    return db.execute("SELECT * FROM trackings WHERE url=?", (url,)).fetchone()


def _mock_claude(summary_text: str):
    mock_content = MagicMock()
    mock_content.text = summary_text
    mock_msg = MagicMock()
    mock_msg.content = [mock_content]
    mock_msg.usage.input_tokens = 100
    mock_msg.usage.output_tokens = 50
    return mock_msg


def test_first_fetch_stores_baseline_and_notifies(db, cfg):
    row = _insert_tracking(db)

    with patch("digestor.tracker.fetch_rendered_text", return_value="Hello page"):
        check_tracking(row, cfg, db)

    updated = db.execute("SELECT * FROM trackings WHERE id=?", (row["id"],)).fetchone()
    assert updated["last_content_text"] == "Hello page"
    assert updated["last_content_hash"] == hashlib.sha256(b"Hello page").hexdigest()
    assert updated["last_checked_at"] is not None
    assert updated["last_changed_at"] is None

    notif = db.execute("SELECT content FROM notifications").fetchone()
    assert notif is not None
    assert "Now tracking" in notif["content"]


def test_first_fetch_does_not_call_claude(db, cfg):
    row = _insert_tracking(db)

    with patch("digestor.tracker.fetch_rendered_text", return_value="content"), \
         patch("digestor.tracker.anthropic.Anthropic") as MockA:
        check_tracking(row, cfg, db)

    MockA.assert_not_called()


def test_no_change_updates_last_checked_only(db, cfg):
    text = "stable content"
    h = hashlib.sha256(text.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=text)

    with patch("digestor.tracker.fetch_rendered_text", return_value=text):
        check_tracking(row, cfg, db)

    updated = db.execute("SELECT * FROM trackings WHERE id=?", (row["id"],)).fetchone()
    assert updated["last_checked_at"] is not None
    assert updated["last_changed_at"] is None
    assert db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0


def test_change_calls_claude_and_queues_notification(db, cfg):
    old = "old content"
    h = hashlib.sha256(old.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=old)

    with patch("digestor.tracker.fetch_rendered_text", return_value="new content"), \
         patch("digestor.tracker.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_claude("The venue moved to Room B.")
        check_tracking(row, cfg, db)

    notif = db.execute("SELECT content FROM notifications").fetchone()
    assert "Change detected" in notif["content"]
    assert "Room B" in notif["content"]


def test_change_logs_token_usage(db, cfg):
    old = "old"
    h = hashlib.sha256(old.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=old)

    with patch("digestor.tracker.fetch_rendered_text", return_value="new"), \
         patch("digestor.tracker.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_claude("Changed.")
        check_tracking(row, cfg, db)

    usage = db.execute("SELECT * FROM token_usage WHERE purpose LIKE 'tracking:%'").fetchone()
    assert usage is not None
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50


def test_change_updates_hash_and_text(db, cfg):
    old = "old content"
    h = hashlib.sha256(old.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=old)
    new = "new content"

    with patch("digestor.tracker.fetch_rendered_text", return_value=new), \
         patch("digestor.tracker.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_claude("Changed.")
        check_tracking(row, cfg, db)

    updated = db.execute("SELECT * FROM trackings WHERE id=?", (row["id"],)).fetchone()
    assert updated["last_content_hash"] == hashlib.sha256(new.encode()).hexdigest()
    assert updated["last_content_text"] == new
    assert updated["last_changed_at"] is not None


def test_content_truncated_to_100k(db, cfg):
    old = "x" * 200_000
    h = hashlib.sha256(old.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=old[:100_000])
    new = "y" * 200_000

    with patch("digestor.tracker.fetch_rendered_text", return_value=new), \
         patch("digestor.tracker.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.return_value = _mock_claude("Changed.")
        check_tracking(row, cfg, db)

    updated = db.execute("SELECT last_content_text FROM trackings WHERE id=?", (row["id"],)).fetchone()
    assert len(updated[0]) == 100_000


def test_fetch_error_is_logged_not_raised(db, cfg):
    row = _insert_tracking(db)

    with patch("digestor.tracker.fetch_rendered_text", side_effect=Exception("timeout")):
        check_tracking(row, cfg, db)  # must not raise

    assert db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0


def test_claude_error_sends_unavailable_summary(db, cfg):
    old = "old"
    h = hashlib.sha256(old.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=old)

    with patch("digestor.tracker.fetch_rendered_text", return_value="new"), \
         patch("digestor.tracker.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.side_effect = Exception("API error")
        check_tracking(row, cfg, db)

    notif = db.execute("SELECT content FROM notifications").fetchone()
    assert "summary unavailable" in notif["content"]
