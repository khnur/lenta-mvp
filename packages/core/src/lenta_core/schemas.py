"""Pydantic models shared across the api boundary and tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Serving                                                                      #
# --------------------------------------------------------------------------- #
class VideoOut(BaseModel):
    id: int
    title: str
    creator_id: int
    genres: list[str]
    tags: list[str] = []
    duration_seconds: int
    upload_time: datetime
    score: float = Field(0.0, description="ranker-predicted watch fraction")
    stage: str = Field("ranked", description="how this item entered the feed")


class FunnelDebug(BaseModel):
    """Per-stage counts so the dashboard can show the funnel working."""

    catalog: int
    candidates: int
    ranked: int
    feed: int
    retrieval: str  # "als" | "content" | "popularity"
    model_version: int | None = None
    cold_start: bool = False
    latency_ms: float = 0.0


class FeedResponse(BaseModel):
    user_id: int
    variant: str
    k: int
    items: list[VideoOut]
    funnel: FunnelDebug


# --------------------------------------------------------------------------- #
# Ingestion                                                                    #
# --------------------------------------------------------------------------- #
# users.id / videos.id are Postgres INTEGER columns; an id beyond int32 can't
# match a real row and would overflow the column (DataError -> 500), so bound
# the request ids here and reject them with a clean 422 instead.
PG_INT32_MAX = 2_147_483_647


class EventIn(BaseModel):
    user_id: int = Field(ge=1, le=PG_INT32_MAX)
    video_id: int = Field(ge=1, le=PG_INT32_MAX)
    event_type: Literal["impression", "click", "play"]
    # bounded to the DB column (varchar 64) so an oversized value is rejected with
    # a clean 422 instead of overflowing the column and surfacing as a 500.
    session_id: str = Field(min_length=1, max_length=64)
    # allow_inf_nan=False: reject NaN/Infinity, which otherwise poison the float
    # columns / metrics and break JSON response serialization (500).
    watch_seconds: float = Field(0.0, ge=0.0, allow_inf_nan=False)
    watch_fraction: float = Field(0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    # only the two A/B variants are valid; anything else (incl. an over-length
    # string) is a 422, matching the /feed contract and never reaching the DB.
    variant: str | None = Field(None, pattern="^(control|treatment)$")
    ts: datetime | None = None
    context: dict[str, Any] | None = None

    @field_validator("ts")
    @classmethod
    def _ts_in_sane_range(cls, v: datetime | None) -> datetime | None:
        """Reject a nonsensical event timestamp. A far-future ts (e.g. year 9999)
        is stored fine but overflows pandas (~2262) when the trainer loads it,
        which used to fail the whole retrain — bound it at the door instead."""
        if v is None:
            return v
        vv = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        lo = datetime(2000, 1, 1, tzinfo=timezone.utc)
        hi = datetime.now(timezone.utc) + timedelta(days=1)  # allow minor clock skew
        if not (lo <= vv <= hi):
            raise ValueError("ts must be between 2000-01-01 and ~now")
        return v


class EventAck(BaseModel):
    ok: bool = True
    event_id: int
    session_features: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Metrics / registry / pipeline                                               #
# --------------------------------------------------------------------------- #
class VariantMetrics(BaseModel):
    variant: str
    impressions: int
    clicks: int
    plays: int
    ctr: float
    avg_watch_seconds: float
    avg_watch_fraction: float
    avg_session_length: float


class MetricsResponse(BaseModel):
    window_minutes: int
    overall: VariantMetrics
    per_variant: list[VariantMetrics]
    lift: dict[str, float] = {}  # treatment-vs-control lift


class ModelInfo(BaseModel):
    id: int
    version: int
    created_at: datetime
    algo: str
    is_active: bool
    artifact_bytes: int
    train_rows: int
    notes: str
    metrics: dict[str, float]


class ModelsResponse(BaseModel):
    active_version: int | None
    versions: list[ModelInfo]


class RetrainAck(BaseModel):
    ok: bool = True
    job_id: int
    status: str


class PipelineStageStatus(BaseModel):
    stage: str
    status: str
    last_run: datetime | None = None
    duration_ms: int | None = None
    detail: dict[str, Any] | None = None


class PipelineStatusResponse(BaseModel):
    stages: list[PipelineStageStatus]
    active_model_version: int | None = None
    total_events: int = 0
    runs: list[PipelineStageStatus] = []  # recent run history


# --------------------------------------------------------------------------- #
# Simulator control                                                            #
# --------------------------------------------------------------------------- #
class SimScenarioIn(BaseModel):
    scenario: Literal["genre_shift", "new_content_surge", "cold_start_wave", "baseline"]
    intensity: float = Field(1.0, ge=0.0, le=5.0)


class SimControlIn(BaseModel):
    # positive and bounded: reject negative / zero / absurd rates that would
    # either stall the simulator or hammer the API (None = keep current rate).
    rate: float | None = Field(None, gt=0, le=1000, description="events/sec")


class SimStatus(BaseModel):
    running: bool
    rate: float
    scenario: str
    emitted: int
    updated_at: datetime | None = None
