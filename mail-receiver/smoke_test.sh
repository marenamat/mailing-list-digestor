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
