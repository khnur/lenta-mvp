from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from lenta_core.registry import active_version, list_versions
from lenta_core.schemas import ModelInfo, ModelsResponse

from ..deps import get_db

router = APIRouter(tags=["registry"])

_NUMERIC_METRICS = (
    "recall_at_k", "ndcg_at_k", "coverage", "diversity", "k", "n_users", "train_events"
)


@router.get("/models", response_model=ModelsResponse)
def get_models(db: Session = Depends(get_db)) -> ModelsResponse:
    versions = list_versions(db)
    infos = [
        ModelInfo(
            id=mv.id,
            version=mv.version,
            created_at=mv.created_at,
            algo=mv.algo,
            is_active=mv.is_active,
            artifact_bytes=mv.artifact_bytes,
            train_rows=mv.train_rows,
            notes=mv.notes,
            metrics={
                kk: float(mv.metrics[kk])
                for kk in _NUMERIC_METRICS
                if isinstance(mv.metrics.get(kk), (int, float))
            },
        )
        for mv in versions
    ]
    return ModelsResponse(active_version=active_version(db), versions=infos)
