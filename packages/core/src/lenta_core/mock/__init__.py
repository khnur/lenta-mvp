"""Mock-data generation: catalog, users with latent affinities, and a
behaviour simulator that produces realistic implicit signals."""

from .catalog import GENRES, GENRE_PEAK_HOUR, generate_catalog
from .users import generate_users
from .simulate import (
    World,
    inject_new_content,
    inject_new_users,
    simulate_backfill,
)

__all__ = [
    "GENRES",
    "GENRE_PEAK_HOUR",
    "generate_catalog",
    "generate_users",
    "World",
    "simulate_backfill",
    "inject_new_content",
    "inject_new_users",
]
