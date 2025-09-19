"""Creation Engine service orchestrating lyrics, audio, and artwork production."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, MutableMapping

from artist_matrix.interfaces.production import (
    ArtworkArtifact,
    ArtworkGenerator,
    AudioGenerator,
    LyricDraft,
    LyricGenerator,
    TrackArtifact,
)
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state.jobs import ArtworkJobSpec, TrackJobSpec

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TRACK_DATA_ROOT = _PROJECT_ROOT / "data" / "artists"


@dataclass(frozen=True)
class CreationBrief:
    """Input describing the track and artwork jobs to run."""

    track: TrackJobSpec
    artwork: ArtworkJobSpec | None = None
    narrative: str | None = None


class TrackManifestRepository:
    """Persist track manifests under per-artist directories."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or _TRACK_DATA_ROOT

    def save(
        self,
        *,
        profile: ArtistProfile,
        track: TrackArtifact,
        lyrics: LyricDraft,
        artwork: ArtworkArtifact | None,
        brief: CreationBrief,
        created_at: datetime,
    ) -> Path:
        artist_root = self.base_path / profile.slug / "tracks"
        artist_root.mkdir(parents=True, exist_ok=True)
        track_slug = track.title.lower().replace(" ", "-")
        manifest_path = artist_root / f"{track_slug}.json"
        manifest: MutableMapping[str, object] = {
            "artist": profile.slug,
            "title": track.title,
            "created_at": created_at.isoformat(),
            "track": {
                "audio_path": str(track.audio_path),
                "duration_seconds": track.duration_seconds,
                "preview_url": track.preview_url,
            },
            "lyrics": {
                "title": lyrics.title,
                "body": lyrics.body,
                "references": list(lyrics.references),
            },
            "track_job": {
                "mood": brief.track.mood,
                "tempo_bpm": brief.track.tempo_bpm,
                "key": brief.track.key,
                "references": list(brief.track.references),
                "narrative": brief.track.narrative,
            },
        }
        if brief.narrative:
            manifest["narrative"] = brief.narrative
        if artwork:
            manifest["artwork"] = {
                "title": artwork.title,
                "image_path": str(artwork.image_path),
                "prompt": artwork.prompt,
                "seed": artwork.seed,
            }
            if brief.artwork is not None:
                manifest["artwork_job"] = {
                    "style": brief.artwork.style,
                    "references": list(brief.artwork.references),
                    "seed": brief.artwork.seed,
                }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest_path


class CreationEngineService:
    """Coordinates lyric, audio, and artwork generation for a profile."""

    def __init__(
        self,
        *,
        lyric_generator: LyricGenerator,
        audio_generator: AudioGenerator,
        artwork_generator: ArtworkGenerator | None = None,
        repository: TrackManifestRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.lyric_generator = lyric_generator
        self.audio_generator = audio_generator
        self.artwork_generator = artwork_generator
        self.repository = repository or TrackManifestRepository()
        self._clock = clock or datetime.utcnow

    def produce_track(
        self,
        profile: ArtistProfile,
        brief: CreationBrief,
    ) -> Mapping[str, object]:
        lyrics = self.lyric_generator.generate_lyrics(profile, brief.track)
        track = self.audio_generator.render_track(profile, brief.track, lyrics)

        artwork = None
        if self.artwork_generator and brief.artwork is not None:
            artwork = self.artwork_generator.render_artwork(profile, brief.artwork, track)

        manifest_path = self.repository.save(
            profile=profile,
            track=track,
            lyrics=lyrics,
            artwork=artwork,
            brief=brief,
            created_at=self._clock(),
        )

        return {
            "lyrics": lyrics,
            "track": track,
            "artwork": artwork,
            "manifest_path": manifest_path,
        }


__all__ = ["CreationBrief", "TrackManifestRepository", "CreationEngineService"]
