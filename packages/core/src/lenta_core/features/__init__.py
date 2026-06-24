"""Feature builders shared by training and serving (train/serve parity).

The ranker's feature vector is defined in exactly one place — :mod:`ranking` —
and used both when building the training matrix and when scoring candidates at
serve time, so they can never drift.
"""

from .ranking import FEATURE_NAMES, CATEGORICAL_FEATURES, feature_row, to_matrix
from .item import time_of_day_match
from .user import build_user_aggregates
from .session import (
    SESSION_TTL_SECONDS,
    read_session_features,
    update_session,
    session_feature_view,
)

__all__ = [
    "FEATURE_NAMES",
    "CATEGORICAL_FEATURES",
    "feature_row",
    "to_matrix",
    "time_of_day_match",
    "build_user_aggregates",
    "SESSION_TTL_SECONDS",
    "read_session_features",
    "update_session",
    "session_feature_view",
]
