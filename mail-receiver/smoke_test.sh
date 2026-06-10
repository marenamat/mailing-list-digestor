#!/bin/bash
set -euo pipefail

RECIPIENT="smoketest@mail-receiver.test"
export RECIPIENT
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
for i in $(seq 1 60); do
    nc -z 127.0.0.1 12525 2>/dev/null && break
    sleep 0.5
done
nc -z 127.0.0.1 12525 || { echo "FAIL: Postfix did not bind"; exit 1; }

echo "==> Sending test message"
python3 - <<'EOF'
import smtplib, os
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
COUNT=0
for i in $(seq 1 25); do
    COUNT=$(ls "${TMPDIR}/maildir/new/" 2>/dev/null | wc -l)
    [ "${COUNT}" -ge 1 ] && break
    sleep 0.2
done
echo "    Messages in new/: ${COUNT}"
[ "${COUNT}" -eq 1 ] || { echo "FAIL: expected 1 message, got ${COUNT}"; exit 1; }

echo "==> Checking rejected recipient"
python3 - <<'EOF'
import smtplib
with smtplib.SMTP("127.0.0.1", 12525, timeout=10) as s:
    s.ehlo("test.local")
    s.mail("sender@test.local")
    code, _ = s.rcpt("nobody@other.domain")
    # Postfix returns 554 (relay access denied) for an unknown domain
    assert code == 554, f"Expected 554 for unknown recipient domain, got {code}"
print("Unknown recipient domain correctly rejected with 554")
EOF

echo ""
echo "PASS: mail-receiver smoke test"
