# Grinder

The tool will directly receive various mailing-lists.
It should automatically process the mailbox and notify about important events.

## General rules

Commit everything into Git.

Document everything, both for developers and for users, most notably deployment needs.

Create automatic tests for every feature if possible.

Everything shall be logged.

Configuration files live in `config/`:
- `context.md`  — free-form markdown describing the user's interests and relevance criteria
- `lists.yaml`  — maps mailing-list addresses to working group names; used to split digests

## Mail receiver

There shall be a mailserver configured to receive e-mails for one single
address and never send anything. This address will be subscribed to various
public mailing-lists and is expected to read and process all that data.

This service must run separated from others and communicate only one-way with the digestor.

### Implementation

- Software: **Postfix 3.7** (Alpine 3.19 package — no custom SMTP code)
- Accepts mail only for the configured recipient via virtual mailbox map; rejects all other domains at SMTP level (554)
- Delivers each message into `/data/maildir/new/` (Maildir format, atomic `tmp/` → `new/` rename)
- No outbound network access; `default_transport = error` and `relay_domains =` disable all relay
- Base image: `alpine:3.19`; UID 1000 (`mailuser`) shared with digestor container
- Logs to stdout via `maillog_file = /dev/stdout` (Postfix 3.4+ feature)
- Configuration via environment variables: `SMTP_RECIPIENT`, `SMTP_HOSTNAME`, `MAILDIR_PATH`

## Digestor

There shall be a service monitoring new e-mail delivery. This service shall
have access to the internet only for HTTP(S)-based requests and nothing else.

There shall be a triage phase running a small local model via ollama first.
This phase classifies the incoming messages whether they are urgent or not.
This model shall be biased a little towards urgency.

For urgent messages, a claude-LLM-based classifier shall run, deciding whether
that mail is indeed urgent, and if so, notify about them immediately.

For all other messages, once daily, a claude-LLM-based classifier shall run,
creating a digest.

Monitor the LLM token usage and append the usage report to the digest.

There shall be some database keeping the e-mails, digests and reports. It may
be a folder structure, as it will mostly be write once and not return back too often.

There shall be a full-text index of the e-mails, digests and reports, to allow
for faster searching.

If an e-mail is a reply (In-Reply-To, References) and the referenced mail is not available locally,
it shall be downloaded from public archives and considered received. For IETF lists this means the
IETF mailarchive (`https://mailarchive.ietf.org/arch/`); non-IETF archive support is a future
extension.

Split the digests by working groups. If the digestor finds out that nothing happened in some list,
it should be mentioned as "nothing here". If the digestor finds out that there is another mailing-list
worth being interested in, it shall recommend to subscribe there.

### Implementation

- Language: **Python 3.12+**
- Key libraries:
  - `watchdog` — inotify-based watch on `/data/maildir/new/`; triggers processing on each new `.eml` file
  - `email` (stdlib) — RFC 2822 / MIME parsing
  - `ollama` Python client — local triage model; default `gemma3:4b`, configurable via `OLLAMA_MODEL`
  - `anthropic` Python SDK — Claude classification and digest generation
  - `apscheduler` — daily digest cron job (default 07:00 local, configurable via `DIGEST_TIME`)
  - `httpx` — archive fetching
  - `sqlite3` (stdlib) — storage and FTS5 full-text index
- **SQLite schema** at `/data/digestor.db`:
  - `emails(id, message_id, date, from_addr, subject, list_addr, working_group, body_text, urgency_local, urgency_claude, processed_at, source)`
  - `digests(id, date, working_group, content, token_input, token_output)`
  - `token_usage(id, ts, model, input_tokens, output_tokens, purpose)`
  - `notifications(id, type, content, status, repeat_interval_h, next_fire_at, cancelled_at)`
  - `replies(id, ts, matrix_sender, content, applied)`
  - FTS5 virtual table over `emails(subject, body_text)` and `digests(content)`
