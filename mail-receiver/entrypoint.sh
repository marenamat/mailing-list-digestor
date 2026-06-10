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
