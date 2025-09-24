"""Protocols for lyric, audio, and artwork production services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state.jobs import ArtworkJobSpec, TrackJobSpec


@dataclass(frozen=True)
class LyricDraft:
    """Represents generated lyrics content."""

    title: str
    body: str
    references: Sequence[str] = ()


@dataclass(frozen=True)
class TrackArtifact:
    """Metadata describing a rendered audio track."""

    title: str
    audio_path: Path
    duration_seconds: float | None = None
    preview_url: str | None = None
    alternates: Sequence[Path] = ()


@dataclass(frozen=True)
class ArtworkArtifact:
    """Metadata describing a produced cover image."""

    title: str
    image_path: Path
    prompt: str
    seed: int | None = None


class LyricGenerator(Protocol):
    """Generates lyric drafts for a given profile and track brief."""

    def generate_lyrics(self, profile: ArtistProfile, spec: TrackJobSpec) -> LyricDraft:
        ...


class AudioGenerator(Protocol):
    """Produces audio tracks from lyrics and track specs."""

    def render_track(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
        lyrics: LyricDraft,
    ) -> TrackArtifact:
        ...


class ArtworkGenerator(Protocol):
    """Produces cover artwork aligned with a profile and track."""

    def render_artwork(
        self,
        profile: ArtistProfile,
        spec: ArtworkJobSpec,
        track: TrackArtifact,
    ) -> ArtworkArtifact:
        ...


__all__ = [
    "LyricDraft",
    "TrackArtifact",
    "ArtworkArtifact",
    "LyricGenerator",
    "AudioGenerator",
    "ArtworkGenerator",
]
