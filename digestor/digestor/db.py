import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      TEXT    UNIQUE NOT NULL,
    date            TEXT    NOT NULL,
    from_addr       TEXT,
    subject         TEXT,
    list_addr       TEXT,
    working_group   TEXT,
    body_text       TEXT,
    urgency_local   TEXT,
    urgency_claude  TEXT,
    rationale       TEXT,
    processed_at    TEXT,
    source          TEXT    DEFAULT 'smtp'
);

CREATE TABLE IF NOT EXISTS digests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    working_group TEXT NOT NULL,
    content      TEXT NOT NULL,
    token_input  INTEGER,
    token_output INTEGER,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS token_usage (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT DEFAULT (datetime('now')),
    model        TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    purpose      TEXT NOT NULL
);

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

CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
    subject, body_text,
    content=emails, content_rowid=id
);

CREATE TABLE IF NOT EXISTS trackings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    url               TEXT NOT NULL,
    label             TEXT,
    interval_h        REAL NOT NULL,
    last_content_hash TEXT,
    last_content_text TEXT,
    last_checked_at   TEXT,
    last_changed_at   TEXT,
    created_at        TEXT DEFAULT (datetime('now')),
    cancelled_at      TEXT
);
"""

def init_db(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def get_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
