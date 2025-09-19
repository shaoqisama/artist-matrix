"""State management and shared schemas for Artist Matrix workflows."""

from __future__ import annotations

from .jobs import ArtworkJobSpec, TrackJobSpec
from .schemas import ArtistManifest, JobContext, ReleaseManifest, TrackManifest
from .settings import ArtistMatrixSettings

__all__ = [
    "TrackJobSpec",
    "ArtworkJobSpec",
    "ArtistManifest",
    "TrackManifest",
    "ReleaseManifest",
    "JobContext",
    "ArtistMatrixSettings",
]
