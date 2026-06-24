"""Real-time per-session features in Redis.

Updated on every event, read by the ranker at serving time. Keeps a short
recency list of genres per session plus a small hash of counters, and a global
sorted-set of active sessions for the dashboard.
"""

from __future__ import annotations

from typing import Any

SESSION_TTL_SECONDS = 60 * 30
_ACTIVE_KEY = "sessions:active"


def _gkey(session_id: str) -> str:
    return f"sess:{session_id}:g"


def _hkey(session_id: str) -> str:
    return f"sess:{session_id}"


def update_session(
    r: Any,
    session_id: str,
    *,
    user_id: int,
    primary_genre: str,
    watch_fraction: float,
    ts_epoch: float,
    history_len: int = 20,
) -> None:
    """Record one interaction into the session's real-time feature state."""
    pipe = r.pipeline()
    gk = _gkey(session_id)
    pipe.lpush(gk, primary_genre)
    pipe.ltrim(gk, 0, history_len - 1)
    pipe.expire(gk, SESSION_TTL_SECONDS)

    hk = _hkey(session_id)
    pipe.hset(
        hk,
        mapping={
            "user_id": int(user_id),
            "last_genre": primary_genre,
            "last_ts": ts_epoch,
            "last_wf": float(watch_fraction),
        },
    )
    pipe.hincrby(hk, "len", 1)
    pipe.expire(hk, SESSION_TTL_SECONDS)
    pipe.zadd(_ACTIVE_KEY, {session_id: ts_epoch})
    pipe.execute()


def read_session_features(r: Any, session_id: str) -> dict:
    """Return {genres, len, last_genre, streak, active} for a session."""
    genres = r.lrange(_gkey(session_id), 0, -1) or []
    h = r.hgetall(_hkey(session_id)) or {}
    length = int(h.get("len", len(genres)))
    last = h.get("last_genre")
    streak = 0
    for g in genres:  # list is most-recent-first
        if g == last:
            streak += 1
        else:
            break
    return {
        "genres": genres,
        "len": length,
        "last_genre": last,
        "streak": streak,
        "active": bool(genres or h),
    }


def session_feature_view(session: dict, candidate_primary_genre: str) -> tuple[float, float]:
    """Return (session_genre_match, session_len) for a candidate genre."""
    genres = session.get("genres") or []
    n = len(genres)
    if n == 0:
        return 0.0, float(session.get("len", 0))
    match = sum(1 for g in genres if g == candidate_primary_genre) / n
    return float(match), float(session.get("len", n))


def active_session_count(r: Any, *, now_epoch: float, window_seconds: int = 120) -> int:
    return int(r.zcount(_ACTIVE_KEY, now_epoch - window_seconds, now_epoch))


def recent_active_sessions(r: Any, *, now_epoch: float, window_seconds: int = 300, limit: int = 25) -> list[dict]:
    """Most-recent active sessions for the live-workflow panel."""
    ids = r.zrevrangebyscore(
        _ACTIVE_KEY, now_epoch, now_epoch - window_seconds, start=0, num=limit
    )
    out: list[dict] = []
    for sid in ids:
        h = r.hgetall(_hkey(sid)) or {}
        out.append(
            {
                "session_id": sid,
                "user_id": int(h["user_id"]) if h.get("user_id") else None,
                "last_genre": h.get("last_genre"),
                "len": int(h.get("len", 0)),
            }
        )
    return out


def prune_active(r: Any, *, now_epoch: float, older_than_seconds: int = 1800) -> None:
    r.zremrangebyscore(_ACTIVE_KEY, 0, now_epoch - older_than_seconds)
