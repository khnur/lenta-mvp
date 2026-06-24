from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from lenta_core.config import settings
from lenta_core.features.session import read_session_features, update_session
from lenta_core.ingest import insert_event
from lenta_core.models import Video
from lenta_core.schemas import EventAck, EventIn

from ..ab import assign_variant
from ..deps import get_db, get_redis, get_state
from ..state import AppState

router = APIRouter(tags=["ingestion"])


def _primary_genre(state: AppState, db: Session, video_id: int) -> str:
    if state.model.ready:
        ii = state.model.bundle.item_index(video_id)
        if ii is not None:
            return state.model.bundle.genre_names[int(state.model.bundle.item_primary[ii])]
    v = db.get(Video, video_id)
    if v and v.genres:
        return v.genres[0]
    return "unknown"


@router.post("/event", response_model=EventAck)
def post_event(
    ev: EventIn,
    db: Session = Depends(get_db),
    state: AppState = Depends(get_state),
    r=Depends(get_redis),
) -> EventAck:
    variant = ev.variant or assign_variant(db, ev.user_id)
    row = insert_event(
        db,
        {
            "user_id": ev.user_id,
            "video_id": ev.video_id,
            "event_type": ev.event_type,
            "watch_seconds": ev.watch_seconds,
            "watch_fraction": ev.watch_fraction,
            "session_id": ev.session_id,
            "variant": variant,
            "ts": ev.ts,
            "context": ev.context,
        },
    )
    db.commit()

    # Session state = recently *watched* genres, so only plays advance it. This
    # matches how the trainer reconstructs session features (train/serve parity).
    if ev.event_type == "play":
        ts = ev.ts or row.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        update_session(
            r,
            ev.session_id,
            user_id=ev.user_id,
            primary_genre=_primary_genre(state, db, ev.video_id),
            watch_fraction=ev.watch_fraction,
            ts_epoch=ts.timestamp(),
            history_len=settings.session_history_len,
        )
    return EventAck(event_id=row.id, session_features=read_session_features(r, ev.session_id))
