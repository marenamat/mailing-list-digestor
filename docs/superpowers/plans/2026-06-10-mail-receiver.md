# Mail Receiver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a Postfix container that accepts SMTP mail for one configured address and delivers it as Maildir files for the digestor to watch.

**Architecture:** Postfix running in an Alpine container, configured receive-only for a single virtual mailbox. An entrypoint script reads `SMTP_RECIPIENT` at startup, writes the virtual mailbox map, and starts Postfix. Mail lands in `/data/maildir/new/` — the exact path the digestor's inotify watcher expects. No relay, no outbound, no custom code.

**Tech Stack:** Alpine Linux 3.19, Postfix 3.7 (from Alpine packages), `postconf` for runtime configuration, `postmap` for map hashing

---

## Scope note

This is **Plan 1 of 4**. Subsequent plans cover:

- Plan 2: Digestor (Python) — Maildir watcher, email parsing, SQLite schema, ollama triage, Claude pipeline, digest generation, archive fetch, health endpoint
- Plan 3: Notifier (Python) — Matrix bot, notification delivery, reply handling, cancel commands
- Plan 4: Deployment — `compose.yaml`, network policy, integration smoke test

---

## How the delivery path works

```
virtual_mailbox_base = /data          (parent of the Maildir)
virtual_mailboxes map:
    digest@example.com   maildir/     (trailing slash = Maildir format)

→ Postfix delivers to /data/maildir/new/<message>
→ Digestor (Plan 2) watches /data/maildir/new/
```

The entrypoint derives `MAILDIR_PARENT=$(dirname $MAILDIR_PATH)` and `MAILDIR_LEAF=$(basename $MAILDIR_PATH)` from the `MAILDIR_PATH` env var, so any value works without changing the map template.

---

## File Map

```
mail-receiver/
  main.cf           static Postfix config; runtime values injected by entrypoint
  entrypoint.sh     reads env vars, runs postconf + postmap, starts postfix start-fg
  Dockerfile        FROM alpine:3.19, installs postfix, copies files
  smoke_test.sh     build image, run container, send email, assert file in new/
config/
  context.md.example    template for digestor evaluation context
  lists.yaml.example    template for WG→list-address mapping
.env.example            all env vars with placeholder values
```

No Rust workspace — the Cargo.toml mentioned in any earlier draft is not needed.

---

## Task 1: Postfix configuration and Dockerfile

**Files:**
- Create: `mail-receiver/main.cf`
- Create: `mail-receiver/Dockerfile`

- [ ] **Step 1: Create `mail-receiver/main.cf`**

```
# Runtime values injected by entrypoint.sh via `postconf -e`:
#   myhostname, virtual_mailbox_domains, virtual_mailbox_base,
#   virtual_uid_maps, virtual_gid_maps

# Disable local account delivery and outbound relay entirely
mydestination =
local_transport = error: local delivery disabled
relay_domains =
default_transport = error: outbound relay disabled

# Listen on all interfaces, IPv4 only (IPv6 not needed in the compose network)
inet_interfaces = all
inet_protocols = ipv4

# Virtual mailbox delivery (path and map populated at runtime)
virtual_transport = virtual
virtual_mailbox_maps = hash:/etc/postfix/virtual_mailboxes

# Log to stdout — requires Postfix 3.4+; Alpine 3.19 ships 3.7
maillog_file = /dev/stdout

# Minimal banner; no biff, no domain appending
smtpd_banner = $myhostname ESMTP
biff = no
append_dot_mydomain = no
```

- [ ] **Step 2: Create `mail-receiver/Dockerfile`**

```dockerfile
FROM alpine:3.19

RUN apk add --no-cache postfix

# UID 1000 owns the Maildir volume; shared with the digestor container
RUN adduser -D -u 1000 -h /data -s /bin/false mailuser

COPY main.cf /etc/postfix/main.cf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 25

ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 3: Verify the Dockerfile builds (entrypoint.sh does not exist yet — expect a COPY failure)**

```bash
podman build -t mail-receiver:local mail-receiver/ 2>&1 | tail -5
```

Expected: build fails at `COPY entrypoint.sh` because the file does not exist yet. This confirms the Dockerfile syntax is valid up to that point.

- [ ] **Step 4: Commit**

```bash
git add mail-receiver/main.cf mail-receiver/Dockerfile
git commit -m "feat(mail-receiver): Postfix config and Dockerfile skeleton"
```

---

## Task 2: Entrypoint script

**Files:**
- Create: `mail-receiver/entrypoint.sh`

- [ ] **Step 1: Create `mail-receiver/entrypoint.sh`**

```sh
#!/bin/sh
set -eu

