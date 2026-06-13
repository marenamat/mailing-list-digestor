from unittest.mock import MagicMock, patch

import pytest

from digestor.config import Config
from digestor.db import init_db


@pytest.fixture
def db(tmp_path):
    return init_db(str(tmp_path / "test.db"))


@pytest.fixture
def cfg():
    return Config()


def test_build_scheduler_includes_poll_trackings_job(cfg, db):
    from digestor.scheduler import build_scheduler
    scheduler = build_scheduler(cfg, db)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "poll_trackings" in job_ids
    assert "daily_digest" in job_ids


def test_poll_trackings_calls_check_for_due_row(db, cfg):
    db.execute(
        "INSERT INTO trackings(url, label, interval_h) VALUES(?,?,?)",
        ("https://example.com", "test", 24.0),
    )
    db.commit()

    with patch("digestor.scheduler.check_tracking") as mock_check:
        from digestor.scheduler import _poll_trackings
        _poll_trackings(cfg, db)

    mock_check.assert_called_once()
    assert mock_check.call_args[0][0]["url"] == "https://example.com"


def test_poll_trackings_skips_cancelled(db, cfg):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO trackings(url, label, interval_h, cancelled_at) VALUES(?,?,?,?)",
        ("https://example.com", "test", 24.0, now),
    )
    db.commit()

    with patch("digestor.scheduler.check_tracking") as mock_check:
        from digestor.scheduler import _poll_trackings
        _poll_trackings(cfg, db)

    mock_check.assert_not_called()


def test_poll_trackings_skips_not_yet_due(db, cfg):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO trackings(url, label, interval_h, last_checked_at) VALUES(?,?,?,?)",
        ("https://example.com", "test", 24.0, now),
    )
    db.commit()

    with patch("digestor.scheduler.check_tracking") as mock_check:
        from digestor.scheduler import _poll_trackings
        _poll_trackings(cfg, db)

    mock_check.assert_not_called()


def test_poll_trackings_continues_after_error(db, cfg):
    db.execute(
        "INSERT INTO trackings(url, label, interval_h) VALUES(?,?,?)",
        ("https://a.com", "a", 24.0),
    )
    db.execute(
        "INSERT INTO trackings(url, label, interval_h) VALUES(?,?,?)",
        ("https://b.com", "b", 24.0),
    )
    db.commit()

    call_count = 0

    def mock_check(row, cfg, db):
        nonlocal call_count
        call_count += 1
        if row["url"] == "https://a.com":
            raise Exception("fetch failed")

    with patch("digestor.scheduler.check_tracking", side_effect=mock_check):
        from digestor.scheduler import _poll_trackings
        _poll_trackings(cfg, db)

    assert call_count == 2


def test_poll_trackings_calls_check_for_overdue_row(db, cfg):
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    db.execute(
        "INSERT INTO trackings(url, label, interval_h, last_checked_at) VALUES(?,?,?,?)",
        ("https://example.com", "test", 24.0, past),
    )
    db.commit()

    with patch("digestor.scheduler.check_tracking") as mock_check:
        from digestor.scheduler import _poll_trackings
        _poll_trackings(cfg, db)

    mock_check.assert_called_once()
