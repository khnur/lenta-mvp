"""The serving funnel: candidate generation (ALS + content + freshness) →
LightGBM ranking on watch-time → diversity/freshness re-rank → feed.

`recommend` is pure: it takes a loaded :class:`ModelBundle` plus request context
and returns scored video ids + per-stage debug. The api maps ids to display rows.
"""

from __future__ import annotations

import math
import time

import numpy as np

from ..features.item import time_of_day_match
from ..features.ranking import feature_row, to_matrix
from ..features.session import session_feature_view
from .artifacts import ModelBundle
from .content import content_scores
from .ranker import load_booster, predict


def _fresh_candidates(bundle: ModelBundle, now_epoch: float, n: int) -> list[int]:
    age = now_epoch - bundle.item_upload_epoch
    idx = np.argsort(age)[:n]
    return [int(bundle.item_ids[i]) for i in idx]


def _candidate_ids(
    bundle: ModelBundle, user_id: int, now_epoch: float, n_candidates: int
) -> tuple[list[int], str, bool]:
    """Union ALS / content / popularity / freshness candidates."""
    known = bundle.has_user(user_id)
    profile = bundle.user_profile(user_id)
    cand: list[int] = []
    retrieval = "als"
    cold = not known

    if known:
        uvec = bundle.als_user_vector(user_id)
        scores = bundle.als_item_factors @ uvec
        top = np.argsort(-scores)[: int(n_candidates * 0.7)]
        cand.extend(int(bundle.als_item_ids[i]) for i in top)

    if profile.sum() > 0:
        cs = content_scores(bundle.item_genre_matrix, profile)
        ctop = np.argsort(-cs)[: int(n_candidates * 0.3)]
        cand.extend(int(bundle.item_ids[i]) for i in ctop)
        if not known:
            retrieval = "content"

    if not cand:  # brand-new user, no profile
        retrieval = "popularity"
        cand.extend(int(v) for v in bundle.pop_ids[:n_candidates])

    # always mix in some fresh uploads so new content can break through
    cand.extend(_fresh_candidates(bundle, now_epoch, max(10, n_candidates // 10)))

    # dedup preserving order, cap
    seen: set[int] = set()
    uniq = [v for v in cand if not (v in seen or seen.add(v))]
    return uniq[:n_candidates], retrieval, cold


def recommend(
    bundle: ModelBundle,
    user_id: int,
    k: int,
    *,
    session: dict | None = None,
    now_epoch: float,
    n_candidates: int = 300,
    max_per_genre: int = 3,
    max_per_creator: int = 2,
    fresh_slots: int = 2,
    fresh_days: float = 10.0,
    variant: str = "treatment",
    booster=None,
) -> tuple[list[dict], dict]:
    t0 = time.perf_counter()
    catalog = int(len(bundle.item_ids))
    session = session or {}
    hour = int(time.gmtime(now_epoch).tm_hour)

    # ---- A/B control: popularity baseline, no ranker ----
    if variant == "control":
        items = [
            {"video_id": int(v), "score": float(s), "stage": "popularity"}
            for v, s in _topk_pop(bundle, k)
        ]
        debug = _debug(catalog, len(items), 0, len(items), "popularity", bundle.version, False, t0)
        return items, debug

    # ---- retrieval ----
    cand_ids, retrieval, cold = _candidate_ids(bundle, user_id, now_epoch, n_candidates)
    if not cand_ids:
        return [], _debug(catalog, 0, 0, 0, retrieval, bundle.version, cold, t0)

    # ---- feature build for ranking ----
    profile = bundle.user_profile(user_id)
    uvec = bundle.als_user_vector(user_id)
    ua = bundle._uagg.get(int(user_id))
    u_hist = float(bundle.user_hist_count[ua]) if ua is not None else 0.0
    u_avg = float(bundle.user_avg_wf[ua]) if ua is not None else 0.0
    u_pr = float(bundle.user_play_rate[ua]) if ua is not None else 0.0

    rows: list[list[float]] = []
    meta: list[dict] = []
    for vid in cand_ids:
        ii = bundle.item_index(vid)
        if ii is None:
            continue
        pg = int(bundle.item_primary[ii])
        gname = bundle.genre_names[pg]
        igv = bundle.item_genre_matrix[ii]
        als_score = float(bundle.als_item_factors[ii] @ uvec) if uvec is not None else 0.0
        denom = (np.linalg.norm(profile) * np.linalg.norm(igv)) + 1e-9
        content_score = float(profile @ igv) / denom
        affinity = float(profile @ igv)
        sgm, slen = session_feature_view(session, gname)
        age_days = max(0.0, (now_epoch - float(bundle.item_upload_epoch[ii])) / 86400.0)
        rows.append(
            feature_row(
                als_score=als_score,
                content_score=content_score,
                user_item_affinity=affinity,
                pop_score=float(bundle.item_pop[ii]),
                item_age_days=age_days,
                item_duration_log=math.log1p(float(bundle.item_duration[ii])),
                item_primary_genre=pg,
                u_hist_count_log=math.log1p(u_hist),
                u_avg_wf=u_avg,
                u_play_rate=u_pr,
                session_genre_match=sgm,
                session_len=slen,
                tod_match=time_of_day_match(gname, hour),
                hour=hour,
            )
        )
        meta.append(
            {
                "video_id": vid,
                "genre": pg,
                "creator": int(bundle.item_creator[ii]),
                "age_days": age_days,
            }
        )

    booster = booster or load_booster(bundle.ranker_model_str)
    scores = predict(booster, to_matrix(rows))
    order = np.argsort(-scores)

    feed = _rerank(
        order, scores, meta, k,
        max_per_genre=max_per_genre,
        max_per_creator=max_per_creator,
        fresh_slots=fresh_slots,
        fresh_days=fresh_days,
    )
    debug = _debug(catalog, len(cand_ids), len(rows), len(feed), retrieval, bundle.version, cold, t0)
    return feed, debug


def _rerank(order, scores, meta, k, *, max_per_genre, max_per_creator, fresh_slots, fresh_days):
    """Greedy selection with per-genre / per-creator caps + reserved fresh slots."""
    genre_count: dict[int, int] = {}
    creator_count: dict[int, int] = {}
    chosen: list[dict] = []
    fresh_chosen = 0
    deferred: list[int] = []

    for idx in order:
        m = meta[idx]
        if len(chosen) >= k:
            break
        if genre_count.get(m["genre"], 0) >= max_per_genre or \
           creator_count.get(m["creator"], 0) >= max_per_creator:
            deferred.append(idx)
            continue
        chosen.append({"video_id": m["video_id"], "score": float(scores[idx]),
                       "stage": "fresh" if m["age_days"] <= fresh_days else "ranked"})
        genre_count[m["genre"]] = genre_count.get(m["genre"], 0) + 1
        creator_count[m["creator"]] = creator_count.get(m["creator"], 0) + 1
        if m["age_days"] <= fresh_days:
            fresh_chosen += 1

    # backfill remaining slots from deferred (relax caps) if needed
    for idx in deferred:
        if len(chosen) >= k:
            break
        m = meta[idx]
        chosen.append({"video_id": m["video_id"], "score": float(scores[idx]),
                       "stage": "ranked"})

    # ensure at least `fresh_slots` fresh items if any fresh candidates exist
    if fresh_chosen < fresh_slots:
        chosen_ids = {c["video_id"] for c in chosen}
        fresh_pool = [i for i in order if meta[i]["age_days"] <= fresh_days
                      and meta[i]["video_id"] not in chosen_ids]
        for i in fresh_pool:
            if fresh_chosen >= fresh_slots or not chosen:
                break
            # replace the lowest-scored non-fresh item
            repl = max(
                (c for c in chosen if c["stage"] != "fresh"),
                key=lambda c: -c["score"], default=None,
            )
            if repl is None:
                break
            chosen.remove(repl)
            chosen.append({"video_id": meta[i]["video_id"], "score": float(scores[i]),
                           "stage": "fresh"})
            fresh_chosen += 1

    chosen.sort(key=lambda c: -c["score"])
    return chosen[:k]


def _topk_pop(bundle: ModelBundle, k: int) -> list[tuple[int, float]]:
    n = min(k, len(bundle.pop_ids))
    smax = float(bundle.pop_scores[0]) if len(bundle.pop_scores) else 1.0
    return [(int(bundle.pop_ids[i]), float(bundle.pop_scores[i] / (smax + 1e-9))) for i in range(n)]


def _debug(catalog, candidates, ranked, feed, retrieval, version, cold, t0) -> dict:
    return {
        "catalog": catalog,
        "candidates": candidates,
        "ranked": ranked,
        "feed": feed,
        "retrieval": retrieval,
        "model_version": version,
        "cold_start": cold,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
