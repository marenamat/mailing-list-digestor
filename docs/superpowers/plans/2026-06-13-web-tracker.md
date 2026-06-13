# Web Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `!track`, `!untrack`, and `!list` Matrix bot commands that poll URLs via headless Chromium, detect content changes by hash, and call Claude to summarise what changed.

**Architecture:** Bot commands (notifier) write to a `trackings` table in the shared SQLite database. The digestor scheduler polls due trackings every 5 minutes, fetches rendered DOM text via Playwright, compares SHA-256 hashes, and on change calls Claude for a diff summary queued as a notification. The notifier delivers it to Matrix as normal.

**Tech Stack:** `playwright` (sync API, bundled Chromium), `hashlib` (stdlib), `anthropic` (already present), `apscheduler` (already present), `sqlite3` (already present).

---

## Context for implementers

The repo has two Python packages:

- `digestor/` — watches Maildir, triages emails with ollama + Claude, runs scheduled jobs. Has `db.py` (SQLite schema), `scheduler.py` (APScheduler), `classifier.py` (Claude calls). Tests mock external calls with `unittest.mock.patch`.
- `notifier/` — Matrix bot, delivers notifications from the shared SQLite DB. Has `bot.py` (command handling), `db.py` (DB helpers). Tests use `init_test_db()` with an in-memory-style temp DB.

Both packages share `/data/digestor.db`. The notifier's `db.py` keeps its own `_TEST_SCHEMA` (a subset of the full schema) so its tests don't depend on the digestor package.

Run digestor tests: `.venv/bin/pytest digestor/tests/ -v`
Run notifier tests: `.venv/bin/pytest notifier/tests/ -v`
Run suites separately — they conflict if run together from root.

---

## Task 1: trackings table in DB schema

**Files:**
- Modify: `digestor/digestor/db.py`
- Modify: `digestor/tests/test_db.py`
- Modify: `notifier/notifier/db.py`
- Modify: `notifier/tests/test_db.py`

- [ ] **Step 1: Write a failing test for the trackings table in the digestor**

In `digestor/tests/test_db.py`, add to the existing `test_init_creates_all_tables` test:

```python
def test_init_creates_all_tables(tmp_path):
    conn = init_db(str(tmp_path / "test.db"))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert tables >= {"emails", "digests", "token_usage", "notifications", "replies", "trackings"}
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/pytest digestor/tests/test_db.py::test_init_creates_all_tables -v
```

Expected: FAIL — `trackings` not in tables.

- [ ] **Step 3: Add trackings to digestor SCHEMA**

In `digestor/digestor/db.py`, append to the `SCHEMA` string (before the closing `"""`):

```python
SCHEMA = """
...existing tables...

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
```

- [ ] **Step 4: Run to verify it passes**

```bash
.venv/bin/pytest digestor/tests/test_db.py -v
```

Expected: all PASS.

- [ ] **Step 5: Write failing tests for notifier db helpers**

In `notifier/tests/test_db.py`, add at the bottom:

```python
from notifier.db import insert_tracking, cancel_tracking, fetch_active_trackings


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
```

- [ ] **Step 6: Run to verify they fail**

```bash
.venv/bin/pytest notifier/tests/test_db.py -v -k "tracking"
```

Expected: FAIL — `ImportError: cannot import name 'insert_tracking'`.

- [ ] **Step 7: Add trackings to notifier _TEST_SCHEMA and implement helpers**

In `notifier/notifier/db.py`, add to `_TEST_SCHEMA`:

```python
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
```

Then add three new functions at the bottom of `notifier/notifier/db.py`:

```python
def insert_tracking(conn: sqlite3.Connection, url: str, label: str | None, interval_h: float) -> int:
    cur = conn.execute(
        "INSERT INTO trackings(url, label, interval_h) VALUES(?,?,?)",
        (url, label, interval_h),
    )
    conn.commit()
    return cur.lastrowid


def cancel_tracking(conn: sqlite3.Connection, tracking_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE trackings SET cancelled_at=? WHERE id=?",
        (now, tracking_id),
    )
    conn.commit()


def fetch_active_trackings(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM trackings WHERE cancelled_at IS NULL ORDER BY id"
    ).fetchall()
```

