import logging
import signal
import sys
import time
from digestor.config import Config
from digestor.db import init_db
from digestor.watcher import start_watcher
from digestor.pipeline import process_eml
from digestor.scheduler import build_scheduler
from digestor.health import start_health_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("digestor")


def main() -> None:
    cfg = Config.from_env()
    log.info("Starting digestor — maildir=%s db=%s", cfg.maildir_path, cfg.db_path)

    db = init_db(cfg.db_path)

    start_health_server(cfg.db_path)

    scheduler = build_scheduler(cfg, db)
    scheduler.start()

    def on_new_mail(path):
        process_eml(path, cfg, db)

    observer = start_watcher(cfg.maildir_path, on_new_mail)
    log.info("Watching %s/new for mail", cfg.maildir_path)

    def shutdown(sig, frame):
        log.info("Shutting down")
        observer.stop()
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    observer.join()


if __name__ == "__main__":
    main()
