#!/bin/bash
set -euo pipefail

# Integration smoke test — tests mail delivery path end-to-end.
# Requires: podman, podman-compose (or docker compose)

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