# ── Validate required env vars ────────────────────────────────────────────────
: "${SMTP_RECIPIENT:?SMTP_RECIPIENT is required (e.g. digest@example.com)}"
MAILDIR_PATH="${MAILDIR_PATH:-/data/maildir}"
SMTP_HOSTNAME="${SMTP_HOSTNAME:-mail-receiver}"

# ── Derive config values ──────────────────────────────────────────────────────
DOMAIN="${SMTP_RECIPIENT#*@}"
LOCAL="${SMTP_RECIPIENT%@*}"
MAILDIR_PARENT="$(dirname "${MAILDIR_PATH}")"
MAILDIR_LEAF="$(basename "${MAILDIR_PATH}")"

# ── Apply runtime Postfix settings ────────────────────────────────────────────
postconf -e "myhostname=${SMTP_HOSTNAME}"
postconf -e "virtual_mailbox_domains=${DOMAIN}"
postconf -e "virtual_mailbox_base=${MAILDIR_PARENT}"
postconf -e "virtual_uid_maps=static:1000"
postconf -e "virtual_gid_maps=static:1000"

# ── Write and hash the virtual mailbox map ────────────────────────────────────
# Trailing slash on the path tells Postfix to use Maildir format.
echo "${SMTP_RECIPIENT} ${MAILDIR_LEAF}/" > /etc/postfix/virtual_mailboxes
postmap /etc/postfix/virtual_mailboxes

# ── Ensure Maildir structure exists with correct ownership ────────────────────
mkdir -p "${MAILDIR_PATH}/new" "${MAILDIR_PATH}/cur" "${MAILDIR_PATH}/tmp"
chown -R 1000:1000 "${MAILDIR_PATH}"

echo "mail-receiver: accepting mail for <${SMTP_RECIPIENT}> → ${MAILDIR_PATH}/new/"
exec postfix start-fg
```

- [ ] **Step 2: Build the image**

```bash
podman build -t mail-receiver:local mail-receiver/
```

Expected: successful build, no errors.

- [ ] **Step 3: Verify error on missing SMTP_RECIPIENT**

```bash
podman run --rm mail-receiver:local 2>&1
```

Expected output contains: `SMTP_RECIPIENT: parameter not set or null`  
Expected exit code: non-zero

- [ ] **Step 4: Verify clean startup with valid config**

```bash
podman run --rm -d --name mr-check \
    -e SMTP_RECIPIENT=test@example.com \
    -p 12525:25 \
    mail-receiver:local

sleep 2
podman logs mr-check 2>&1 | grep -E "accepting mail|master/daemon"
podman rm -f mr-check
```

Expected: log line `mail-receiver: accepting mail for <test@example.com>` and Postfix master startup messages.

- [ ] **Step 5: Commit**

```bash
git add mail-receiver/entrypoint.sh
git commit -m "feat(mail-receiver): entrypoint script wires env vars into Postfix"
```

---

## Task 3: Smoke test

**Files:**
- Create: `mail-receiver/smoke_test.sh`

This test builds the image, starts a container with a temporary Maildir volume, sends a real SMTP message using Python's stdlib `smtplib`, and asserts that a file appears in `new/`.

- [ ] **Step 1: Create `mail-receiver/smoke_test.sh`**

```bash
#!/bin/bash
set -euo pipefail

RECIPIENT="smoketest@mail-receiver.test"
TMPDIR="$(mktemp -d)"
trap 'podman rm -f mr-smoke 2>/dev/null; rm -rf "${TMPDIR}"' EXIT

echo "==> Building image"
podman build -q -t mail-receiver:local "$(dirname "$0")"

echo "==> Starting container"
podman run -d --name mr-smoke \
    -e SMTP_RECIPIENT="${RECIPIENT}" \
    -e MAILDIR_PATH=/data/maildir \
    -e SMTP_HOSTNAME=mail-receiver.test \
    -v "${TMPDIR}:/data" \
    -p 12525:25 \
    mail-receiver:local

echo "==> Waiting for Postfix to start"
for i in $(seq 1 10); do
    nc -z 127.0.0.1 12525 2>/dev/null && break
    sleep 0.5
done
nc -z 127.0.0.1 12525 || { echo "FAIL: Postfix did not bind"; exit 1; }

echo "==> Sending test message"
python3 - <<'EOF'
import smtplib, os, sys
recipient = os.environ.get("RECIPIENT", "smoketest@mail-receiver.test")
with smtplib.SMTP("127.0.0.1", 12525, timeout=10) as s:
    code, _ = s.ehlo("test.local")
    assert code == 250, f"EHLO failed: {code}"
    errs = s.sendmail(
        "sender@test.local",
        recipient,
        "Subject: Smoke test\r\n\r\nThis is a smoke test message.",
    )
    assert not errs, f"sendmail errors: {errs}"
