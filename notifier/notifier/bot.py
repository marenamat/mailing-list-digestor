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
