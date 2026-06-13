import sqlite3, pytest
from datetime import datetime, timezone
from notifier.db import (
    fetch_pending,
    mark_sent,
    cancel_notif,
    cancel_all,
    insert_reply,
    init_test_db,
    insert_tracking,
    cancel_tracking,
    fetch_active_trackings,
)


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


def test_insert_tracking_returns_id(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    tid = insert_tracking(conn, "https://example.com", "venue", 24.0)
    assert isinstance(tid, int)
    assert tid > 0


def test_insert_tracking_no_label(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    tid = insert_tracking(conn, "https://example.com", None, 6.0)
    row = conn.execute("SELECT label FROM trackings WHERE id=?", (tid,)).fetchone()
    assert row[0] is None


def test_cancel_tracking_sets_cancelled_at(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    tid = insert_tracking(conn, "https://example.com", "test", 24.0)
    cancel_tracking(conn, tid)
    row = conn.execute("SELECT cancelled_at FROM trackings WHERE id=?", (tid,)).fetchone()
    assert row[0] is not None


def test_fetch_active_trackings_excludes_cancelled(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    t1 = insert_tracking(conn, "https://a.com", "a", 24.0)
    t2 = insert_tracking(conn, "https://b.com", "b", 6.0)
    cancel_tracking(conn, t2)
    rows = fetch_active_trackings(conn)
    ids = [r["id"] for r in rows]
    assert t1 in ids
    assert t2 not in ids


def test_fetch_active_trackings_ordered_by_id(tmp_path):
    conn = init_test_db(str(tmp_path / "test.db"))
    t1 = insert_tracking(conn, "https://a.com", "a", 24.0)
    t2 = insert_tracking(conn, "https://b.com", "b", 6.0)
    rows = fetch_active_trackings(conn)
    assert rows[0]["id"] == t1
    assert rows[1]["id"] == t2
