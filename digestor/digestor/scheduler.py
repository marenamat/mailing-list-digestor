import logging
import sqlite3
from datetime import datetime, timezone, date
from apscheduler.schedulers.background import BackgroundScheduler
from digestor.config import Config
from digestor.digest import generate_digest

log = logging.getLogger(__name__)


def _run_daily_digest(cfg: Config, db: sqlite3.Connection) -> None:
    today = date.today().isoformat()
    log.info("Running daily digest for %s", today)
    lists = cfg.load_lists()
    context = cfg.load_context()

    wgs = set(lists.keys()) | {"General"}
    for wg in wgs:
        wg_lists = lists.get(wg, [])
        if wg_lists:
            placeholders = ",".join("?" * len(wg_lists))
            rows = db.execute(
                f"SELECT * FROM emails WHERE DATE(date)=? AND list_addr IN ({placeholders}) AND urgency_claude != 'urgent'",
                [today] + wg_lists,
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM emails WHERE DATE(date)=? AND working_group=? AND urgency_claude != 'urgent'",
                (today, wg),
            ).fetchall()

        emails = [dict(r) for r in rows]
        content, in_tok, out_tok = generate_digest(emails, wg, context, cfg.anthropic_api_key)

        db.execute(
            "INSERT INTO digests(date, working_group, content, token_input, token_output) VALUES(?,?,?,?,?)",
            (today, wg, content, in_tok, out_tok),
        )
        db.execute(
            "INSERT INTO token_usage(model, input_tokens, output_tokens, purpose) VALUES(?,?,?,?)",
            ("claude-sonnet-4-6", in_tok, out_tok, f"digest:{wg}"),
        )
        db.execute(
            "INSERT INTO notifications(type, content, status, next_fire_at) VALUES(?,?,?,?)",
            ("digest", f"**Daily digest — {wg}**\n\n{content}", "pending",
             datetime.now(timezone.utc).isoformat()),
        )
    db.commit()
    log.info("Daily digest complete")


def build_scheduler(cfg: Config, db: sqlite3.Connection) -> BackgroundScheduler:
    hour, minute = (int(x) for x in cfg.digest_time.split(":"))
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _run_daily_digest,
        "cron",
        hour=hour,
        minute=minute,
        args=[cfg, db],
        id="daily_digest",
    )
    return scheduler
