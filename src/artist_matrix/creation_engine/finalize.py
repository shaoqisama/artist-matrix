"""Helpers for building Suno payloads from track drafts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from artist_matrix.creation_engine.ideation import TrackIdeationDraft
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state.jobs import TrackJobSpec


@dataclass(frozen=True)
class SunoPayloadPreview:
    title: str
    prompt: str
    style: str | None
    tags: tuple[str, ...]
    negative_tags: tuple[str, ...]
    instrumental: bool
    custom_mode: bool
    lyrics: str | None
    model: str | None

    def as_json(self) -> Mapping[str, object]:
        return {
            "title": self.title,
            "prompt": self.prompt,
            "style": self.style,
            "tags": self.tags,
            "negativeTags": self.negative_tags,
            "instrumental": self.instrumental,
            "customMode": self.custom_mode,
            "lyrics": self.lyrics,
            "model": self.model,
        }


def build_suno_preview(
    profile: ArtistProfile,
    draft: TrackIdeationDraft,
    track_spec: TrackJobSpec,
) -> SunoPayloadPreview:
    prompt = draft.prompt or track_spec.narrative or track_spec.title
    style = draft.style or track_spec.mood or profile.lyric_style
    tags = tuple(draft.tags) if draft.tags else tuple(track_spec.references)
    negative = tuple(draft.negative_tags)
    instrumental = draft.instrumental
    lyrics = draft.lyrics
    model = draft.model
    return SunoPayloadPreview(
        title=draft.title or track_spec.title,
        prompt=prompt or track_spec.title,
        style=style,
        tags=tags,
        negative_tags=negative,
        instrumental=instrumental,
        custom_mode=draft.custom_mode,
        lyrics=lyrics,
        model=model,
    )


__all__ = ["SunoPayloadPreview", "build_suno_preview"]
