import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_TEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    type              TEXT NOT NULL,
    content           TEXT NOT NULL,
    status            TEXT DEFAULT 'pending',
    repeat_interval_h REAL,
    next_fire_at      TEXT,
    cancelled_at      TEXT,
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS replies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT DEFAULT (datetime('now')),
    matrix_sender TEXT NOT NULL,
    content       TEXT NOT NULL,
    applied       INTEGER DEFAULT 0
);
"""


def init_test_db(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_TEST_SCHEMA)
    conn.commit()
    return conn


def get_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    now = datetime.now(timezone.utc).isoformat()
    return conn.execute(
        """SELECT * FROM notifications
           WHERE status = 'pending'
             AND cancelled_at IS NULL
             AND (next_fire_at IS NULL OR next_fire_at <= ?)
        """,
        (now,),
    ).fetchall()


def mark_sent(conn: sqlite3.Connection, notif_id: int) -> None:
    conn.execute("UPDATE notifications SET status='sent' WHERE id=?", (notif_id,))
    conn.commit()


def cancel_notif(conn: sqlite3.Connection, notif_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE notifications SET cancelled_at=? WHERE id=?", (now, notif_id)
    )
    conn.commit()


def cancel_all(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE notifications SET cancelled_at=? WHERE cancelled_at IS NULL AND repeat_interval_h IS NOT NULL",
        (now,),
    )
    conn.commit()


def insert_reply(conn: sqlite3.Connection, sender: str, content: str) -> None:
    conn.execute(
        "INSERT INTO replies(matrix_sender, content) VALUES(?,?)", (sender, content)
    )
    conn.commit()
