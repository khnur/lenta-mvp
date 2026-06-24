"""Retrain + reset orchestration with pipeline-stage tracking.

Each retrain records four pipeline stages (ingest -> feature_update -> retrain ->
deploy) so the dashboard's pipeline panel shows live progress. The api hot-reloads
the new active model on its own via the registry poller.
"""

from __future__ import annotations

from lenta_core.bootstrap import seed_database
from lenta_core.db import get_session
from lenta_core.ingest import counts
from lenta_core.logging_conf import get_logger
from lenta_core.ml.train import train_bundle
from lenta_core.pipeline import finish_stage, start_stage
from lenta_core.registry import next_version, save_model_version

log = get_logger("lenta.trainer.retrain")


def run_retrain(notes: str = "scheduled") -> tuple[int, dict]:
    """Train the next version on current events and activate it."""
    s = get_session()
    try:
        before = counts(s)["events"]

        ing = start_stage(s, "ingest", {"events_total": before})
        finish_stage(s, ing, detail={"events_total": before})

        fu = start_stage(s, "feature_update", {})
        finish_stage(s, fu, detail={"events_total": before})

        version = next_version(s)
        rt = start_stage(s, "retrain", {"version": version})
        bundle, metrics, rows = train_bundle(s, version=version)
        finish_stage(
            s, rt,
            detail={
                "version": version,
                "recall_at_k": metrics.get("recall_at_k"),
                "ndcg_at_k": metrics.get("ndcg_at_k"),
                "train_rows": rows,
            },
        )

        dp = start_stage(s, "deploy", {"version": version})
        save_model_version(s, bundle, metrics=metrics, train_rows=rows, set_active=True, notes=notes)
        s.commit()
        finish_stage(s, dp, detail={"version": version, "active": True})

        log.info("retrain complete: v%d %s", version, metrics)
        return version, metrics
    except Exception as exc:
        s.rollback()
        log.exception("retrain failed: %s", exc)
        raise
    finally:
        s.close()


def run_reset(demo: bool = True) -> tuple[int, dict]:
    """Wipe + reseed + train a fresh v1 (the dashboard 'reset DB' control)."""
    log.info("reset: wiping + reseeding (demo=%s)", demo)
    seed_database(demo=demo, reset=True)
    return run_retrain(notes="reset")


def scheduled_retrain() -> None:
    """APScheduler entrypoint — never propagate exceptions to the scheduler."""
    try:
        run_retrain(notes="scheduled")
    except Exception as exc:  # noqa: BLE001
        log.warning("scheduled retrain skipped: %s", exc)
