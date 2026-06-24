"""`python -m lenta_core.cli <cmd>` — dev/demo helpers.

Commands: seed, train, recommend, eval, smoke, reset, counts.
"""

from __future__ import annotations

import argparse
import json
import time

from sqlalchemy import select

from .bootstrap import seed_database, train_and_register
from .db import init_db, reset_db, session_scope
from .ingest import counts
from .logging_conf import get_logger
from .ml.funnel import recommend
from .models import Video
from .registry import load_active_model

log = get_logger("lenta.cli")


def _print_feed(feed: list[dict], debug: dict, titles: dict[int, Video]) -> None:
    print(f"\n  funnel: catalog={debug['catalog']} -> candidates={debug['candidates']} "
          f"-> ranked={debug['ranked']} -> feed={debug['feed']}  "
          f"[{debug['retrieval']}, v{debug['model_version']}, "
          f"cold={debug['cold_start']}, {debug['latency_ms']}ms]")
    for i, it in enumerate(feed, 1):
        v = titles.get(it["video_id"])
        title = v.title if v else f"video {it['video_id']}"
        genres = ",".join(v.genres) if v else "?"
        print(f"  {i:>2}. [{it['score']:.3f}] {title}  ({genres}) <{it['stage']}>")


def cmd_recommend(args: argparse.Namespace) -> None:
    with session_scope() as sess:
        loaded = load_active_model(sess)
        if not loaded:
            print("No active model. Run: python -m lenta_core.cli train")
            return
        _, bundle = loaded
        feed, debug = recommend(
            bundle, args.user, args.k, now_epoch=time.time(), variant=args.variant
        )
        ids = [it["video_id"] for it in feed]
        titles = {
            v.id: v for v in sess.execute(select(Video).where(Video.id.in_(ids))).scalars()
        }
        print(f"Top-{args.k} for user {args.user} (variant={args.variant}):")
        _print_feed(feed, debug, titles)


def cmd_eval(args: argparse.Namespace) -> None:
    with session_scope() as sess:
        loaded = load_active_model(sess)
        if not loaded:
            print("No active model.")
            return
        mv, _ = loaded
        print(f"Active model v{mv.version} ({mv.algo}), {mv.artifact_bytes} bytes")
        print(json.dumps(mv.metrics, indent=2))


def cmd_seed(args: argparse.Namespace) -> None:
    c = seed_database(demo=args.demo, reset=not args.no_reset)
    print(f"Seeded: {c}")


def cmd_train(args: argparse.Namespace) -> None:
    version, metrics = train_and_register(notes=args.notes or "cli")
    print(f"Trained + registered v{version}")
    print(json.dumps(metrics, indent=2))


def cmd_counts(args: argparse.Namespace) -> None:
    with session_scope() as sess:
        print(json.dumps(counts(sess), indent=2))


def cmd_reset(args: argparse.Namespace) -> None:
    reset_db()
    print("Database reset (schema recreated).")


def cmd_smoke(args: argparse.Namespace) -> None:
    """Full pipeline in one shot: seed -> train -> recommend -> eval."""
    init_db()
    print("== seed (demo) ==")
    c = seed_database(demo=True, reset=True)
    print(c)
    print("== train v1 ==")
    version, metrics = train_and_register(notes="smoke")
    print(f"v{version}:", json.dumps(metrics))
    print("== recommend (warm user 1, cold user 999999) ==")
    with session_scope() as sess:
        _, bundle = load_active_model(sess)
        for uid in (1, 999_999):
            feed, debug = recommend(bundle, uid, 10, now_epoch=time.time())
            ids = [it["video_id"] for it in feed]
            titles = {v.id: v for v in sess.execute(select(Video).where(Video.id.in_(ids))).scalars()}
            print(f"\nuser {uid}:")
            _print_feed(feed, debug, titles)
    assert metrics["recall_at_k"] >= 0.0
    print("\nSMOKE OK")


def main() -> None:
    p = argparse.ArgumentParser(prog="lenta_core.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("seed", help="seed catalog/users/backfill")
    sp.add_argument("--demo", action="store_true")
    sp.add_argument("--no-reset", action="store_true")
    sp.set_defaults(func=cmd_seed)

    sp = sub.add_parser("train", help="train + register next version")
    sp.add_argument("--notes", default="")
    sp.set_defaults(func=cmd_train)

    sp = sub.add_parser("recommend", help="print top-k for a user")
    sp.add_argument("--user", type=int, default=1)
    sp.add_argument("--k", type=int, default=10)
    sp.add_argument("--variant", default="treatment", choices=["treatment", "control"])
    sp.set_defaults(func=cmd_recommend)

    sp = sub.add_parser("eval", help="show active model metrics")
    sp.set_defaults(func=cmd_eval)

    sp = sub.add_parser("counts", help="row counts")
    sp.set_defaults(func=cmd_counts)

    sp = sub.add_parser("reset", help="drop + recreate schema")
    sp.set_defaults(func=cmd_reset)

    sp = sub.add_parser("smoke", help="seed -> train -> recommend -> eval")
    sp.set_defaults(func=cmd_smoke)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
