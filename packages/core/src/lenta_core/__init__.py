"""lenta_core — shared library for the lenta-mvp recommendation system.

One source of truth for: db schema, features, ALS + LightGBM training/scoring,
offline/online eval, the Postgres model registry, and mock-data generation.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import settings  # noqa: E402

__all__ = ["settings", "__version__"]