print("SMTP accepted the message")
EOF

echo "==> Waiting for delivery"
sleep 1

echo "==> Checking Maildir"
COUNT=$(ls "${TMPDIR}/maildir/new/" 2>/dev/null | wc -l)
echo "    Messages in new/: ${COUNT}"
[ "${COUNT}" -eq 1 ] || { echo "FAIL: expected 1 message, got ${COUNT}"; exit 1; }

echo "==> Checking rejected recipient"
python3 - <<'EOF'
import smtplib
with smtplib.SMTP("127.0.0.1", 12525, timeout=10) as s:
    s.ehlo("test.local")
    code, _ = s.rcpt("nobody@other.domain")
    assert code == 550, f"Expected 550 for unknown recipient, got {code}"
print("Unknown recipient correctly rejected with 550")
EOF

echo ""
echo "PASS: mail-receiver smoke test"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x mail-receiver/smoke_test.sh
```

- [ ] **Step 3: Run the smoke test**

```bash
RECIPIENT=smoketest@mail-receiver.test mail-receiver/smoke_test.sh
```

Expected output (last lines):
```
    Messages in new/: 1
Unknown recipient correctly rejected with 550

PASS: mail-receiver smoke test
```

- [ ] **Step 4: Commit**

```bash
git add mail-receiver/smoke_test.sh
git commit -m "test(mail-receiver): smoke test — send SMTP, assert Maildir delivery"
```

---

## Task 4: Config example files

**Files:**
- Create: `config/context.md.example`
- Create: `config/lists.yaml.example`
- Create: `.env.example`

- [ ] **Step 1: Create `config/context.md.example`**

```markdown
# Digestor Context

This file tells the digestor what topics matter to you.
Mount it at /config/context.md in the digestor container.
Edit freely — the digestor re-reads it on each processing cycle.

## My interests

I am an IETF participant focused on transport protocols. I care about:

- Protocol design discussions in QUIC, TLS, HTTPBIS, WEBTRANS
- Calls for adoption and working group last calls in my WGs
- Interim meeting announcements
- Documents entering IETF last call

I am less interested in:

- Administrative threads unrelated to my working groups
- Off-topic or social content
```

- [ ] **Step 2: Create `config/lists.yaml.example`**

```yaml
# Maps mailing-list addresses to working group names.
# The digestor uses this to group emails in the daily digest.
# Copy to config/lists.yaml and adjust for your subscriptions.

working_groups:
  QUIC:
    - quic@ietf.org
    - quic-issues@ietf.org
  TLS:
    - tls@ietf.org
  HTTPBIS:
    - ietf-http-wg@w3.org
    - httpbis@ietf.org
  WEBTRANS:
    - webtransport@ietf.org
  General:
    - ietf-announce@ietf.org
    - ietf@ietf.org
```

- [ ] **Step 3: Create `.env.example`**

```bash
# ── Mail receiver ─────────────────────────────────────────────────────────────
SMTP_RECIPIENT=digest@yourdomain.example
SMTP_HOSTNAME=mail.yourdomain.example
MAILDIR_PATH=/data/maildir

# ── Digestor ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_MODEL=gemma3:4b
DIGEST_TIME=07:00

# ── Notifier ──────────────────────────────────────────────────────────────────
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USERNAME=@digestbot:example.com
MATRIX_PASSWORD=changeme
MATRIX_WHITELIST=@you:example.com
```

- [ ] **Step 4: Commit**

```bash
git add config/ .env.example
git commit -m "docs: config example files for all services"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Mailserver for one address, never sends | `main.cf`: `default_transport = error: outbound relay disabled`; recipient filter via virtual map |
| Communicates one-way with digestor | Maildir volume (wired in Plan 4); digestor reads, mail-receiver writes |
| Runs separated from other services | Separate container; Plan 4 network policy restricts egress |
| Everything committed to git | Each task ends with a commit |
| Everything logged | `maillog_file = /dev/stdout`; entrypoint echoes startup line |
| Deployment documented | `.env.example`, Dockerfile, Plan 4 |
| Config files (context.md, lists.yaml) | Task 4 (examples committed; digestor reads them in Plan 2) |

**No Rust code anywhere.** The workspace `Cargo.toml` is not needed. If it was created during an earlier session, delete it:

```bash
# Only if Cargo.toml and mail-receiver/src/ exist from a previous attempt:
git rm -r Cargo.toml mail-receiver/src/ mail-receiver/tests/ 2>/dev/null || true
git commit -m "chore: remove Rust skeleton, replaced by Postfix config"
```
