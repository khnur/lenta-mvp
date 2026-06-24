"""Mock-data generator tests: determinism + a learnable behavioural signal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from lenta_core.mock.catalog import generate_catalog
from lenta_core.mock.simulate import World, simulate_backfill
from lenta_core.mock.users import generate_users

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _gen(seed):
    rng = np.random.default_rng(seed)
    v = generate_catalog(40, n_genres=8, backfill_days=10, rng=rng, now=NOW)
    u = generate_users(30, n_genres=8, rng=rng, now=NOW)
    return v, u


def test_generators_deterministic():
    v1, u1 = _gen(7)
    v2, u2 = _gen(7)
    assert [x["title"] for x in v1] == [x["title"] for x in v2]
    assert [x["affinity"] for x in u1] == [x["affinity"] for x in u2]


def test_simulate_produces_plausible_signal():
    rng = np.random.default_rng(1)
    v, u = _gen(1)
    world = World.from_rows(u, v, n_genres=8, rng=rng)
    events = simulate_backfill(
        world, 3000, rng=rng, start=NOW - timedelta(days=10), end=NOW
    )
    types = [e["event_type"] for e in events]
    imp = types.count("impression")
    clk = types.count("click")
    ply = types.count("play")
    assert imp > 0 and clk > 0 and ply > 0
    ctr = clk / imp
    assert 0.05 < ctr < 0.9  # plausible click-through
    wfs = [e["watch_fraction"] for e in events if e["event_type"] == "play"]
    assert 0.0 <= np.mean(wfs) <= 1.0


def test_genre_shift_changes_affinity():
    rng = np.random.default_rng(2)
    v, u = _gen(2)
    world = World.from_rows(u, v, n_genres=8, rng=rng)
    before = world.U.copy()
    rep = world.apply_scenario("genre_shift", 3.0, rng)
    assert rep["scenario"] == "genre_shift"
    assert not np.allclose(before, world.U)  # some users' tastes moved