- **Ollama triage**: system prompt biases toward urgency; output is `urgent | not_urgent`
- **Claude classification**: runs only when ollama says `urgent`; decides final urgency and records rationale
- **Daily digest**: groups emails by `working_group` from `lists.yaml`; calls Claude with the batch; appends token usage summary to the digest
- **Context update**: when a Matrix reply triggers a context update, digestor calls Claude with the old and new `context.md` to produce a summary, which is queued as a one-off notification
- **Health endpoint**: exposes `GET /healthz` on `localhost:8080` returning SQLite status and last-processed timestamp

### Specific message types

Calls for presentations are always urgent. Also, setup a repeated notification:
- for IETF and everything else with deadline shorter than 2 weeks, every day until manually cancelled
- otherwise, once a week until manually cancelled

Cancellation is done by sending `!cancel <notification_id>` to the Matrix bot. `!cancel-all` cancels all active repeating notifications.

Messages about IETF interim meetings are always regular, but they also shall set several notifications:
- one week ahead
- that day morning
- half an hour ahead

Documents in last call are never irrelevant.

IETF Documents in working group adoption call are never irrelevant.

Confirmations of mailing-list subscriptions are always urgent.

### Digestor context

There shall be a context in which the messages are evaluated, to determine their relevance,
as a markdown file somewhere in the configuration.

## Deployment

Orchestrated with Podman Compose (`compose.yaml` in Docker Compose v3 format; compatible with `podman-compose`).

Services:
- `mail-receiver`  — Rust binary; exposes port 25 (SMTP); no egress
- `digestor`       — Python; egress to HTTPS only (Claude API, IETF archives, ollama service); no ingress
- `notifier`       — Python; egress to Matrix homeserver HTTPS only; no ingress
- `ollama`         — official `ollama/ollama` image; internal network only; GPU passthrough optional

Volumes:
- `maildir`        — `/data/maildir`  shared between mail-receiver (write) and digestor (read)
- `db`             — `/data`          shared between digestor (write) and notifier (read/write)
- `config`         — `/config`        read-only mount for all services
- `ollama-models`  — ollama model cache

Networks:
- `internal`       — digestor, notifier, ollama (no external access by policy)
- `smtp-ingress`   — mail-receiver only (exposes port 25)

Secrets and credentials go in a `.env` file (not committed to git); an `.env.example` is committed and documents all required variables.

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

## Notifier

The notifier is a Matrix user. The server, username and password shall be
configured. There shall be a configured whitelist of users allowed to communicate with the bot.
Every attempt to communicate from a non-whitelisted account shall be logged.

The whitelisted user gets digests and notifications.

The whitelisted user may reply to the messages from the bot. These should be processed and 
the digestor context updated accordingly. The changes shall be presented back in a concise form.

This service must run separated from others and communicate with the digestor only in a form of
a single messaging channel.

### Implementation

- Language: **Python 3.12+**
- Key libraries:
  - `matrix-nio` (async) — Matrix client
  - `sqlite3` (stdlib) — shared database with digestor at `/data/digestor.db`
  - `apscheduler` — drives the notification poll loop and repeat-firing schedule
- **Outbound**: polls `notifications` where `status='pending' AND next_fire_at <= now()`; sends to the whitelisted user; marks `status='sent'`
- **Inbound**: receives Matrix messages from whitelisted user; inserts into `replies` table; digestor picks them up on its next cycle
- **Cancel command**: `!cancel <notification_id>` sets `notifications.cancelled_at`; `!cancel-all` cancels all active repeating notifications
- **Unknown sender**: logs Matrix user ID and timestamp; does not reply
- All services write structured logs to stdout, collected by Podman's log driver
- Configuration via environment variables: `MATRIX_HOMESERVER`, `MATRIX_USERNAME`, `MATRIX_PASSWORD`, `MATRIX_WHITELIST`
