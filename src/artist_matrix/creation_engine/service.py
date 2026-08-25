"""Creation Engine service orchestrating lyrics, audio, and artwork production."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
_SLUG_SEPARATOR = re.compile(r"[^a-z0-9]+")


def _safe_slug(value: str, *, fallback: str) -> str:
    slug = _SLUG_SEPARATOR.sub("-", value.lower().strip()).strip("-")
    return slug or fallback


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
        track_slug = _safe_slug(track.title, fallback="track")
        manifest_path = artist_root / f"{track_slug}.json"
        track_section: MutableMapping[str, object] = {
            "audio_path": str(track.audio_path),
            "duration_seconds": track.duration_seconds,
            "preview_url": track.preview_url,
        }
        manifest: MutableMapping[str, object] = {
            "artist": profile.slug,
            "title": track.title,
            "created_at": created_at.isoformat(),
            "track": track_section,
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
        if track.alternates:
            track_section["alternates"] = [str(path) for path in track.alternates]
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
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def produce_track(
        self,
        profile: ArtistProfile,
        brief: CreationBrief,
    ) -> Mapping[str, object]:
        lyrics = self.lyric_generator.generate_lyrics(profile, brief.track)
        track = self.audio_generator.render_track(profile, brief.track, lyrics)
        logs: tuple[Path, ...] = ()
        last_logs_getter = getattr(self.audio_generator, "last_run_logs", None)
        if callable(last_logs_getter):
            try:
                logs = tuple(Path(p) for p in last_logs_getter())
            except Exception:  # noqa: BLE001
                logs = ()

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
            "logs": logs,
        }


__all__ = ["CreationBrief", "TrackManifestRepository", "CreationEngineService"]
