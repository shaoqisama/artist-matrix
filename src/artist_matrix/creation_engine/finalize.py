"""Helpers for building Suno payloads from track drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from artist_matrix.creation_engine.ideation import TrackIdeationDraft


@dataclass(frozen=True)
class SunoPayloadPreview:
    title: str
    style: str | None
    tags: tuple[str, ...]
    lyrics: str | None
    notes: tuple[str, ...]
    duration_sec: int | None
    allow_instrumental: bool
    ref_url: str | None

    def as_json(self) -> Mapping[str, object]:
        return {
            "title": self.title,
            "style": self.style,
            "tags": list(self.tags),
            "lyrics": self.lyrics,
            "notes": list(self.notes),
            "duration_sec": self.duration_sec,
            "allow_instrumental": self.allow_instrumental,
            "reference_url": self.ref_url,
        }


def build_suno_preview(draft: TrackIdeationDraft) -> SunoPayloadPreview:
    return SunoPayloadPreview(
        title=draft.title or "Untitled Track",
        style=draft.style,
        tags=tuple(draft.tags),
        lyrics=draft.lyrics,
        notes=tuple(draft.notes),
        duration_sec=draft.duration_sec,
        allow_instrumental=draft.allow_instrumental,
        ref_url=draft.ref_url,
    )


__all__ = ["SunoPayloadPreview", "build_suno_preview"]
