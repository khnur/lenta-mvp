"""Postgres-backed model registry.

The serialized :class:`ModelBundle` is stored as ``bytea`` so services need no
shared filesystem/volume (Railway volumes attach to a single service).
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import settings
from .logging_conf import get_logger
from .ml.artifacts import ModelBundle
from .models import ModelVersion

log = get_logger("lenta.registry")


def next_version(session: Session) -> int:
    cur = session.execute(select(ModelVersion.version).order_by(ModelVersion.version.desc())).first()
    return (cur[0] + 1) if cur else 1


def save_model_version(
    session: Session,
    bundle: ModelBundle,
    *,
    metrics: dict,
    train_rows: int,
    set_active: bool = True,
    notes: str = "",
) -> ModelVersion:
    blob = bundle.to_bytes()
    mv = ModelVersion(
        version=bundle.version,
        algo=bundle.algo,
        metrics=metrics,
        artifact=blob,
        artifact_bytes=len(blob),
        train_rows=train_rows,
        is_active=False,
        notes=notes,
    )
    session.add(mv)
    session.flush()
    if set_active:
        session.execute(update(ModelVersion).values(is_active=False))
        mv.is_active = True
    session.flush()

    # Bound storage: free the bytea of versions older than the retention window
    # (keep their metrics rows for the model timeline). Never touch the active one.
    keep = max(1, settings.keep_model_artifacts)
    freed = session.execute(
        update(ModelVersion)
        .where(
            ModelVersion.version <= mv.version - keep,
            ModelVersion.artifact_bytes > 0,
            ModelVersion.is_active.is_(False),
        )
        .values(artifact=b"", artifact_bytes=0)
    ).rowcount
    if freed:
        log.info("pruned artifacts of %d old model version(s)", freed)
    log.info("saved model v%d (%d bytes, active=%s)", mv.version, len(blob), set_active)
    return mv


def load_active_model(session: Session) -> tuple[ModelVersion, ModelBundle] | None:
    mv = (
        session.execute(
            select(ModelVersion).where(ModelVersion.is_active.is_(True)).order_by(
                ModelVersion.version.desc()
            )
        )
        .scalars()
        .first()
    )
    if mv is None:
        return None
    return mv, ModelBundle.from_bytes(mv.artifact)


def active_version(session: Session) -> int | None:
    row = session.execute(
        select(ModelVersion.version).where(ModelVersion.is_active.is_(True)).order_by(
            ModelVersion.version.desc()
        )
    ).first()
    return int(row[0]) if row else None


def list_versions(session: Session, limit: int = 50) -> list[ModelVersion]:
    return list(
        session.execute(
            select(ModelVersion).order_by(ModelVersion.version.desc()).limit(limit)
        ).scalars()
    )


def load_version(session: Session, version: int) -> tuple[ModelVersion, ModelBundle] | None:
    mv = session.execute(
        select(ModelVersion).where(ModelVersion.version == version)
    ).scalars().first()
    if mv is None:
        return None
    return mv, ModelBundle.from_bytes(mv.artifact)
