import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from digestor.db import init_db
from digestor.config import Config
from digestor.pipeline import process_eml

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def db(tmp_path):
    return init_db(str(tmp_path / "test.db"))

@pytest.fixture
def cfg(tmp_path):
    c = Config.from_env()
    c.anthropic_api_key = "sk-test"
    return c

def test_process_stores_email_in_db(db, cfg):
    with patch("digestor.pipeline.classify_urgency", return_value="not_urgent"), \
         patch("digestor.pipeline.classify_urgent", return_value=("not_urgent", "routine", 10, 5)):
        process_eml(FIXTURES / "sample.eml", cfg, db)

    row = db.execute("SELECT * FROM emails WHERE message_id='<sample-001@example.com>'").fetchone()
    assert row is not None
    assert row["subject"] == "Re: QUIC multipath latest revision"

def test_process_urgent_email_creates_notification(db, cfg):
    with patch("digestor.pipeline.classify_urgency", return_value="urgent"), \
         patch("digestor.pipeline.classify_urgent", return_value=("urgent", "CFP deadline soon", 50, 20)):
        process_eml(FIXTURES / "cfp.eml", cfg, db)

    notif = db.execute("SELECT * FROM notifications WHERE status='pending'").fetchone()
    assert notif is not None
    assert notif["type"] == "urgent"

def test_process_duplicate_skipped(db, cfg):
    with patch("digestor.pipeline.classify_urgency", return_value="not_urgent"), \
         patch("digestor.pipeline.classify_urgent", return_value=("not_urgent", "", 0, 0)):
        process_eml(FIXTURES / "sample.eml", cfg, db)
        process_eml(FIXTURES / "sample.eml", cfg, db)

    rows = db.execute("SELECT COUNT(*) FROM emails WHERE message_id='<sample-001@example.com>'").fetchone()
    assert rows[0] == 1
