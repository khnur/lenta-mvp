"""Models: ALS retrieval, content fallback, popularity baseline, LightGBM
ranker, and the serving funnel. The serialized :class:`ModelBundle` is the unit
stored in the Postgres registry."""

from .artifacts import ModelBundle
from .als import train_als
from .ranker import train_ranker
from .funnel import recommend

__all__ = ["ModelBundle", "train_als", "train_ranker", "recommend"]
