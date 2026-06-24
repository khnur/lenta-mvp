"""Behaviour simulator.

A :class:`World` holds latent user affinities and item features as numpy arrays
and exposes the *same* engagement model used by:

* the historical **backfill** (bulk events sampled by a "natural exposure" feed), and
* the **live simulator** (the trainer fetches /feed, then engages with the returned
  items according to latent affinity — so a better model earns more watch-time).

``shift_preferences`` is implemented via :meth:`World.apply_scenario`.
Everything is deterministic given an rng.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import GENRE_PEAK_HOUR, genre_list
from ..models import Event, User, Video

# --- engagement model constants (tuned for CTR ~0.25 baseline, clear gradient) ---
CLICK_A = 3.2      # affinity weight
CLICK_B = 1.1      # popularity weight
CLICK_TOD = 0.7    # time-of-day weight
CLICK_FRESH = 0.5  # freshness weight
CLICK_BIAS = 2.3   # baseline shift (higher => lower CTR)

PLAY_GIVEN_CLICK = 0.85
WF_BASE = 0.10
WF_AFF = 0.75
WF_TOD = 0.10
WF_DUR = 0.30
WF_KAPPA = 6.0     # Beta concentration for watch-fraction noise

FRESH_TAU_DAYS = 30.0
EXPOSURE_TEMP = 0.5  # softmax temperature for the natural-exposure feed


def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class Engagement:
    impression: bool
    clicked: bool
    played: bool
    watch_fraction: float
    watch_seconds: float


@dataclass
class World:
    """In-memory view of users + catalog used to generate behaviour."""

    n_genres: int
    genre_names: list[str]

    user_ids: np.ndarray
    U: np.ndarray            # (n_users, n_genres) affinity, rows ~sum to 1
    activity: np.ndarray     # (n_users,) sampling weight

    video_ids: np.ndarray
    Vg: np.ndarray           # (n_videos, n_genres) row-normalised genre multi-hot
    v_primary: np.ndarray    # (n_videos,) primary genre index
    v_duration: np.ndarray   # (n_videos,) seconds
    v_upload_epoch: np.ndarray
    v_pop: np.ndarray        # (n_videos,) base popularity in [0,1]
    v_creator: np.ndarray

    _uidx: dict[int, int] = field(default_factory=dict)
    _vidx: dict[int, int] = field(default_factory=dict)

    scenario: str = "baseline"
    scenario_detail: dict = field(default_factory=dict)
    surge_videos: set[int] = field(default_factory=set)  # video_ids to boost in exposure

    # ------------------------------------------------------------------ build
    @classmethod
    def from_rows(
        cls, users: list[dict], videos: list[dict], *, n_genres: int, rng: np.random.Generator
    ) -> "World":
        genre_names = genre_list(n_genres)
        u_ids = np.array([u["id"] for u in users], dtype=np.int64)
        U = np.array([u["affinity"] for u in users], dtype=np.float64)
        U = U / np.clip(U.sum(axis=1, keepdims=True), 1e-9, None)
        activity = rng.lognormal(mean=0.0, sigma=0.6, size=len(users))

        return cls._assemble(u_ids, U, activity, videos, genre_names, n_genres)

    @classmethod
    def from_db(cls, session: Session, *, n_genres: int, rng: np.random.Generator) -> "World":
        users = session.execute(select(User)).scalars().all()
        videos = session.execute(select(Video)).scalars().all()
        if not users or not videos:
            raise ValueError("World.from_db: users/videos tables are empty")
        genre_names = genre_list(n_genres)
        u_ids = np.array([u.id for u in users], dtype=np.int64)
        U = np.array(
            [_pad(u.affinity, n_genres) for u in users], dtype=np.float64
        )
        U = U / np.clip(U.sum(axis=1, keepdims=True), 1e-9, None)
        activity = rng.lognormal(mean=0.0, sigma=0.6, size=len(users))
        vrows = [
            {
                "id": v.id,
                "genres": v.genres,
                "duration_seconds": v.duration_seconds,
                "upload_time": v.upload_time,
                "base_popularity": v.base_popularity,
                "creator_id": v.creator_id,
            }
            for v in videos
        ]
        return cls._assemble(u_ids, U, activity, vrows, genre_names, n_genres)

    @classmethod
    def _assemble(cls, u_ids, U, activity, videos, genre_names, n_genres) -> "World":
        gindex = {g: i for i, g in enumerate(genre_names)}
        v_ids, Vg, prim, dur, up, pop, creator = [], [], [], [], [], [], []
        for v in videos:
            vec = np.zeros(n_genres)
            idxs = [gindex[g] for g in v["genres"] if g in gindex]
            if not idxs:
                idxs = [0]
            vec[idxs] = 1.0
            vec = vec / vec.sum()
            v_ids.append(v["id"])
            Vg.append(vec)
            prim.append(idxs[0])
            dur.append(float(v["duration_seconds"]))
            up.append(_epoch(v["upload_time"]))
            pop.append(float(v["base_popularity"]))
            creator.append(int(v["creator_id"]))

        world = cls(
            n_genres=n_genres,
            genre_names=genre_names,
            user_ids=u_ids,
            U=U,
            activity=activity / activity.sum(),
            video_ids=np.array(v_ids, dtype=np.int64),
            Vg=np.array(Vg),
            v_primary=np.array(prim, dtype=np.int64),
            v_duration=np.array(dur),
            v_upload_epoch=np.array(up),
            v_pop=np.array(pop),
            v_creator=np.array(creator, dtype=np.int64),
        )
        world._uidx = {int(u): i for i, u in enumerate(u_ids)}
        world._vidx = {int(v): i for i, v in enumerate(world.video_ids)}
        return world

    # ------------------------------------------------------------- behaviour
    def pick_user(self, rng: np.random.Generator) -> int:
        i = int(rng.choice(len(self.user_ids), p=self.activity))
        return int(self.user_ids[i])

    def exposure_probs(self, user_id: int, ts: datetime) -> np.ndarray:
        """Probability a 'natural' feed surfaces each video to this user."""
        u = self._uidx[user_id]
        ts_epoch = _epoch(ts)
        age_days = np.clip((ts_epoch - self.v_upload_epoch) / 86400.0, 0, None)
        fresh = np.exp(-age_days / FRESH_TAU_DAYS)
        match = self.Vg @ self.U[u]
        # affinity-led exposure (users mostly browse what they like), with
        # popularity + freshness as secondary drivers -> a learnable signal that
        # a personalized model can beat the popularity baseline on.
        score = 0.45 * self.v_pop + 0.2 * fresh + 1.4 * match
        if self.surge_videos:
            boost = np.array(
                [3.0 if int(v) in self.surge_videos else 0.0 for v in self.video_ids]
            )
            score = score + boost
        score = score - score.max()
        ex = np.exp(score / EXPOSURE_TEMP)
        return ex / ex.sum()

    def engage(self, user_id: int, video_id: int, ts: datetime, rng: np.random.Generator) -> Engagement:
        """Decide click / play / watch-fraction for one (user, video) impression."""
        u = self._uidx[user_id]
        v = self._vidx[video_id]
        match = float(self.U[u] @ self.Vg[v])
        match_scaled = match / (float(self.U[u].max()) + 1e-9)
        tod = self._tod_match(int(self.v_primary[v]), ts.hour)
        age_days = max(0.0, (_epoch(ts) - float(self.v_upload_epoch[v])) / 86400.0)
        fresh = math.exp(-age_days / FRESH_TAU_DAYS)

        logit = (
            CLICK_A * match_scaled
            + CLICK_B * float(self.v_pop[v])
            + CLICK_TOD * tod
            + CLICK_FRESH * fresh
            - CLICK_BIAS
        )
        clicked = bool(rng.random() < _sigmoid(logit))
        played = clicked and bool(rng.random() < PLAY_GIVEN_CLICK)

        wf = 0.0
        secs = 0.0
        if played:
            dur_penalty = float(_sigmoid((self.v_duration[v] - 1200.0) / 600.0)) * 0.6
            mu = float(np.clip(WF_BASE + WF_AFF * match_scaled + WF_TOD * tod - WF_DUR * dur_penalty, 0.03, 0.97))
            a = mu * WF_KAPPA
            b = (1.0 - mu) * WF_KAPPA
            wf = float(rng.beta(a, b))
            secs = wf * float(self.v_duration[v])
        return Engagement(True, clicked, played, wf, secs)

    def _tod_match(self, genre_idx: int, hour: int) -> float:
        name = self.genre_names[genre_idx]
        peak = GENRE_PEAK_HOUR.get(name, 12)
        d = abs(hour - peak)
        d = min(d, 24 - d)
        return 1.0 - d / 12.0

    # -------------------------------------------------------------- scenarios
    def apply_scenario(self, scenario: str, intensity: float, rng: np.random.Generator) -> dict:
        """``shift_preferences`` hook: mutate the world for a demo scenario.

        Returns a small report dict describing the change for the dashboard.
        """
        self.scenario = scenario
        if scenario == "genre_shift":
            target = int(rng.integers(0, self.n_genres))
            # swing roughly half the audience toward `target`
            mask = rng.random(len(self.user_ids)) < 0.5
            alpha = float(np.clip(0.35 * intensity, 0.1, 0.9))
            onehot = np.zeros(self.n_genres)
            onehot[target] = 1.0
            self.U[mask] = (1 - alpha) * self.U[mask] + alpha * onehot
            self.U = self.U / np.clip(self.U.sum(axis=1, keepdims=True), 1e-9, None)
            self.scenario_detail = {
                "genre": self.genre_names[target],
                "genre_idx": target,
                "cohort_share": float(mask.mean()),
                "alpha": alpha,
            }
        elif scenario == "new_content_surge":
            target = int(rng.integers(0, self.n_genres))
            self.scenario_detail = {"genre": self.genre_names[target], "genre_idx": target}
        elif scenario == "cold_start_wave":
            self.scenario_detail = {}
        else:
            self.scenario = "baseline"
            self.scenario_detail = {}
            self.surge_videos.clear()
        return {"scenario": self.scenario, **self.scenario_detail}

    def report(self) -> dict:
        return {"scenario": self.scenario, "detail": self.scenario_detail}


# --------------------------------------------------------------------------- #
# Bulk historical backfill                                                     #
# --------------------------------------------------------------------------- #
def simulate_backfill(
    world: World,
    n_events: int,
    *,
    rng: np.random.Generator,
    start: datetime,
    end: datetime,
    variant: str = "treatment",
) -> list[dict]:
    """Generate ~``n_events`` historical event dicts grouped into sessions."""
    events: list[dict] = []
    span = (end - start).total_seconds()
    session_no = 0
    while len(events) < n_events:
        session_no += 1
        user_id = world.pick_user(rng)
        t0 = start + timedelta(seconds=float(rng.uniform(0, span)))
        sid = f"bf-{session_no}-{user_id}"
        probs = world.exposure_probs(user_id, t0)
        n_imp = int(rng.integers(3, 9))
        n_imp = min(n_imp, (probs > 0).sum())
        picks = rng.choice(len(world.video_ids), size=n_imp, replace=False, p=probs)
        t = t0
        for vi in picks:
            video_id = int(world.video_ids[vi])
            t = t + timedelta(seconds=float(rng.uniform(20, 240)))
            eng = world.engage(user_id, video_id, t, rng)
            ctx = {"hour": t.hour, "source": "backfill"}
            events.append(_event(user_id, video_id, "impression", 0.0, 0.0, sid, variant, t, ctx))
            if eng.clicked:
                events.append(
                    _event(user_id, video_id, "click", 0.0, 0.0, sid, variant, t + timedelta(seconds=2), ctx)
                )
            if eng.played:
                events.append(
                    _event(
                        user_id, video_id, "play", eng.watch_seconds, eng.watch_fraction,
                        sid, variant, t + timedelta(seconds=4), ctx,
                    )
                )
            if len(events) >= n_events:
                break
    return events


# --------------------------------------------------------------------------- #
# Live injections (scenarios that add rows to the DB)                          #
# --------------------------------------------------------------------------- #
def inject_new_content(
    session: Session,
    *,
    n: int,
    n_genres: int,
    rng: np.random.Generator,
    genre_idx: int | None = None,
    now: datetime | None = None,
) -> list[int]:
    """Insert a burst of brand-new high-appeal videos (new_content_surge)."""
    from .catalog import _GENRE_MINUTES, _make_tags  # local import to avoid cycle

    now = now or datetime.now(timezone.utc)
    names = genre_list(n_genres)
    if genre_idx is None:
        genre_idx = int(rng.integers(0, n_genres))
    primary = names[genre_idx]
    max_id = session.execute(select(Video.id).order_by(Video.id.desc()).limit(1)).scalar() or 0
    new_ids: list[int] = []
    for j in range(n):
        vid = max_id + 1 + j
        minutes = max(0.5, _GENRE_MINUTES.get(primary, 12) * float(rng.lognormal(0, 0.3)))
        v = Video(
            id=vid,
            title=f"[NEW] {primary.title()} Drop #{vid}",
            creator_id=int(rng.integers(1, 50)),
            genres=[primary],
            tags=_make_tags([primary], rng),
            duration_seconds=int(minutes * 60),
            upload_time=now,
            base_popularity=float(np.clip(rng.uniform(0.6, 1.0), 0, 1)),
        )
        session.add(v)
        new_ids.append(vid)
    session.flush()
    return new_ids


def inject_new_users(
    session: Session,
    *,
    count: int,
    n_genres: int,
    rng: np.random.Generator,
    now: datetime | None = None,
) -> list[int]:
    """Insert brand-new users with no history (cold_start_wave)."""
    from .users import new_user_rows

    now = now or datetime.now(timezone.utc)
    max_id = session.execute(select(User.id).order_by(User.id.desc()).limit(1)).scalar() or 0
    rows = new_user_rows(max_id + 1, count, n_genres=n_genres, rng=rng, now=now)
    for r in rows:
        session.add(User(**r))
    session.flush()
    return [r["id"] for r in rows]


# --------------------------------------------------------------------------- helpers
def _event(user_id, video_id, etype, secs, frac, sid, variant, ts, ctx) -> dict:
    return {
        "user_id": int(user_id),
        "video_id": int(video_id),
        "event_type": etype,
        "watch_seconds": float(secs),
        "watch_fraction": float(frac),
        "session_id": sid,
        "variant": variant,
        "ts": ts,
        "context": ctx,
    }


def _pad(vec: list, n: int) -> list:
    vec = list(vec or [])
    if len(vec) >= n:
        return vec[:n]
    return vec + [0.0] * (n - len(vec))


def _epoch(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()
