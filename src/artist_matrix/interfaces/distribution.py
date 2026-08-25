"""Protocols for music distribution and analytics reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol, Sequence

from artist_matrix.soul_forge import ArtistProfile


@dataclass(frozen=True)
class ReleaseSpec:
    """Describes a release to be distributed across platforms."""

    title: str
    release_date: date
    platforms: Sequence[str]
    track_manifest: Path
    artwork_path: Path | None = None
    description: str | None = None


@dataclass(frozen=True)
class DistributionReceipt:
    """Represents a platform-specific acknowledgement."""

    platform: str
    external_id: str
    dashboard_url: str | None = None


class DistributionClient(Protocol):
    """Interface for uploading releases to streaming platforms."""

    platform: str

    def submit_release(self, profile: ArtistProfile, spec: ReleaseSpec) -> DistributionReceipt: ...


class ReleaseAnalytics(Protocol):
    """Interface for recording release analytics."""

    def record(
        self, profile: ArtistProfile, spec: ReleaseSpec, receipt: DistributionReceipt
    ) -> None: ...


__all__ = [
    "ReleaseSpec",
    "DistributionReceipt",
    "DistributionClient",
    "ReleaseAnalytics",
]
