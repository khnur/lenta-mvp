"""`python -m trainer.seed [--demo]` — used by `make seed` / `make demo`.

Resets the DB, seeds catalog/users/backfill, and trains + activates v1.
"""

from __future__ import annotations

import argparse

from lenta_core.bootstrap import seed_database
from lenta_core.logging_conf import get_logger, setup_logging

from .retrain import run_retrain

log = get_logger("lenta.trainer.seed")


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="trainer.seed")
    p.add_argument("--demo", action="store_true", help="smaller, quick, demo-ready state")
    args = p.parse_args()

    counts = seed_database(demo=args.demo, reset=True)
    log.info("seeded: %s", counts)
    version, metrics = run_retrain(notes="seed-v1")
    log.info("trained v%d: %s", version, metrics)
    print(f"Seed complete: {counts}; active model v{version} metrics={metrics}")


if __name__ == "__main__":
    main()
