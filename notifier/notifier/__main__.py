import asyncio
import logging

from notifier.config import Config
from notifier.db import get_db
from notifier.bot import MatrixBot
from notifier.scheduler import build_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("notifier")


async def main() -> None:
    cfg = Config.from_env()
    log.info("Starting notifier — db=%s homeserver=%s", cfg.db_path, cfg.homeserver)

    db = get_db(cfg.db_path)
    bot = MatrixBot(cfg, db)

    await bot.login()
    bot.add_message_callback()

    scheduler = build_scheduler(cfg, bot)
    scheduler.start()
    log.info("Polling for notifications every %ds", cfg.poll_interval_s)

    try:
        await bot.sync_forever()
    finally:
        scheduler.shutdown(wait=False)
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
