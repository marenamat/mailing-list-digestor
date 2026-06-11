import asyncio, sqlite3
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from notifier.config import Config
from notifier.bot import MatrixBot
from notifier.db import init_test_db


@pytest.fixture
def cfg():
    c = Config.from_env()
    c.homeserver = "https://matrix.example.com"
    c.username = "@bot:example.com"
    c.password = "secret"
    c.whitelist = {"@alice:example.com"}
    c.room_id = "!room:example.com"
    return c


@pytest.fixture
def db(tmp_path):
    return init_test_db(str(tmp_path / "test.db"))


@pytest.fixture
def bot(cfg, db):
    return MatrixBot(cfg, db)


def test_bot_is_whitelist_member(bot):
    assert bot.is_allowed("@alice:example.com")
    assert not bot.is_allowed("@eve:example.com")


async def test_send_notification_calls_room_send(bot):
    with patch.object(bot._client, "room_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = MagicMock()
        await bot.send_notification("Hello!")
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs or {}
    call_args = mock_send.call_args.args
    # body should appear in the content dict
    content = call_kwargs.get("content") or (call_args[1] if len(call_args) > 1 else None)
    assert content is not None
    assert "Hello!" in str(content)


async def test_handle_cancel_cancels_notification(bot, db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO notifications(type, content, status, next_fire_at) VALUES(?,?,?,?)",
        ("urgent", "Something urgent", "pending", now),
    )
    db.commit()
    notif_id = db.execute("SELECT id FROM notifications").fetchone()[0]

    with patch.object(bot, "send_notification", new_callable=AsyncMock):
        await bot.handle_message("@alice:example.com", f"!cancel {notif_id}")

    row = db.execute("SELECT cancelled_at FROM notifications WHERE id=?", (notif_id,)).fetchone()
    assert row[0] is not None


async def test_handle_cancel_all(bot, db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for i in range(2):
        db.execute(
            "INSERT INTO notifications(type, content, status, next_fire_at, repeat_interval_h) VALUES(?,?,?,?,?)",
            ("urgent", f"Notif {i}", "pending", now, 24.0),
        )
    db.commit()
    with patch.object(bot, "send_notification", new_callable=AsyncMock):
        await bot.handle_message("@alice:example.com", "!cancel-all")
    rows = db.execute(
        "SELECT * FROM notifications WHERE cancelled_at IS NULL AND repeat_interval_h IS NOT NULL"
    ).fetchall()
    assert len(rows) == 0


async def test_handle_regular_message_inserts_reply(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock):
        await bot.handle_message("@alice:example.com", "Please focus on QUIC drafts")
    row = db.execute("SELECT content FROM replies").fetchone()
    assert row is not None
    assert "QUIC" in row[0]


async def test_unknown_sender_ignored(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@eve:example.com", "malicious content")
    mock_send.assert_not_called()
    row = db.execute("SELECT * FROM replies").fetchone()
    assert row is None
