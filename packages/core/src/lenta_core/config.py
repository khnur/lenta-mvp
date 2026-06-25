"""Central configuration, read from the environment only (no secrets in code)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Every field has a safe local default."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- datastores ---
    database_url: str = Field(
        default="postgresql+psycopg://lenta:lenta@localhost:5432/lenta",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- determinism ---
    seed: int = Field(default=42, alias="LENTA_SEED")

    # --- mock data ---
    n_videos: int = Field(default=600, alias="LENTA_N_VIDEOS")
    n_users: int = Field(default=400, alias="LENTA_N_USERS")
    n_genres: int = Field(default=12, alias="LENTA_N_GENRES")
    backfill_days: int = Field(default=30, alias="LENTA_BACKFILL_DAYS")
    backfill_events: int = Field(default=40_000, alias="LENTA_BACKFILL_EVENTS")

    # --- trainer ---
    seed_on_boot: bool = Field(default=True, alias="SEED_ON_BOOT")
    retrain_interval_minutes: int = Field(default=5, alias="RETRAIN_INTERVAL_MINUTES")
    trainer_poll_seconds: int = Field(default=3, alias="TRAINER_POLL_SECONDS")
    sim_default_rate: float = Field(default=6.0, alias="SIM_DEFAULT_RATE")

    # --- api / serving ---
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="PORT")
    api_url: str = Field(default="http://localhost:8000", alias="API_URL")
    model_reload_seconds: int = Field(default=5, alias="MODEL_RELOAD_SECONDS")
    als_candidates: int = Field(default=300, alias="ALS_CANDIDATES")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # recency weighting in training: recent behaviour dominates so the model
    # visibly adapts when preferences shift (lower = faster adaptation).
    recency_halflife_days: float = Field(default=3.0, alias="RECENCY_HALFLIFE_DAYS")
    # cap retrain input to the most recent N events so sustained live traffic
    # can't grow training time/memory unbounded (recency weighting already
    # discounts old events, so this loses almost nothing).
    # Train on the most recent N events. Kept well below the storage retention so
    # retrains reflect *recent* behavior quickly — a freshly-injected preference
    # shift becomes a meaningful fraction of the training window within seconds,
    # so the model (and the dashboard) adapt visibly. Plenty of data for this
    # catalog size; raise it for larger catalogs where more history helps.
    train_max_events: int = Field(default=40_000, alias="TRAIN_MAX_EVENTS")
    # keep the serialized artifact (bytea) for only the most recent N versions;
    # older rows keep their metrics (for the timeline) but free the ~1.4 MB blob.
    keep_model_artifacts: int = Field(default=12, alias="KEEP_MODEL_ARTIFACTS")
    # cap the events table: after each retrain, trim to the most recent N events
    # (training only uses the recent window and metrics windows are short, so old
    # rows are dead weight). 0 disables pruning.
    event_retention: int = Field(default=600_000, alias="EVENT_RETENTION")

    # --- ranking / rerank knobs ---
    rerank_max_per_genre: int = Field(default=3, alias="RERANK_MAX_PER_GENRE")
    rerank_max_per_creator: int = Field(default=2, alias="RERANK_MAX_PER_CREATOR")
    rerank_fresh_slots: int = Field(default=2, alias="RERANK_FRESH_SLOTS")
    session_history_len: int = Field(default=20, alias="SESSION_HISTORY_LEN")

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise a bare ``postgres://`` (Railway style) to psycopg3 driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
