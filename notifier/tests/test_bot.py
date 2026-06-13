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


# --- !track / !untrack / !list tests ---

async def test_track_command_inserts_tracking(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", "!track daily https://example.com/ for venue")
    row = db.execute("SELECT * FROM trackings WHERE url='https://example.com/'").fetchone()
    assert row is not None
    assert row["interval_h"] == 24.0
    assert row["label"] == "venue"
    mock_send.assert_called_once()
    assert "[" in mock_send.call_args[0][0]  # reply contains tracking ID


async def test_track_command_without_label(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock):
        await bot.handle_message("@alice:example.com", "!track 6h https://rss.example.com/feed")
    row = db.execute("SELECT * FROM trackings WHERE url='https://rss.example.com/feed'").fetchone()
    assert row is not None
    assert row["interval_h"] == 6.0
    assert row["label"] is None


async def test_track_command_bad_interval(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", "!track badinterval https://example.com/")
    assert db.execute("SELECT COUNT(*) FROM trackings").fetchone()[0] == 0
    assert "interval" in mock_send.call_args[0][0].lower()


async def test_track_command_missing_url(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", "!track daily")
    assert db.execute("SELECT COUNT(*) FROM trackings").fetchone()[0] == 0
    assert "Usage" in mock_send.call_args[0][0]


async def test_untrack_command_cancels_tracking(bot, db):
    from notifier.db import insert_tracking
    tid = insert_tracking(db, "https://example.com", "test", 24.0)

    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", f"!untrack {tid}")

    row = db.execute("SELECT cancelled_at FROM trackings WHERE id=?", (tid,)).fetchone()
    assert row[0] is not None
    assert str(tid) in mock_send.call_args[0][0]


async def test_untrack_command_unknown_id(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", "!untrack 9999")
    assert "not found" in mock_send.call_args[0][0]


async def test_untrack_command_bad_id(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", "!untrack abc")
    assert "Usage" in mock_send.call_args[0][0]


async def test_list_command_shows_trackings(bot, db):
    from notifier.db import insert_tracking
    insert_tracking(db, "https://example.com", "the venue", 24.0)
    insert_tracking(db, "https://rss.example.com/", None, 6.0)

    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", "!list")

    reply = mock_send.call_args[0][0]
    assert "https://example.com" in reply
    assert "https://rss.example.com/" in reply
    assert "Pending notifications" in reply


async def test_list_command_empty(bot, db):
    with patch.object(bot, "send_notification", new_callable=AsyncMock) as mock_send:
        await bot.handle_message("@alice:example.com", "!list")

    reply = mock_send.call_args[0][0]
    assert "No active trackings" in reply
    assert "Pending notifications" in reply


async def test_parse_interval_variants(bot, db):
    cases = [
        ("hourly", 1.0, "https://a.com"),
        ("daily", 24.0, "https://b.com"),
        ("weekly", 168.0, "https://c.com"),
        ("12h", 12.0, "https://d.com"),
        ("2d", 48.0, "https://e.com"),
        ("1w", 168.0, "https://f.com"),
    ]
    for interval_str, expected_h, url in cases:
        with patch.object(bot, "send_notification", new_callable=AsyncMock):
            await bot.handle_message("@alice:example.com", f"!track {interval_str} {url}")
        row = db.execute("SELECT interval_h FROM trackings WHERE url=?", (url,)).fetchone()
        assert row is not None, f"no row for {interval_str}"
        assert row[0] == expected_h, f"{interval_str} → expected {expected_h}, got {row[0]}"