- [ ] **Step 8: Run to verify they pass**

```bash
.venv/bin/pytest notifier/tests/test_db.py -v
```

Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add digestor/digestor/db.py digestor/tests/test_db.py \
        notifier/notifier/db.py notifier/tests/test_db.py
git commit -m "feat(tracker): add trackings table and notifier db helpers"
```

---

## Task 2: Crawler module

**Files:**
- Create: `digestor/digestor/crawler.py`
- Create: `digestor/tests/test_crawler.py`
- Modify: `digestor/pyproject.toml`

- [ ] **Step 1: Write the failing test**

Create `digestor/tests/test_crawler.py`:

```python
from unittest.mock import MagicMock, patch


def _make_playwright_mock(inner_text: str):
    mock_page = MagicMock()
    mock_page.evaluate.return_value = inner_text

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_p)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    return mock_ctx, mock_page, mock_browser


def test_fetch_rendered_text_returns_inner_text():
    mock_ctx, mock_page, mock_browser = _make_playwright_mock("Hello from the page")

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        result = fetch_rendered_text("https://example.com")

    assert result == "Hello from the page"


def test_fetch_rendered_text_navigates_to_url():
    mock_ctx, mock_page, _ = _make_playwright_mock("content")

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        fetch_rendered_text("https://example.com/path")

    mock_page.goto.assert_called_once_with(
        "https://example.com/path", wait_until="networkidle", timeout=30000
    )


def test_fetch_rendered_text_closes_browser():
    mock_ctx, _, mock_browser = _make_playwright_mock("content")

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        fetch_rendered_text("https://example.com")

    mock_browser.close.assert_called_once()


def test_fetch_rendered_text_closes_browser_on_error():
    mock_page = MagicMock()
    mock_page.goto.side_effect = Exception("Navigation failed")

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_p)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch("digestor.crawler.sync_playwright", return_value=mock_ctx):
        from digestor.crawler import fetch_rendered_text
        try:
            fetch_rendered_text("https://example.com")
        except Exception:
            pass

    mock_browser.close.assert_called_once()
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/pytest digestor/tests/test_crawler.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'digestor.crawler'`.

- [ ] **Step 3: Create `digestor/digestor/crawler.py`**

```python
from playwright.sync_api import sync_playwright


def fetch_rendered_text(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            return page.evaluate("document.body.innerText")
        finally:
            browser.close()
```

- [ ] **Step 4: Add playwright to digestor/pyproject.toml**

In `digestor/pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    "anthropic>=0.30",
    "ollama>=0.3",
    "watchdog>=4",
    "apscheduler>=3.10",
    "httpx>=0.27",
    "pyyaml>=6",
    "playwright>=1.44",
]
```

- [ ] **Step 5: Install playwright in the venv**

```bash
.venv/bin/pip install -e digestor/
.venv/bin/playwright install chromium
```

Expected: playwright installs, then Chromium downloads (~150 MB).

- [ ] **Step 6: Run tests to verify they pass**

```bash
.venv/bin/pytest digestor/tests/test_crawler.py -v
```

Expected: all 4 PASS (tests use mocks, no real browser needed).

- [ ] **Step 7: Commit**

```bash
git add digestor/digestor/crawler.py digestor/tests/test_crawler.py digestor/pyproject.toml
git commit -m "feat(tracker): add playwright crawler module"
```

---

## Task 3: Tracker module

**Files:**
- Create: `digestor/digestor/tracker.py`
- Create: `digestor/tests/test_tracker.py`

- [ ] **Step 1: Write the failing tests**

Create `digestor/tests/test_tracker.py`:

```python
import hashlib
from unittest.mock import MagicMock, patch

import pytest

