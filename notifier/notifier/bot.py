import asyncio
import logging
import sqlite3

from nio import AsyncClient, RoomMessageText

from notifier.config import Config
from notifier.db import (
    cancel_all,
    cancel_notif,
    fetch_pending,
    insert_reply,
    mark_sent,
)

log = logging.getLogger(__name__)


class MatrixBot:
    def __init__(self, cfg: Config, db: sqlite3.Connection):
        self._cfg = cfg
        self._db = db
        self._client = AsyncClient(cfg.homeserver, cfg.username)

    def is_allowed(self, sender: str) -> bool:
        return sender in self._cfg.whitelist

    async def login(self) -> None:
        resp = await self._client.login(self._cfg.password)
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
        else:
            insert_reply(self._db, sender, body)
            log.info("Reply from %s stored", sender)

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
