"""Protocols for social platform interactions and scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from artist_matrix.soul_forge import ArtistProfile


@dataclass(frozen=True)
class SocialPost:
    """Represents a templated social content payload."""

    platform: str
    content: str
    scheduled_for: datetime | None = None
    media_paths: Sequence[str] = ()


class SocialClient(Protocol):
    """Interface for publishing content to a social platform."""

    platform: str

    def publish(self, post: SocialPost) -> None:
        ...


class AnalyticsClient(Protocol):
    """Interface for recording engagement metrics."""

    def record(self, profile: ArtistProfile, post: SocialPost, *, status: str) -> None:
        ...


__all__ = ["SocialPost", "SocialClient", "AnalyticsClient"]