from digestor.config import Config
from digestor.db import init_db


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
        from digestor.tracker import check_tracking
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
        from digestor.tracker import check_tracking
        check_tracking(row, cfg, db)

    MockA.assert_not_called()


def test_no_change_updates_last_checked_only(db, cfg):
    text = "stable content"
    h = hashlib.sha256(text.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=text)

    with patch("digestor.tracker.fetch_rendered_text", return_value=text):
        from digestor.tracker import check_tracking
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
        from digestor.tracker import check_tracking
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
        from digestor.tracker import check_tracking
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
        from digestor.tracker import check_tracking
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
        from digestor.tracker import check_tracking
        check_tracking(row, cfg, db)

    updated = db.execute("SELECT last_content_text FROM trackings WHERE id=?", (row["id"],)).fetchone()
    assert len(updated[0]) == 100_000


def test_fetch_error_is_logged_not_raised(db, cfg):
    row = _insert_tracking(db)

    with patch("digestor.tracker.fetch_rendered_text", side_effect=Exception("timeout")):
        from digestor.tracker import check_tracking
        check_tracking(row, cfg, db)  # must not raise

    assert db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0


def test_claude_error_sends_unavailable_summary(db, cfg):
    old = "old"
    h = hashlib.sha256(old.encode()).hexdigest()
    row = _insert_tracking(db, last_hash=h, last_text=old)

    with patch("digestor.tracker.fetch_rendered_text", return_value="new"), \
         patch("digestor.tracker.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.side_effect = Exception("API error")
        from digestor.tracker import check_tracking
        check_tracking(row, cfg, db)

    notif = db.execute("SELECT content FROM notifications").fetchone()
    assert "summary unavailable" in notif["content"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest digestor/tests/test_tracker.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'digestor.tracker'`.

- [ ] **Step 3: Create `digestor/digestor/tracker.py`**

```python
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone

import anthropic

from digestor.config import Config
from digestor.crawler import fetch_rendered_text

log = logging.getLogger(__name__)

_MAX_CONTENT_LEN = 100_000
_LLM_SNIPPET_LEN = 4_000

_PROMPT = """You are monitoring a webpage for changes.
Tracking goal: {label}
URL: {url}

PREVIOUS CONTENT (truncated):
{prev_text}

CURRENT CONTENT (truncated):
{new_text}

Summarise what changed in 2-3 sentences, focusing on what is relevant to the tracking goal."""


def check_tracking(row: sqlite3.Row, cfg: Config, db: sqlite3.Connection) -> None:
    url = row["url"]
    label = row["label"] or url
    now = datetime.now(timezone.utc).isoformat()

    try:
        text = fetch_rendered_text(url)
    except Exception:
        log.exception("Failed to fetch %s", url)
        return

    new_hash = hashlib.sha256(text.encode()).hexdigest()

    if new_hash == row["last_content_hash"]:
        db.execute("UPDATE trackings SET last_checked_at=? WHERE id=?", (now, row["id"]))
        db.commit()
        return

    if row["last_content_text"] is None:
        db.execute(
            "UPDATE trackings SET last_content_hash=?, last_content_text=?, last_checked_at=? WHERE id=?",
            (new_hash, text[:_MAX_CONTENT_LEN], now, row["id"]),
        )
        db.execute(
            "INSERT INTO notifications(type, content, status) VALUES(?,?,?)",
            ("tracking", f"Now tracking: {label}\n{url}", "pending"),
        )
        db.commit()
        return

    summary, in_tok, out_tok = _summarise_change(
        label, url, row["last_content_text"], text, cfg.anthropic_api_key
    )

    db.execute(
        "UPDATE trackings SET last_content_hash=?, last_content_text=?, last_checked_at=?, last_changed_at=? WHERE id=?",
        (new_hash, text[:_MAX_CONTENT_LEN], now, now, row["id"]),
    )
    db.execute(
        "INSERT INTO notifications(type, content, status) VALUES(?,?,?)",
        ("tracking", f"**Change detected: {label}**\n{url}\n\n{summary}", "pending"),
    )
    db.execute(
        "INSERT INTO token_usage(model, input_tokens, output_tokens, purpose) VALUES(?,?,?,?)",
        ("claude-sonnet-4-6", in_tok, out_tok, f"tracking:{url}"),
    )
    db.commit()


def _summarise_change(
    label: str, url: str, prev_text: str, new_text: str, api_key: str
) -> tuple[str, int, int]:
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": _PROMPT.format(
                    label=label,
                    url=url,
                    prev_text=prev_text[:_LLM_SNIPPET_LEN],
                    new_text=new_text[:_LLM_SNIPPET_LEN],
                ),
            }],
        )
        return msg.content[0].text, msg.usage.input_tokens, msg.usage.output_tokens
    except Exception:
        log.exception("Claude summarise failed for %s", url)
        return "(summary unavailable)", 0, 0
