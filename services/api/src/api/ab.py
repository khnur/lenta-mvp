"""A/B variant assignment: sticky per user, ~50/50 treatment vs control."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lenta_core.models import VARIANT_CONTROL, VARIANT_TREATMENT, Experiment


def _hash_variant(user_id: int) -> str:
    # deterministic, well-mixed split
    h = (int(user_id) * 2_654_435_761) % 100
    return VARIANT_TREATMENT if h < 50 else VARIANT_CONTROL


def assign_variant(session: Session, user_id: int, forced: str | None = None) -> str:
    if forced in (VARIANT_CONTROL, VARIANT_TREATMENT):
        return forced

    row = session.execute(
        select(Experiment).where(Experiment.user_id == user_id)
    ).scalars().first()
    if row:
        return row.variant

    variant = _hash_variant(user_id)
    session.add(Experiment(user_id=user_id, variant=variant))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        row = session.execute(
            select(Experiment).where(Experiment.user_id == user_id)
        ).scalars().first()
        if row:
            return row.variant
    return variant
