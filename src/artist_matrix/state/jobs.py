"""Job specification dataclasses for Artist Matrix production pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class TrackJobSpec:
    """Parameters describing a track generation request."""

    title: str
    mood: str
    tempo_bpm: int | None = None
    key: str | None = None
    references: Sequence[str] = ()
    narrative: str | None = None


@dataclass(frozen=True)
class ArtworkJobSpec:
    """Parameters describing an artwork render request."""

    title: str
    style: str
    references: Sequence[str] = ()
    seed: int | None = None


__all__ = ["TrackJobSpec", "ArtworkJobSpec"]