```

- [ ] **Step 4: Run to verify they pass**

```bash
.venv/bin/pytest digestor/tests/test_tracker.py -v
```

Expected: all 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add digestor/digestor/tracker.py digestor/tests/test_tracker.py
git commit -m "feat(tracker): add tracker module with hash-based change detection"
```

---

## Task 4: Scheduler integration

**Files:**
- Modify: `digestor/digestor/scheduler.py`

- [ ] **Step 1: Write the failing test**

Create `digestor/tests/test_scheduler.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest digestor/tests/test_scheduler.py -v
```

Expected: FAIL — `poll_trackings` job not found, `_poll_trackings` not importable.

- [ ] **Step 3: Update `digestor/digestor/scheduler.py`**

Replace the entire file:

```python
import logging
import sqlite3
from datetime import datetime, timezone, date

from apscheduler.schedulers.background import BackgroundScheduler

from digestor.config import Config
from digestor.digest import generate_digest
from digestor.tracker import check_tracking

log = logging.getLogger(__name__)


def _run_daily_digest(cfg: Config, db: sqlite3.Connection) -> None:
    today = date.today().isoformat()
    log.info("Running daily digest for %s", today)
    lists = cfg.load_lists()
    context = cfg.load_context()

    wgs = set(lists.keys()) | {"General"}
    for wg in wgs:
        wg_lists = lists.get(wg, [])
        if wg_lists:
            placeholders = ",".join("?" * len(wg_lists))
            rows = db.execute(
                f"SELECT * FROM emails WHERE DATE(date)=? AND list_addr IN ({placeholders}) AND urgency_claude != 'urgent'",
                [today] + wg_lists,
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM emails WHERE DATE(date)=? AND working_group=? AND urgency_claude != 'urgent'",
                (today, wg),
            ).fetchall()

        emails = [dict(r) for r in rows]
        content, in_tok, out_tok = generate_digest(emails, wg, context, cfg.anthropic_api_key)

        db.execute(
            "INSERT INTO digests(date, working_group, content, token_input, token_output) VALUES(?,?,?,?,?)",
            (today, wg, content, in_tok, out_tok),
        )
        db.execute(
            "INSERT INTO token_usage(model, input_tokens, output_tokens, purpose) VALUES(?,?,?,?)",
            ("claude-sonnet-4-6", in_tok, out_tok, f"digest:{wg}"),
        )
        db.execute(
            "INSERT INTO notifications(type, content, status, next_fire_at) VALUES(?,?,?,?)",
            ("digest", f"**Daily digest — {wg}**\n\n{content}", "pending",
             datetime.now(timezone.utc).isoformat()),
        )
    db.commit()
    log.info("Daily digest complete")


def _poll_trackings(cfg: Config, db: sqlite3.Connection) -> None:
    rows = db.execute(
        """SELECT * FROM trackings
           WHERE cancelled_at IS NULL
             AND (last_checked_at IS NULL
                  OR datetime(last_checked_at, '+' || CAST(ROUND(interval_h * 60) AS INTEGER) || ' minutes') <= datetime('now'))"""
    ).fetchall()
    for row in rows:
        try:
            check_tracking(row, cfg, db)
        except Exception:
            log.exception("Tracking check failed for %s", row["url"])


def build_scheduler(cfg: Config, db: sqlite3.Connection) -> BackgroundScheduler:
    hour, minute = (int(x) for x in cfg.digest_time.split(":"))
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _run_daily_digest,
        "cron",
        hour=hour,
        minute=minute,
        args=[cfg, db],
        id="daily_digest",
    )
    scheduler.add_job(
        _poll_trackings,
        "interval",
        minutes=5,
        args=[cfg, db],
        id="poll_trackings",
    )
    return scheduler
```

