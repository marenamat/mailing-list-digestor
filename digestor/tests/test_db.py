import pytest, sqlite3
from digestor.db import init_db, get_db

def test_init_creates_all_tables(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert tables >= {"emails", "digests", "token_usage", "notifications", "replies", "trackings"}

def test_fts5_table_exists(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='emails_fts'"
    ).fetchall()
    assert rows, "emails_fts FTS5 virtual table missing"

def test_insert_and_fetch_email(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    conn.execute("""
        INSERT INTO emails (message_id, date, from_addr, subject, list_addr, working_group, body_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("<test@1>", "2026-06-11T00:00:00", "a@b.com", "Hello", "list@ietf.org", "QUIC", "body"))
    conn.commit()
    row = conn.execute("SELECT subject FROM emails WHERE message_id='<test@1>'").fetchone()
    assert row["subject"] == "Hello"

def test_fts5_search(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    conn.execute("""
        INSERT INTO emails (message_id, date, from_addr, subject, list_addr, working_group, body_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("<fts@1>", "2026-06-11T00:00:00", "a@b.com", "QUIC multipath proposal", "quic@ietf.org", "QUIC", "extended QUIC multipath support"))
    conn.commit()
    conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('rebuild')")
    rows = conn.execute("SELECT subject FROM emails_fts WHERE emails_fts MATCH 'multipath'").fetchall()
    assert rows
