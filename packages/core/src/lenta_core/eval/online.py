"""Online behavioural metrics computed from the `events` stream, per A/B variant.

CTR (clicks/impressions), avg watch seconds & fraction (plays), and average
session length (events per session).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


def _variant_metrics(df: pd.DataFrame, variant: str) -> dict:
    imp = int((df["event_type"] == "impression").sum())
    clk = int((df["event_type"] == "click").sum())
    plays = df[df["event_type"] == "play"]
    ply = int(len(plays))
    sess_len = df.groupby("session_id").size().mean() if not df.empty else 0.0
    return {
        "variant": variant,
        "impressions": imp,
        "clicks": clk,
        "plays": ply,
        "ctr": round(clk / imp, 4) if imp else 0.0,
        "avg_watch_seconds": round(float(plays["watch_seconds"].mean()), 2) if ply else 0.0,
        "avg_watch_fraction": round(float(plays["watch_fraction"].mean()), 4) if ply else 0.0,
        "avg_session_length": round(float(sess_len), 2),
    }


def online_metrics(events: pd.DataFrame) -> dict:
    """Return overall + per-variant metrics and treatment-vs-control lift."""
    overall = _variant_metrics(events, "overall")
    per_variant = []
    by_variant: dict[str, dict] = {}
    for variant, df in events.groupby("variant"):
        m = _variant_metrics(df, str(variant))
        per_variant.append(m)
        by_variant[str(variant)] = m

    lift = _lift(by_variant)
    return {"overall": overall, "per_variant": per_variant, "lift": lift}


def _lift(by_variant: dict[str, dict]) -> dict[str, float]:
    lift: dict[str, float] = {}
    t, c = by_variant.get("treatment"), by_variant.get("control")
    if t and c:
        for metric in ("ctr", "avg_watch_seconds", "avg_watch_fraction", "avg_session_length"):
            base = c[metric]
            lift[metric] = round((t[metric] - base) / base, 4) if base else 0.0
    return lift


# --------------------------------------------------------------------------- #
# SQL-aggregated variant — O(1) result size, used by the hot /metrics endpoint #
# --------------------------------------------------------------------------- #
_AGG = """
  count(*) FILTER (WHERE event_type='impression') AS imp,
  count(*) FILTER (WHERE event_type='click') AS clk,
  count(*) FILTER (WHERE event_type='play') AS ply,
  coalesce(avg(watch_seconds) FILTER (WHERE event_type='play'), 0) AS avg_ws,
  coalesce(avg(watch_fraction) FILTER (WHERE event_type='play'), 0) AS avg_wf,
  (count(*)::float / NULLIF(count(DISTINCT session_id), 0)) AS asl
"""


def _row_metrics(variant, imp, clk, ply, avg_ws, avg_wf, asl) -> dict:
    imp = int(imp or 0)
    return {
        "variant": variant,
        "impressions": imp,
        "clicks": int(clk or 0),
        "plays": int(ply or 0),
        "ctr": round((clk or 0) / imp, 4) if imp else 0.0,
        "avg_watch_seconds": round(float(avg_ws or 0), 2),
        "avg_watch_fraction": round(float(avg_wf or 0), 4),
        "avg_session_length": round(float(asl or 0), 2),
    }


def online_metrics_sql(session: Session, *, cutoff) -> dict:
    """Same shape as :func:`online_metrics`, computed by Postgres aggregation so
    the result is a couple of rows regardless of how many events are in window."""
    per = session.execute(
        text(f"SELECT variant, {_AGG} FROM events WHERE ts >= :c GROUP BY variant"),
        {"c": cutoff},
    ).all()
    ov = session.execute(
        text(f"SELECT 'overall' AS variant, {_AGG} FROM events WHERE ts >= :c"),
        {"c": cutoff},
    ).one()

    per_variant = [
        _row_metrics(r.variant, r.imp, r.clk, r.ply, r.avg_ws, r.avg_wf, r.asl) for r in per
    ]
    overall = _row_metrics("overall", ov.imp, ov.clk, ov.ply, ov.avg_ws, ov.avg_wf, ov.asl)
    by = {m["variant"]: m for m in per_variant}
    return {"overall": overall, "per_variant": per_variant, "lift": _lift(by)}
