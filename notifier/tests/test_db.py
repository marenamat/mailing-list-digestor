import sqlite3, pytest
from datetime import datetime, timezone
from notifier.db import fetch_pending, mark_sent, cancel_notif, cancel_all, insert_reply, init_test_db


def test_fetch_pending_returns_due_notifications(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO notifications(type, content, status, next_fire_at) VALUES(?,?,?,?)",
        ("urgent", "Test notification", "pending", now),
    )
    conn.commit()
    rows = fetch_pending(conn)
    assert len(rows) == 1
    assert rows[0]["content"] == "Test notification"


def test_fetch_pending_excludes_cancelled(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO notifications(type, content, status, next_fire_at, cancelled_at) VALUES(?,?,?,?,?)",
        ("urgent", "Cancelled", "pending", now, now),
    )
    conn.commit()
    rows = fetch_pending(conn)
    assert len(rows) == 0


def test_mark_sent(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO notifications(type, content, status, next_fire_at) VALUES(?,?,?,?)",
        ("digest", "Content", "pending", now),
    )
    conn.commit()
    notif_id = conn.execute("SELECT id FROM notifications").fetchone()[0]
    mark_sent(conn, notif_id)
    row = conn.execute("SELECT status FROM notifications WHERE id=?", (notif_id,)).fetchone()
    assert row[0] == "sent"


def test_cancel_notif(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO notifications(type, content, status, next_fire_at) VALUES(?,?,?,?)",
        ("urgent", "Content", "pending", now),
    )
    conn.commit()
    notif_id = conn.execute("SELECT id FROM notifications").fetchone()[0]
    cancel_notif(conn, notif_id)
    row = conn.execute("SELECT cancelled_at FROM notifications WHERE id=?", (notif_id,)).fetchone()
    assert row[0] is not None


def test_cancel_all(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    now = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        conn.execute(
            "INSERT INTO notifications(type, content, status, next_fire_at, repeat_interval_h) VALUES(?,?,?,?,?)",
            ("urgent", f"Notif {i}", "pending", now, 24.0),
        )
    conn.commit()
    cancel_all(conn)
    rows = conn.execute(
        "SELECT * FROM notifications WHERE cancelled_at IS NULL AND repeat_interval_h IS NOT NULL"
    ).fetchall()
    assert len(rows) == 0


def test_insert_reply(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    insert_reply(conn, "@alice:example.com", "I agree with this")
    row = conn.execute("SELECT content, matrix_sender FROM replies").fetchone()
    assert row[0] == "I agree with this"
    assert row[1] == "@alice:example.com"
