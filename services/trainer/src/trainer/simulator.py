"""The live simulator.

Drives synthetic traffic through the *real* serving path: it GETs /feed for a
user (which assigns the A/B variant and logs impressions), then engages with the
returned items according to the user's latent affinity (so a better model — or a
preference shift — produces visibly different CTR / watch-time). Scenarios
mutate the world: genre_shift swings a cohort's taste in memory, while
new_content_surge / cold_start_wave inject rows into the DB.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import httpx
import numpy as np
from redis import Redis

from lenta_core.config import settings
from lenta_core.db import session_scope
from lenta_core.logging_conf import get_logger
from lenta_core.mock.simulate import World, inject_new_content, inject_new_users
from lenta_core.pipeline import finish_stage, start_stage
from lenta_core.simctl import get_sim, incr_emitted

log = get_logger("lenta.trainer.sim")

HEARTBEAT_SECONDS = 15
SURGE_VIDEOS = 25
COLD_START_USERS = 40


class LiveSimulator:
    def __init__(self) -> None:
        self.r = Redis.from_url(settings.redis_url, decode_responses=True)
        self.client = httpx.Client(base_url=settings.api_url, timeout=8.0)
        self.rng = np.random.default_rng(settings.seed + 7)
        self.world: World | None = None
        self.applied_seq = get_sim(self.r)["scenario_seq"]
        self._stop = threading.Event()
        self._last_heartbeat = 0.0
        self._since_heartbeat = 0

    # -------------------------------------------------------------- world
    def _reload_world(self) -> None:
        with session_scope() as s:
            self.world = World.from_db(s, n_genres=settings.n_genres, rng=self.rng)
        log.info("simulator world loaded: %d users, %d videos",
                 len(self.world.user_ids), len(self.world.video_ids))

    def _ensure_world(self) -> None:
        if self.world is None:
            self._reload_world()

    # ----------------------------------------------------------- scenarios
    def _maybe_apply(self, ctl: dict) -> None:
        if ctl["scenario_seq"] == self.applied_seq:
            return
        self.applied_seq = ctl["scenario_seq"]
        scenario, intensity = ctl["scenario"], ctl["intensity"]
        log.info("applying scenario: %s (intensity=%.1f)", scenario, intensity)
        try:
            if scenario in ("genre_shift", "baseline"):
                self._ensure_world()
                rep = self.world.apply_scenario(scenario, intensity, self.rng)
                log.info("scenario report: %s", rep)
            elif scenario == "new_content_surge":
                with session_scope() as s:
                    ids = inject_new_content(
                        s, n=SURGE_VIDEOS, n_genres=settings.n_genres, rng=self.rng
                    )
                self._reload_world()
                self.world.surge_videos = set(ids)
                self.world.scenario = "new_content_surge"
                log.info("injected %d new videos", len(ids))
            elif scenario == "cold_start_wave":
                with session_scope() as s:
                    ids = inject_new_users(
                        s, count=COLD_START_USERS, n_genres=settings.n_genres, rng=self.rng
                    )
                self._reload_world()
                self.world.scenario = "cold_start_wave"
                log.info("injected %d new users", len(ids))
        except Exception as exc:  # noqa: BLE001
            log.warning("scenario apply failed: %s", exc)

    # -------------------------------------------------------------- step
    def step(self) -> int:
        self._ensure_world()
        assert self.world is not None
        user_id = self.world.pick_user(self.rng)
        now = datetime.now(timezone.utc)
        sid = f"sim-{user_id}-{int(time.time() // 120)}"

        try:
            resp = self.client.get(
                "/feed", params={"user_id": int(user_id), "k": 10, "session_id": sid}
            )
            if resp.status_code != 200:
                return 0
            data = resp.json()
        except httpx.HTTPError:
            return 0

        variant = data["variant"]
        items = data.get("items", [])
        emitted = len(items)  # impressions logged by /feed

        for it in items:
            vid = it["id"]
            try:
                eng = self.world.engage(int(user_id), int(vid), now, self.rng)
            except KeyError:
                # world is stale (post reset/surge) — reload and skip this step
                self._reload_world()
                return emitted
            if eng.clicked:
                self._post(user_id, vid, "click", sid, variant, 0.0, 0.0)
                emitted += 1
            if eng.played:
                self._post(
                    user_id, vid, "play", sid, variant, eng.watch_seconds, eng.watch_fraction
                )
                emitted += 1
        return emitted

    def _post(self, user_id, vid, etype, sid, variant, secs, frac) -> None:
        try:
            self.client.post(
                "/event",
                json={
                    "user_id": int(user_id),
                    "video_id": int(vid),
                    "event_type": etype,
                    "session_id": sid,
                    "watch_seconds": float(secs),
                    "watch_fraction": float(frac),
                    "variant": variant,
                },
            )
        except httpx.HTTPError:
            pass

    # ---------------------------------------------------------- heartbeat
    def _heartbeat(self, emitted: int) -> None:
        self._since_heartbeat += emitted
        now = time.time()
        if now - self._last_heartbeat < HEARTBEAT_SECONDS:
            return
        self._last_heartbeat = now
        try:
            with session_scope() as s:
                run = start_stage(s, "ingest", {"emitted": self._since_heartbeat})
                finish_stage(s, run, detail={"emitted": self._since_heartbeat})
                fu = start_stage(s, "feature_update", {"sessions": "redis"})
                finish_stage(s, fu, detail={"emitted": self._since_heartbeat})
        except Exception as exc:  # noqa: BLE001
            log.debug("heartbeat skipped: %s", exc)
        self._since_heartbeat = 0

    # --------------------------------------------------------------- run
    def run(self) -> None:
        log.info("live simulator thread started (api=%s)", settings.api_url)
        while not self._stop.is_set():
            try:
                ctl = get_sim(self.r)
                self._maybe_apply(ctl)
                if not ctl["running"]:
                    time.sleep(0.5)
                    continue
                rate = float(np.clip(ctl["rate"], 0.2, 50.0))
                n = self.step()
                if n:
                    incr_emitted(self.r, n)
                    self._heartbeat(n)
                time.sleep(1.0 / rate)
            except Exception as exc:  # noqa: BLE001
                log.warning("sim loop error: %s", exc)
                time.sleep(1.0)

    def stop(self) -> None:
        self._stop.set()