- [ ] **Step 4: Run to verify they pass**

```bash
.venv/bin/pytest digestor/tests/test_scheduler.py -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Run full digestor suite to check for regressions**

```bash
.venv/bin/pytest digestor/tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add digestor/digestor/scheduler.py digestor/tests/test_scheduler.py
git commit -m "feat(tracker): add tracking poll job to digestor scheduler"
```

---

## Task 5: Bot commands (!track, !untrack, !list)

**Files:**
- Modify: `notifier/notifier/bot.py`
- Modify: `notifier/tests/test_bot.py`

- [ ] **Step 1: Write failing tests**

Add to the bottom of `notifier/tests/test_bot.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
.venv/bin/pytest notifier/tests/test_bot.py -v -k "track or untrack or list"
```

Expected: FAIL — commands not yet implemented.

- [ ] **Step 3: Update `notifier/notifier/bot.py`**

Replace the entire file:

```python
import asyncio
import logging
import re
import sqlite3

from nio import AsyncClient, RoomMessageText

from notifier.config import Config
from notifier.db import (
    cancel_all,
    cancel_notif,
    cancel_tracking,
    fetch_active_trackings,
    fetch_pending,
    insert_reply,
    insert_tracking,
    mark_sent,
)

log = logging.getLogger(__name__)


def _parse_interval(s: str) -> float | None:
    s = s.lower().strip()
    if s == "hourly":
        return 1.0
    if s == "daily":
        return 24.0
    if s == "weekly":
        return 168.0
    m = re.match(r"^(\d+(?:\.\d+)?)h$", s)
    if m:
        return float(m.group(1))
    m = re.match(r"^(\d+(?:\.\d+)?)d$", s)
    if m:
        return float(m.group(1)) * 24
    m = re.match(r"^(\d+(?:\.\d+)?)w$", s)
    if m:
        return float(m.group(1)) * 168
    return None


def _format_interval(h: float) -> str:
    if h == 1.0:
        return "hourly"
    if h == 24.0:
        return "daily"
    if h == 168.0:
        return "weekly"
    if h >= 24 and h % 24 == 0:
        return f"{int(h // 24)}d"
    return f"{h:g}h"


