"""Pydantic models shared across the api boundary and tests."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


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
class EventIn(BaseModel):
    user_id: int
    video_id: int
    event_type: Literal["impression", "click", "play"]
    session_id: str
    watch_seconds: float = 0.0
    watch_fraction: float = Field(0.0, ge=0.0, le=1.0)
    variant: str | None = None
    ts: datetime | None = None
    context: dict[str, Any] | None = None


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
    rate: float | None = Field(None, description="events/sec")


class SimStatus(BaseModel):
    running: bool
    rate: float
    scenario: str
    emitted: int
    updated_at: datetime | None = None
