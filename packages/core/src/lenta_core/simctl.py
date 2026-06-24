"""Simulator control state in Redis (shared by api control plane + trainer loop).

The api writes desired state (running, rate, scenario); the trainer's live
simulator reads it every tick and acts. ``scenario_seq`` increments on each new
scenario request so the trainer applies a scenario exactly once.
"""

from __future__ import annotations

from typing import Any

from .config import settings

_KEY = "sim:control"

_DEFAULTS = {
    "running": "0",
    "rate": "",  # filled from settings on read
    "scenario": "baseline",
    "intensity": "1.0",
    "emitted": "0",
    "scenario_seq": "0",
}


def get_sim(r: Any) -> dict:
    raw = r.hgetall(_KEY) or {}
    out = dict(_DEFAULTS)
    out["rate"] = str(settings.sim_default_rate)
    out.update(raw)
    return {
        "running": out["running"] in ("1", "true", "True"),
        "rate": float(out["rate"]) if out["rate"] else settings.sim_default_rate,
        "scenario": out["scenario"],
        "intensity": float(out["intensity"]),
        "emitted": int(out["emitted"]),
        "scenario_seq": int(out["scenario_seq"]),
    }


def set_running(r: Any, running: bool, rate: float | None = None) -> None:
    mapping: dict[str, Any] = {"running": "1" if running else "0"}
    if rate is not None:
        mapping["rate"] = str(rate)
    r.hset(_KEY, mapping=mapping)


def set_rate(r: Any, rate: float) -> None:
    r.hset(_KEY, mapping={"rate": str(rate)})


def request_scenario(r: Any, scenario: str, intensity: float) -> int:
    seq = r.hincrby(_KEY, "scenario_seq", 1)
    r.hset(_KEY, mapping={"scenario": scenario, "intensity": str(intensity)})
    return int(seq)


def incr_emitted(r: Any, n: int = 1) -> None:
    r.hincrby(_KEY, "emitted", n)


def reset(r: Any) -> None:
    r.delete(_KEY)
