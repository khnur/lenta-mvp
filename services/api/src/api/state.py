"""App state: the hot-swappable model cache + Redis client.

The active model is loaded on startup and hot-reloaded by a background poller
whenever the trainer registers a newer active version.
"""

from __future__ import annotations

import time

from redis import Redis
from sqlalchemy.orm import Session

from lenta_core.config import settings
from lenta_core.logging_conf import get_logger
from lenta_core.ml.ranker import load_booster
from lenta_core.registry import active_version, load_active_model

log = get_logger("lenta.api.state")


class ModelHolder:
    def __init__(self) -> None:
        self.version: int | None = None
        self.bundle = None
        self.booster = None
        self.loaded_at: float = 0.0
        self.created_at = None
        self.metrics: dict = {}
        self.algo: str = ""

    @property
    def ready(self) -> bool:
        return self.bundle is not None

    def set(self, mv, bundle) -> None:
        self.bundle = bundle
        self.booster = load_booster(bundle.ranker_model_str)
        self.version = mv.version
        self.created_at = mv.created_at
        self.metrics = mv.metrics
        self.algo = mv.algo
        self.loaded_at = time.time()


class AppState:
    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
        self.model = ModelHolder()

    def reload(self, session: Session, *, force: bool = False) -> bool:
        """Load the active model if it is newer than what's cached."""
        av = active_version(session)
        if av is None:
            return False
        if force or av != self.model.version:
            loaded = load_active_model(session)
            if loaded:
                mv, bundle = loaded
                holder = ModelHolder()
                holder.set(mv, bundle)
                self.model = holder  # atomic swap: readers see old or new holder whole
                log.info("loaded active model v%d (%d items)", mv.version, len(bundle.item_ids))
                return True
        return False

    def ping_redis(self) -> bool:
        try:
            return bool(self.redis.ping())
        except Exception:
            return False
