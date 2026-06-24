"""Catalog generation: videos with genres, tags, duration, upload time, and a
latent global appeal ("base_popularity"). Deterministic given an rng."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

# Fixed genre vocabulary. n_genres in config selects a prefix of this list.
GENRES: list[str] = [
    "comedy",
    "drama",
    "action",
    "music",
    "gaming",
    "sports",
    "news",
    "tech",
    "cooking",
    "travel",
    "education",
    "kids",
]

# Hour of day (0-23) at which each genre is most consumed (time-of-day effect).
GENRE_PEAK_HOUR: dict[str, int] = {
    "comedy": 21,
    "drama": 22,
    "action": 20,
    "music": 18,
    "gaming": 23,
    "sports": 19,
    "news": 8,
    "tech": 12,
    "cooking": 17,
    "travel": 14,
    "education": 10,
    "kids": 7,
}

# Typical content length (minutes) per genre — drives the watch-fraction model.
_GENRE_MINUTES: dict[str, float] = {
    "comedy": 8,
    "drama": 28,
    "action": 16,
    "music": 4,
    "gaming": 24,
    "sports": 12,
    "news": 6,
    "tech": 14,
    "cooking": 11,
    "travel": 18,
    "education": 32,
    "kids": 9,
}

_ADJ = [
    "Epic", "Daily", "Late-Night", "Ultimate", "Hidden", "Wild", "Classic",
    "Viral", "Cozy", "Insane", "Pro", "Golden", "Quiet", "Electric", "Retro",
]
_NOUN = [
    "Breakdown", "Recap", "Session", "Story", "Guide", "Showdown", "Diary",
    "Mix", "Challenge", "Review", "Highlights", "Journey", "Explainer", "Set",
]


def genre_list(n_genres: int) -> list[str]:
    """Return the active genre vocabulary (a prefix of GENRES, extended if needed)."""
    if n_genres <= len(GENRES):
        return GENRES[:n_genres]
    return GENRES + [f"genre_{i}" for i in range(len(GENRES), n_genres)]


def generate_catalog(
    n_videos: int,
    *,
    n_genres: int,
    backfill_days: int,
    rng: np.random.Generator,
    now: datetime | None = None,
    n_creators: int | None = None,
) -> list[dict]:
    """Generate ``n_videos`` video rows as plain dicts (ids assigned 1..n)."""
    now = now or datetime.now(timezone.utc)
    genres = genre_list(n_genres)
    n_creators = n_creators or max(8, n_videos // 12)

    # Power-law global appeal: a few hits, a long tail.
    ranks = np.arange(1, n_videos + 1)
    appeal = 1.0 / np.power(ranks, 0.7)
    appeal = appeal / appeal.max()
    rng.shuffle(appeal)

    videos: list[dict] = []
    for i in range(n_videos):
        vid = i + 1
        # 1-3 genres, the first is "primary".
        k = int(rng.integers(1, 4))
        gidx = rng.choice(len(genres), size=k, replace=False)
        vgenres = [genres[j] for j in gidx]
        primary = vgenres[0]

        minutes = max(0.5, _GENRE_MINUTES.get(primary, 12) * float(rng.lognormal(0, 0.4)))
        duration = int(minutes * 60)

        # Upload spread over the backfill window plus some older + some very fresh.
        age_days = float(rng.uniform(0, backfill_days + 90))
        upload_time = now - timedelta(days=age_days, hours=float(rng.uniform(0, 24)))

        tags = _make_tags(vgenres, rng)
        title = f"{rng.choice(_ADJ)} {primary.title()} {rng.choice(_NOUN)} #{vid}"

        videos.append(
            {
                "id": vid,
                "title": title,
                "creator_id": int(rng.integers(1, n_creators + 1)),
                "genres": vgenres,
                "tags": tags,
                "duration_seconds": duration,
                "upload_time": upload_time,
                "base_popularity": float(appeal[i]),
            }
        )
    return videos


def _make_tags(genres: list[str], rng: np.random.Generator) -> list[str]:
    pool = [
        "trending", "creator-pick", "longform", "shorts", "tutorial", "live",
        "interview", "compilation", "behind-the-scenes", "beginner", "advanced",
    ]
    k = int(rng.integers(2, 5))
    chosen = list(rng.choice(pool, size=min(k, len(pool)), replace=False))
    return genres[:1] + chosen
