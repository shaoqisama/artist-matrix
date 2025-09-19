"""Shared Pydantic schemas for Artist Matrix workflows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from pydantic import BaseModel, Field


class ArtistManifest(BaseModel):
    name: str
    slug: str
    persona_tags: Sequence[str]
    lyric_style: str
    visual_style: str
    influences: Sequence[str]
    safety_notes: str | None = None


class TrackManifest(BaseModel):
    title: str
    mood: str
    tempo_bpm: int | None = None
    key: str | None = None
    references: Sequence[str] = Field(default_factory=tuple)
    narrative: str | None = None
    audio_path: str
    artwork_path: str | None = None
    created_at: datetime
    manifest_path: str


class ReleaseManifest(BaseModel):
    title: str
    artist_slug: str
    release_date: date
    platforms: Sequence[str]
    track_manifest_path: str
    artwork_path: str | None = None
    description: str | None = None
    receipts: Sequence[dict[str, Any]]


class JobContext(BaseModel):
    artist: ArtistManifest
    track: TrackManifest | None = None
    release: ReleaseManifest | None = None
    last_event: str | None = None
    errors: Sequence[str] = Field(default_factory=tuple)


__all__ = [
    "ArtistManifest",
    "TrackManifest",
    "ReleaseManifest",
    "JobContext",
]
