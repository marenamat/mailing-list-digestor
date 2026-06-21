# Grinder

A self-hosted tool that receives IETF mailing-list emails via SMTP, triages them with a local LLM, classifies urgent messages with Claude, and sends a daily digest plus immediate alerts to a Matrix room.

## How it works

```
SMTP → Postfix → Maildir → digestor → SQLite → notifier → Matrix
                                  ↓
                              ollama (local triage)
                              Claude API (classification + digest)
```

1. **mail-receiver** — Postfix container accepts mail for one address, writes Maildir files
2. **digestor** — watches Maildir with inotify, triages each email (ollama → Claude), stores in SQLite
3. **notifier** — Matrix bot delivers urgent alerts and daily digests, accepts `!cancel` commands
4. **ollama** — runs a small local model (`gemma3:4b` by default) for fast first-pass triage

## Requirements

- Podman 5+ with rootless support and cgroups v2 mounted
- podman-compose
- An Anthropic API key
- A Matrix account for the bot (and a room to send to)
- A domain with an MX record pointing at your host, or port-forwarding on port 25

## Quick start

### 1. Clone and copy config templates

```bash
git clone <repo-url>
cd mailing-list-digestor
cp .env.example .env
cp config/context.md.example config/context.md
cp config/lists.yaml.example config/lists.yaml
```

### 2. Edit `.env`

```bash
# Minimum required fields:
SMTP_RECIPIENT=digest@yourdomain.example   # the address you'll subscribe lists to
SMTP_HOSTNAME=mail.yourdomain.example      # your MX hostname
ANTHROPIC_API_KEY=sk-ant-...
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USERNAME=@digestbot:example.com
MATRIX_PASSWORD=your-bot-password
MATRIX_WHITELIST=@you:example.com          # your own Matrix ID
MATRIX_ROOM_ID=!roomid:example.com         # the room the bot will post to
```

### 3. Edit `config/context.md`

Describe what you care about — the digestor and Claude use this to decide what is urgent and to write relevant digests. Plain markdown, free-form. The file is re-read on every processing cycle so you can update it without restarting.

### 4. Edit `config/lists.yaml`

Map each mailing-list address to a working group name. Digests are grouped by working group.

```yaml
working_groups:
  QUIC:
    - quic@ietf.org
  TLS:
    - tls@ietf.org
```

### 5. Build and start

```bash
podman-compose up -d
```

On first start, the `ollama` container pulls the model (several hundred MB — takes a few minutes).

### 6. Subscribe your lists

Subscribe `$SMTP_RECIPIENT` to the mailing lists you want. Confirmation emails arrive as Matrix notifications.

## Configuration reference

All configuration is via environment variables in `.env`.

| Variable | Default | Description |
|---|---|---|
| `SMTP_RECIPIENT` | — | Email address to accept mail for |
| `SMTP_HOSTNAME` | `mail-receiver` | Hostname in Postfix banner |
| `SMTP_PORT` | `25` | Host port mapped to container port 25 |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OLLAMA_MODEL` | `gemma3:4b` | Model for local triage |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama API base URL |
| `DIGEST_TIME` | `07:00` | Daily digest time (HH:MM, container local time) |
| `MATRIX_HOMESERVER` | — | Matrix homeserver URL |
| `MATRIX_USERNAME` | — | Bot Matrix ID (`@bot:server`) |
| `MATRIX_PASSWORD` | — | Bot password |
| `MATRIX_WHITELIST` | — | Comma-separated Matrix IDs allowed to interact with the bot |
| `MATRIX_ROOM_ID` | — | Room the bot posts to |
| `POLL_INTERVAL_S` | `30` | How often the notifier checks for pending notifications |

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

## Health check

The digestor exposes `GET /healthz` on port 8080 (container-internal):

```bash
podman exec $(podman ps -qf name=digestor) curl -s http://localhost:8080/healthz
```

Returns `{"status": "ok", "db": "ok"}`.

## Logs

```bash
podman-compose logs -f            # all services
podman-compose logs -f digestor   # just the digestor
```

## Running as a systemd service

A user unit is included:

```bash
cp ~/.config/systemd/user/mailing-list-digestor.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mailing-list-digestor
journalctl --user -u mailing-list-digestor -f
```

To start automatically at boot (without a login session):

```bash
loginctl enable-linger
```

## Smoke test

Tests the mail delivery path (no AI credentials needed):

```bash
SMTP_RECIPIENT=smoketest@mail-receiver.test ./smoke_test.sh
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md).

The Python packages have their own test suites:

```bash
.venv/bin/pytest digestor/tests/ -v
.venv/bin/pytest notifier/tests/ -v
```

## Architecture

See [DESING.md](DESING.md) for the full design including implementation details, SQLite schema, network topology, and data flow.
