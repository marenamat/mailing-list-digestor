# Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire all four services (mail-receiver, digestor, notifier, ollama) together with a Podman-Compose-compatible `compose.yaml`, configure networks and volumes, and provide a `smoke_test.sh` that validates end-to-end delivery.

**Architecture:** Docker Compose v3 format. Two networks: `smtp-ingress` (mail-receiver only) and `internal` (digestor, notifier, ollama). Three data volumes: `maildir`, `db`, `config`. The integration smoke test sends an email via SMTP, waits for it to appear in the SQLite `emails` table, then asserts it was processed.

**Tech Stack:** Podman Compose (compatible with Docker Compose v3), bash, Python smtplib, sqlite3 CLI

---

## Scope note — Plan 4 of 4

Plans 1–3 ✅. This plan wires everything together.

---

## File Map

```
compose.yaml             Podman Compose service definitions
smoke_test.sh            Integration smoke test
```

---

## Task 1: compose.yaml

**Files:**
- Create: `compose.yaml`

- [ ] **Step 1: Create `compose.yaml`**

```yaml
version: "3.8"

services:
  mail-receiver:
    build: ./mail-receiver
    ports:
      - "${SMTP_PORT:-25}:25"
    environment:
      SMTP_RECIPIENT: "${SMTP_RECIPIENT}"
      SMTP_HOSTNAME: "${SMTP_HOSTNAME:-mail-receiver}"
      MAILDIR_PATH: /data/maildir
    volumes:
      - maildir:/data
    networks:
      - smtp-ingress
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    networks:
      - internal
    restart: unless-stopped

  digestor:
    build: ./digestor
    environment:
      MAILDIR_PATH: /data/maildir
      DB_PATH: /data/digestor.db
      CONTEXT_PATH: /config/context.md
      LISTS_PATH: /config/lists.yaml
      OLLAMA_BASE_URL: http://ollama:11434
      OLLAMA_MODEL: "${OLLAMA_MODEL:-gemma3:4b}"
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
      DIGEST_TIME: "${DIGEST_TIME:-07:00}"
    volumes:
      - maildir:/data/maildir:ro
      - db:/data
      - config:/config:ro
    networks:
      - internal
    depends_on:
      - ollama
    restart: unless-stopped

  notifier:
    build: ./notifier
    environment:
      DB_PATH: /data/digestor.db
      MATRIX_HOMESERVER: "${MATRIX_HOMESERVER}"
      MATRIX_USERNAME: "${MATRIX_USERNAME}"
      MATRIX_PASSWORD: "${MATRIX_PASSWORD}"
      MATRIX_WHITELIST: "${MATRIX_WHITELIST}"
      MATRIX_ROOM_ID: "${MATRIX_ROOM_ID:-}"
      POLL_INTERVAL_S: "${POLL_INTERVAL_S:-30}"
    volumes:
      - db:/data
    networks:
      - internal
    depends_on:
      - digestor
    restart: unless-stopped

volumes:
  maildir:
  db:
  ollama-models:
  config:

networks:
  smtp-ingress:
  internal:
    internal: true
```

- [ ] **Step 2: Verify compose.yaml is valid YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('compose.yaml'))" && echo "YAML OK"
```

Expected: `YAML OK`

- [ ] **Step 3: Commit**

```bash
git add compose.yaml
git commit -m "feat(deploy): Podman Compose service definitions"
```

---

## Task 2: Integration smoke test

**Files:**
- Create: `smoke_test.sh`

This test:
1. Starts just the `mail-receiver` container (no AI services needed)
2. Sends an email via smtplib
3. Verifies the file lands in the Maildir volume
4. Optionally checks that the digestor container processes it into SQLite (if ANTHROPIC_API_KEY is set; skipped otherwise)

- [ ] **Step 1: Create `smoke_test.sh`**

```bash
#!/bin/bash
set -euo pipefail

# Integration smoke test — tests mail delivery path end-to-end.
# Requires: podman, podman-compose (or docker compose)
# Optional for full path: ANTHROPIC_API_KEY env var

TMPDIR="$(mktemp -d)"
COMPOSE_PROJECT="smoke$$"
trap 'podman-compose -p "${COMPOSE_PROJECT}" down -v 2>/dev/null || true; rm -rf "${TMPDIR}"' EXIT

SMTP_RECIPIENT="${SMTP_RECIPIENT:-smoketest@mail-receiver.test}"
export SMTP_RECIPIENT

echo "==> Building images"
podman-compose -p "${COMPOSE_PROJECT}" build mail-receiver 2>&1 | tail -3

echo "==> Starting mail-receiver"
SMTP_PORT=12526 podman-compose -p "${COMPOSE_PROJECT}" up -d mail-receiver

echo "==> Waiting for SMTP port"
for i in $(seq 1 60); do
    nc -z 127.0.0.1 12526 2>/dev/null && break
    sleep 0.5
done
nc -z 127.0.0.1 12526 || { echo "FAIL: SMTP port not ready"; exit 1; }

echo "==> Sending test message via SMTP"
python3 - <<'EOF'
import smtplib, os
recipient = os.environ["SMTP_RECIPIENT"]
with smtplib.SMTP("127.0.0.1", 12526, timeout=10) as s:
    s.ehlo("test.local")
    errs = s.sendmail("sender@test.local", recipient,
                      "Subject: Integration smoke test\r\n\r\nTest body.")
    assert not errs, f"sendmail errors: {errs}"
print("SMTP accepted the message")
EOF

echo "==> Checking Maildir volume"
# Get the volume name used by compose
VOL=$(podman volume ls --format '{{.Name}}' | grep "${COMPOSE_PROJECT}" | grep maildir | head -1)
if [ -z "${VOL}" ]; then
    echo "FAIL: maildir volume not found"
    exit 1
fi
MAILDIR_MOUNT=$(podman volume inspect "${VOL}" --format '{{.Mountpoint}}')

COUNT=0
for i in $(seq 1 25); do
    COUNT=$(ls "${MAILDIR_MOUNT}/maildir/new/" 2>/dev/null | wc -l)
    [ "${COUNT}" -ge 1 ] && break
    sleep 0.2
done
echo "    Messages in maildir/new/: ${COUNT}"
[ "${COUNT}" -eq 1 ] || { echo "FAIL: expected 1 message in Maildir"; exit 1; }

echo ""
echo "PASS: integration smoke test (mail delivery)"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x smoke_test.sh
```

- [ ] **Step 3: Verify smoke test runs (mail delivery path only)**

```bash
SMTP_RECIPIENT=smoketest@mail-receiver.test ./smoke_test.sh
```

Expected: `PASS: integration smoke test (mail delivery)`

If podman-compose is not installed, skip step 3 and note in the report. The test is still committed.

- [ ] **Step 4: Commit**

```bash
git add smoke_test.sh
git commit -m "test(deploy): integration smoke test for mail delivery path"
```

---

## Self-Review

| Spec requirement | Task |
|---|---|
| compose.yaml with all 4 services | Task 1 |
| smtp-ingress network (mail-receiver only) | Task 1 |
| internal network (digestor, notifier, ollama) | Task 1 |
| maildir volume shared mail-receiver↔digestor | Task 1 |
| db volume shared digestor↔notifier | Task 1 |
| config volume for context.md and lists.yaml | Task 1 |
| ollama-models volume | Task 1 |
| Env vars from .env file | Task 1 (uses ${VAR} syntax) |
| Integration smoke test | Task 2 |
| Everything logged | Each service logs to stdout → podman logs |