class MatrixBot:
    def __init__(self, cfg: Config, db: sqlite3.Connection):
        self._cfg = cfg
        self._db = db
        self._client = AsyncClient(cfg.homeserver, cfg.username)

    def is_allowed(self, sender: str) -> bool:
        return sender in self._cfg.whitelist

    async def login(self) -> None:
        await self._client.login(self._cfg.password)
        log.info("Logged in as %s", self._cfg.username)

    async def send_notification(self, text: str) -> None:
        if not self._cfg.room_id:
            log.warning("MATRIX_ROOM_ID not set — cannot send notification")
            return
        await self._client.room_send(
            room_id=self._cfg.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": text},
        )

    async def handle_message(self, sender: str, body: str) -> None:
        if not self.is_allowed(sender):
            log.warning("Ignored message from unknown sender: %s", sender)
            return

        body = body.strip()

        if body.startswith("!cancel-all"):
            cancel_all(self._db)
            await self.send_notification("All repeating notifications cancelled.")

        elif body.startswith("!cancel "):
            try:
                notif_id = int(body.split()[1])
                cancel_notif(self._db, notif_id)
                await self.send_notification(f"Notification {notif_id} cancelled.")
            except (IndexError, ValueError):
                await self.send_notification("Usage: !cancel <id>")

        elif body.startswith("!track "):
            await self._handle_track(body)

        elif body.startswith("!untrack "):
            await self._handle_untrack(body)

        elif body == "!list":
            await self._handle_list()

        else:
            insert_reply(self._db, sender, body)
            log.info("Reply from %s stored", sender)

    async def _handle_track(self, body: str) -> None:
        parts = body[len("!track "):].split(None, 2)
        if len(parts) < 2:
            await self.send_notification(
                "Usage: !track <interval> <url> [for <description>]\n"
                "Intervals: hourly, daily, weekly, Nh, Nd, Nw"
            )
            return
        interval_str, url = parts[0], parts[1]
        label = None
        if len(parts) == 3 and parts[2].startswith("for "):
            label = parts[2][4:].strip() or None
        interval_h = _parse_interval(interval_str)
        if interval_h is None:
            await self.send_notification(
                f"Unknown interval '{interval_str}'. Use: hourly, daily, weekly, Nh, Nd, Nw"
            )
            return
        tid = insert_tracking(self._db, url, label, interval_h)
        await self.send_notification(f"Tracking [{tid}] started: {label or url}")

    async def _handle_untrack(self, body: str) -> None:
        try:
            tid = int(body.split()[1])
        except (IndexError, ValueError):
            await self.send_notification("Usage: !untrack <id>")
            return
        row = self._db.execute(
            "SELECT url FROM trackings WHERE id=? AND cancelled_at IS NULL", (tid,)
        ).fetchone()
        if not row:
            await self.send_notification(f"Tracking {tid} not found.")
            return
        cancel_tracking(self._db, tid)
        await self.send_notification(f"Tracking [{tid}] stopped: {row['url']}")

    async def _handle_list(self) -> None:
        rows = fetch_active_trackings(self._db)
        pending = self._db.execute(
            "SELECT COUNT(*) FROM notifications WHERE status='pending' AND cancelled_at IS NULL"
        ).fetchone()[0]

        if not rows:
            lines = ["No active trackings."]
        else:
            lines = ["Trackings:"]
            for r in rows:
                interval_label = _format_interval(r["interval_h"])
                changed = r["last_changed_at"] or "never changed"
                label = r["label"] or r["url"]
                lines.append(f"  [{r['id']}] {interval_label}  {r['url']}  \"{label}\"  {changed}")

        lines.append(f"\nPending notifications: {pending}")
        await self.send_notification("\n".join(lines))

    async def deliver_pending(self) -> None:
        rows = fetch_pending(self._db)
        for row in rows:
            try:
                await self.send_notification(row["content"])
                mark_sent(self._db, row["id"])
                log.info("Delivered notification %d", row["id"])
            except Exception:
                log.exception("Failed to deliver notification %d", row["id"])

    def add_message_callback(self) -> None:
        async def on_message(room, event):
            if not isinstance(event, RoomMessageText):
                return
            if event.sender == self._cfg.username:
                return
            await self.handle_message(event.sender, event.body)

        self._client.add_event_callback(on_message, RoomMessageText)

    async def sync_forever(self) -> None:
        await self._client.sync_forever(timeout=30000)

    async def close(self) -> None:
        await self._client.close()
```

- [ ] **Step 4: Run to verify they pass**

```bash
.venv/bin/pytest notifier/tests/test_bot.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full notifier suite**

```bash
.venv/bin/pytest notifier/tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add notifier/notifier/bot.py notifier/tests/test_bot.py
git commit -m "feat(tracker): add !track, !untrack, !list bot commands"
```

---

## Task 6: Digestor Dockerfile

**Files:**
- Modify: `digestor/Dockerfile`

No tests — this is build infrastructure. Verify manually after editing.

- [ ] **Step 1: Update `digestor/Dockerfile`**

