"""SQLAlchemy ORM models — the single source of truth for the schema.

Tables: users, videos, events, model_versions, experiments, jobs, pipeline_runs.
JSONB / bytea are Postgres-native (this MVP targets Postgres).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# Event type vocabulary (kept as plain strings for portability).
EVENT_IMPRESSION = "impression"
EVENT_CLICK = "click"
EVENT_PLAY = "play"

VARIANT_CONTROL = "control"      # popularity baseline
VARIANT_TREATMENT = "treatment"  # full recommender funnel


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    cohort: Mapped[str] = mapped_column(String(32), default="default", index=True)
    # latent per-genre affinity vector (length == n_genres); used only by the simulator
    affinity: Mapped[list] = mapped_column(JSONB, default=list)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    events: Mapped[list["Event"]] = relationship(back_populates="user")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    creator_id: Mapped[int] = mapped_column(Integer, index=True)
    genres: Mapped[list] = mapped_column(JSONB, default=list)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    upload_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    base_popularity: Mapped[float] = mapped_column(Float, default=0.0)

    events: Mapped[list["Event"]] = relationship(back_populates="video")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(16))  # impression | click | play
    watch_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    watch_fraction: Mapped[float] = mapped_column(Float, default=0.0)  # [0, 1]
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    variant: Mapped[str] = mapped_column(String(16), default=VARIANT_TREATMENT, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship(back_populates="events")
    video: Mapped["Video"] = relationship(back_populates="events")


Index("ix_events_user_ts", Event.user_id, Event.ts)
Index("ix_events_type_ts", Event.event_type, Event.ts)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, index=True)  # monotonically increasing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    algo: Mapped[str] = mapped_column(String(64), default="als+lightgbm")
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    artifact: Mapped[bytes] = mapped_column(LargeBinary)  # serialized model bundle (bytea)
    artifact_bytes: Mapped[int] = mapped_column(Integer, default=0)
    train_rows: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[str] = mapped_column(String(512), default="")


# At most one active model version at a time (defense-in-depth alongside the
# trainer's retrain lock): a partial unique index over the rows where is_active.
Index(
    "uq_model_versions_active",
    ModelVersion.is_active,
    unique=True,
    postgresql_where=ModelVersion.is_active.is_(True),
)


class Experiment(Base):
    """A/B assignment: one row per user, sticky variant."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    variant: Mapped[str] = mapped_column(String(16))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Job(Base):
    """Control-plane jobs (retrain triggers) the trainer polls for."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32))  # retrain | seed | reset
    status: Mapped[str] = mapped_column(
        String(16), default="queued", index=True
    )  # queued | running | done | failed
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineRun(Base):
    """Stage runs for the pipeline-status panel."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(
        String(32), index=True
    )  # ingest | feature_update | retrain | deploy
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | ok | error
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


def utcnow() -> datetime:
    """Public helper so services don't re-import datetime/timezone."""
    return _utcnow()
