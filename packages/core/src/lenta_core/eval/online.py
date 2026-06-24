"""Online behavioural metrics computed from the `events` stream, per A/B variant.

CTR (clicks/impressions), avg watch seconds & fraction (plays), and average
session length (events per session).
"""

from __future__ import annotations

import pandas as pd


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

    lift: dict[str, float] = {}
    t, c = by_variant.get("treatment"), by_variant.get("control")
    if t and c:
        for metric in ("ctr", "avg_watch_seconds", "avg_watch_fraction", "avg_session_length"):
            base = c[metric]
            lift[metric] = round((t[metric] - base) / base, 4) if base else 0.0

    return {"overall": overall, "per_variant": per_variant, "lift": lift}
