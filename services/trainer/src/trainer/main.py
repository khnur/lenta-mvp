"""lenta-trainer worker entrypoint.

On boot: seed + train v1 if the DB is empty. Then run forever:
  * APScheduler nightly (configurable; minutes for demos) retrain,
  * a job poller for manual /retrain and /reset triggers,
  * the live simulator thread.
No public port (Railway worker).
"""

from __future__ import annotations

import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler

from lenta_core.config import settings
from lenta_core.db import init_db, session_scope
from lenta_core.ingest import counts
from lenta_core.jobs import claim_job, finish_job, queued_jobs
from lenta_core.logging_conf import get_logger, setup_logging
from lenta_core.registry import active_version

from .retrain import run_reset, run_retrain, scheduled_retrain
from .simulator import LiveSimulator

log = get_logger("lenta.trainer")


def boot() -> None:
    init_db()
    with session_scope() as s:
        c = counts(s)
        has_model = active_version(s) is not None
    log.info("boot: %s, active_model=%s", c, has_model)

    if settings.seed_on_boot and c["users"] == 0:
        log.info("empty DB -> seeding + training v1")
        from lenta_core.bootstrap import seed_database

        seed_database(demo=False, reset=False)
        run_retrain(notes="boot-v1")
    elif not has_model and c["events"] > 0:
        log.info("events present, no active model -> training v1")
        run_retrain(notes="boot-v1")
    else:
        log.info("DB ready (active model v%s)", active_version_safe())


def active_version_safe() -> int | None:
    try:
        with session_scope() as s:
            return active_version(s)
    except Exception:
        return None


def poll_jobs() -> None:
    # claim job ids in one short transaction, then process each independently
    with session_scope() as s:
        claimed: list[tuple[int, str]] = []
        for job in queued_jobs(s):
            claim_job(s, job)
            claimed.append((job.id, job.type))
        s.commit()

    for jid, jtype in claimed:
        log.info("running job %d (%s)", jid, jtype)
        try:
            if jtype == "retrain":
                version, metrics = run_retrain(notes=f"manual job#{jid}")
                result = {
                    "version": version,
                    "ndcg_at_k": metrics.get("ndcg_at_k"),
                    "recall_at_k": metrics.get("recall_at_k"),
                }
                status = "done"
            elif jtype == "reset":
                version, _ = run_reset(demo=True)
                result, status = {"version": version}, "done"
            else:
                result, status = {"error": "unknown job type"}, "failed"
        except Exception as exc:  # noqa: BLE001
            log.exception("job %d failed: %s", jid, exc)
            result, status = {"error": str(exc)}, "failed"
        _finalize_job(jid, status, result)


def _finalize_job(jid: int, status: str, result: dict) -> None:
    from lenta_core.models import Job

    with session_scope() as s:
        job = s.get(Job, jid)
        if job is not None:
            finish_job(s, job, status=status, result=result)


def main() -> None:
    setup_logging()
    log.info("lenta-trainer starting")
    boot()

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_retrain,
        "interval",
        minutes=max(1, settings.retrain_interval_minutes),
        id="nightly_retrain",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("scheduler started (retrain every %d min)", settings.retrain_interval_minutes)

    sim = LiveSimulator()
    threading.Thread(target=sim.run, name="simulator", daemon=True).start()

    try:
        while True:
            try:
                poll_jobs()
            except Exception as exc:  # noqa: BLE001
                log.warning("job poller error: %s", exc)
            time.sleep(max(1, settings.trainer_poll_seconds))
    except (KeyboardInterrupt, SystemExit):
        log.info("trainer shutting down")
        sim.stop()
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
