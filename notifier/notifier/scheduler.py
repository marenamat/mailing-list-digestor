import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from notifier.config import Config
from notifier.bot import MatrixBot

log = logging.getLogger(__name__)


def _deliver(bot: MatrixBot) -> None:
    try:
        asyncio.get_event_loop().run_until_complete(bot.deliver_pending())
    except Exception:
        log.exception("Error delivering pending notifications")


def build_scheduler(cfg: Config, bot: MatrixBot) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _deliver,
        "interval",
        seconds=cfg.poll_interval_s,
        args=[bot],
        id="deliver_pending",
    )
    return scheduler
