# Web Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add URL tracking to the mailing-list digestor: users configure tracked URLs via Matrix bot commands; the digestor fetches rendered page content via headless Chromium, detects changes by hash, and calls Claude to summarise what changed.

**Architecture:** Bot commands (`!track`, `!untrack`, `!list`) write to a `trackings` table in the shared SQLite database. The digestor's scheduler polls due trackings every 5 minutes, fetches via Playwright, compares SHA-256 hashes, and on change calls Claude for a diff summary which is queued as a notification. The notifier delivers it to Matrix as normal.

**Tech Stack:** `playwright` (Python, sync API, bundled Chromium), `hashlib` (stdlib), Claude (`claude-sonnet-4-6`), APScheduler (already present), SQLite (already present).

---

## Data model

New table added to `digestor/digestor/db.py` SCHEMA and mirrored in `notifier/notifier/db.py` `_TEST_SCHEMA`:

```sql
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
```

- `last_content_hash` — SHA-256 hex of the full rendered text; drives change detection.
- `last_content_text` — rendered text truncated to 100 KB; used as the "before" snapshot for the LLM diff prompt. NULL on first fetch (baseline run, no LLM call).
- `interval_h` — polling interval in fractional hours (e.g. 0.5, 6.0, 24.0).

## Bot commands

Handled in `notifier/notifier/bot.py`. All require the sender to be in the whitelist.

### `!track <interval> <url> [for <description>]`

Inserts a row into `trackings`. Bot replies with the assigned ID.

Interval formats accepted:
- `hourly` → 1.0
- `daily` → 24.0
- `weekly` → 168.0
- `Nh` → N hours (e.g. `6h`)
- `Nd` → N × 24 hours (e.g. `2d`)
- `Nw` → N × 168 hours (e.g. `1w`)

The `for <description>` suffix is optional; if omitted the label is the URL.

### `!untrack <id>`

Sets `cancelled_at = now()` on the given tracking. Bot confirms with the URL.

### `!list`

Returns active trackings and a pending-notification count:

```
Trackings:
  [1] daily   https://example.com/venue  "meeting venue location"  changed: 2026-06-12 14:30
  [2] 6h      https://ietf.org/meeting/  never changed

Pending notifications: 2
```

## Crawler module

**File:** `digestor/digestor/crawler.py`

```python
def fetch_rendered_text(url: str) -> str:
```

- Launches Chromium headless via `playwright.sync_api.sync_playwright()`.
- Navigates to `url`, waits for `networkidle`.
- Extracts `document.body.innerText`.
- Returns the string. Raises on navigation error.
- Fresh browser context per call — no session state persists between fetches.

Test mock target: `digestor.crawler.sync_playwright`.

**Dockerfile additions** (after `pip install`):

```dockerfile
RUN playwright install chromium
RUN playwright install-deps chromium
```

**`digestor/pyproject.toml`** gains `"playwright>=1.44"` in dependencies.

## Tracker module

**File:** `digestor/digestor/tracker.py`

```python
def check_tracking(row: sqlite3.Row, cfg: Config, db: sqlite3.Connection) -> None:
```

Flow:

1. `text = fetch_rendered_text(row["url"])`
2. `new_hash = hashlib.sha256(text.encode()).hexdigest()`
3. If `new_hash == row["last_content_hash"]`: update `last_checked_at`, return.
4. If `row["last_content_text"] is None` (first fetch): store baseline, send one-off "Now tracking `<url>`" notification, return.
5. Otherwise: call Claude:

```
You are monitoring a webpage for changes.
Tracking goal: {label}
URL: {url}

PREVIOUS CONTENT (truncated):
{last_content_text[:4000]}

CURRENT CONTENT (truncated):
{new_text[:4000]}

Summarise what changed in 2–3 sentences, focusing on what is relevant to the tracking goal.
```

6. Insert `notifications(type='tracking', content=summary, status='pending')`.
7. Log token usage to `token_usage` with `purpose='tracking:<url>'`.
8. Update `last_content_hash`, `last_content_text` (truncated to 100 000 chars), `last_checked_at`, `last_changed_at`.

Per-row errors are caught and logged; they do not abort the scheduler tick.

Test mock targets: `digestor.tracker.fetch_rendered_text`, `digestor.tracker.anthropic`.

## Scheduler integration

In `digestor/digestor/scheduler.py`, a second job is added to `build_scheduler`:

- Trigger: `interval`, every 5 minutes.
- Query due trackings:

```sql
SELECT * FROM trackings
WHERE cancelled_at IS NULL
  AND (last_checked_at IS NULL
       OR datetime(last_checked_at, '+' || CAST(ROUND(interval_h * 60) AS INTEGER) || ' minutes') <= datetime('now'))
```

- Calls `check_tracking(row, cfg, db)` for each result.

## Documentation updates

- **`README.md`** — extend the "Matrix bot commands" table with `!track`, `!untrack`, `!list`.
- **`docs/index.html`** — extend the commands cheatsheet section with the same three commands and a brief note that the tracker always uses a headless browser and only invokes Claude on content changes.
- **`DESING.md`** — add `## Web tracker` section describing the `trackings` table, the fetch→hash→LLM flow, and the component split (notifier parses commands, digestor executes).
