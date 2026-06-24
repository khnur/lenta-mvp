"""Item-side feature helpers."""

from __future__ import annotations

from ..mock.catalog import GENRE_PEAK_HOUR


def time_of_day_match(genre_name: str, hour: int) -> float:
    """1.0 when `hour` is the genre's peak hour, decaying to 0 twelve hours away."""
    peak = GENRE_PEAK_HOUR.get(genre_name, 12)
    d = abs(int(hour) - peak)
    d = min(d, 24 - d)
    return 1.0 - d / 12.0