Replace the entire file:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
RUN playwright install chromium
RUN playwright install-deps chromium

COPY digestor ./digestor

EXPOSE 8080

CMD ["python", "-m", "digestor"]
```

- [ ] **Step 2: Verify the build works locally (optional, needs Docker/Podman)**

```bash
podman build -t digestor-test digestor/
```

Expected: builds successfully. Chromium install adds ~300 MB to image.

- [ ] **Step 3: Commit**

```bash
git add digestor/Dockerfile
git commit -m "feat(tracker): install Playwright Chromium in digestor image"
```

---

## Task 7: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/index.html`
- Modify: `DESING.md`

- [ ] **Step 1: Update README.md bot commands table**

Find the `## Matrix bot commands` section in `README.md`. Replace the existing table:

```markdown
## Matrix bot commands

Send these to the bot from your whitelisted account:

| Command | Effect |
|---|---|
| `!track <interval> <url> [for <description>]` | Start tracking a URL; interval: `hourly`, `daily`, `weekly`, `Nh`, `Nd`, `Nw` |
| `!untrack <id>` | Stop tracking a URL (get `<id>` from `!list`) |
| `!list` | List active trackings and count of pending notifications |
| `!cancel <id>` | Cancel a specific repeating notification |
| `!cancel-all` | Cancel all active repeating notifications |
| Any other message | Stored as a reply; digestor updates `context.md` on the next cycle |

The tracker always fetches via headless Chromium and only calls Claude when the rendered page text changes.
```

- [ ] **Step 2: Update docs/index.html commands section**

In `docs/index.html`, find the section that lists bot commands (look for `!cancel`). Add the three new commands to the table in the same style as the existing entries. Insert them before `!cancel`:

```html
<tr><td><code>!track &lt;interval&gt; &lt;url&gt; [for &lt;description&gt;]</code></td><td>Track a URL; intervals: <code>hourly</code>, <code>daily</code>, <code>weekly</code>, <code>Nh</code>, <code>Nd</code>, <code>Nw</code></td></tr>
<tr><td><code>!untrack &lt;id&gt;</code></td><td>Stop tracking a URL by its ID (shown in <code>!list</code>)</td></tr>
<tr><td><code>!list</code></td><td>List active trackings and pending notification count</td></tr>
```

Also add a note below the table (in the same style as the existing notes):

```html
<p>The tracker always renders pages with headless Chromium and only calls Claude when the text content changes.</p>
```

- [ ] **Step 3: Update DESING.md**

Open `DESING.md` and append a new section before the final `## Notifier` section, or at the end of the file, whichever flows better. Add:

```markdown
## Web tracker

Users can track arbitrary URLs from the Matrix bot. The `trackings` table in `digestor.db` is written by the notifier (bot commands) and read by the digestor (scheduled polling).

Bot commands:
- `!track <interval> <url> [for <description>]` — creates a tracking row; interval in `hourly`, `daily`, `weekly`, `Nh`, `Nd`, `Nw` format
- `!untrack <id>` — soft-deletes a tracking by setting `cancelled_at`
- `!list` — shows active trackings and pending notification count

The digestor polls all due trackings every 5 minutes. For each due row:
1. Fetches the URL with Playwright (headless Chromium, waits for `networkidle`)
2. Hashes the rendered `document.body.innerText` (SHA-256)
3. If hash unchanged: updates `last_checked_at` only
4. If no prior content (first fetch): stores baseline, queues a "Now tracking" notification, no LLM call
5. If content changed: calls Claude with the previous and current text (truncated to 4 000 chars each), queues a "Change detected" notification with the summary, logs token usage

Rendered content is stored truncated to 100 000 characters in `trackings.last_content_text`.
```

- [ ] **Step 4: Run both test suites to confirm nothing broke**

```bash
.venv/bin/pytest digestor/tests/ -v
.venv/bin/pytest notifier/tests/ -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/index.html DESING.md
git commit -m "docs: document !track, !untrack, !list commands and web tracker design"
```
