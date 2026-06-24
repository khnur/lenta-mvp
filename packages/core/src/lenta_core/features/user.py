"""Per-user aggregate features, computed once at train time and snapshotted into
the model bundle so serving can score without scanning history on every request.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_user_aggregates(
    events: pd.DataFrame,
    user_ids: np.ndarray,
    *,
    item_index: dict[int, int],
    item_genre_matrix: np.ndarray,
    n_genres: int,
) -> dict:
    """Return aligned arrays: profile (nu x g), avg_wf, play_rate, hist_count."""
    uidx = {int(u): i for i, u in enumerate(user_ids)}
    nu = len(user_ids)

    hist_count = np.zeros(nu)
    avg_wf = np.zeros(nu)
    play_rate = np.zeros(nu)
    profile = np.zeros((nu, n_genres))

    if not events.empty:
        # history size = total events per user
        sizes = events.groupby("user_id").size()
        for uid, c in sizes.items():
            if int(uid) in uidx:
                hist_count[uidx[int(uid)]] = float(c)

        imp = events[events["event_type"] == "impression"].groupby("user_id").size()
        plays = events[events["event_type"] == "play"]
        pcount = plays.groupby("user_id").size()
        wfmean = plays.groupby("user_id")["watch_fraction"].mean()

        for uid in user_ids:
            i = uidx[int(uid)]
            p = float(pcount.get(int(uid), 0))
            im = float(imp.get(int(uid), 0))
            avg_wf[i] = float(wfmean.get(int(uid), 0.0))
            play_rate[i] = p / im if im > 0 else 0.0

        # watch-weighted genre profile from plays
        if not plays.empty:
            rows = plays["video_id"].map(item_index)
            valid = rows.notna().to_numpy()
            r = rows[valid].to_numpy(dtype=int)
            uu = plays["user_id"][valid].map(uidx).to_numpy(dtype=int)
            w = (plays["watch_fraction"][valid].fillna(0.0).to_numpy(float) + 0.05)
            contrib = item_genre_matrix[r] * w[:, None]
            np.add.at(profile, uu, contrib)
        sums = profile.sum(axis=1, keepdims=True)
        profile = np.divide(profile, sums, out=np.zeros_like(profile), where=sums > 0)

    return {
        "user_ids_agg": np.asarray(user_ids, dtype=np.int64),
        "user_genre_profile": profile,
        "user_avg_wf": avg_wf,
        "user_play_rate": play_rate,
        "user_hist_count": hist_count,
    }
