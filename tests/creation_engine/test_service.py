from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from artist_matrix.interfaces.production import ArtworkArtifact, LyricDraft, TrackArtifact
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state.jobs import ArtworkJobSpec, TrackJobSpec
from artist_matrix.creation_engine import CreationBrief, CreationEngineService, TrackManifestRepository


@pytest.fixture()
def artist_profile() -> ArtistProfile:
    return ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("cyberpunk", "cinematic"),
        lyric_style="synth metal narration",
        visual_style="retro neon",
        influences=("Nine Inch Nails", "Perturbator"),
        safety_notes="Keep it safe",
    )


class StubLyricGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[ArtistProfile, TrackJobSpec]] = []

    def generate_lyrics(self, profile: ArtistProfile, spec: TrackJobSpec) -> LyricDraft:
        self.calls.append((profile, spec))
        return LyricDraft(
            title=spec.title,
            body="Synthetic city lights glow in the ruins",
            references=spec.references,
        )


class StubAudioGenerator:
    def __init__(self, tmp_path: Path) -> None:
        self.calls: list[tuple[ArtistProfile, TrackJobSpec, LyricDraft]] = []
        self.tmp_path = tmp_path

    def render_track(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
        lyrics: LyricDraft,
    ) -> TrackArtifact:
        self.calls.append((profile, spec, lyrics))
        artifact_path = self.tmp_path / f"{spec.title.lower().replace(' ', '_')}.wav"
        artifact_path.write_bytes(b"fake-binary")
        return TrackArtifact(title=spec.title, audio_path=artifact_path, duration_seconds=180.0)


class StubArtworkGenerator:
    def __init__(self, tmp_path: Path) -> None:
        self.calls: list[tuple[ArtistProfile, ArtworkJobSpec, TrackArtifact]] = []
        self.tmp_path = tmp_path

    def render_artwork(
        self,
        profile: ArtistProfile,
        spec: ArtworkJobSpec,
        track: TrackArtifact,
    ) -> ArtworkArtifact:
        self.calls.append((profile, spec, track))
        image_path = self.tmp_path / f"{spec.title.lower().replace(' ', '_')}.png"
        image_path.write_bytes(b"fake-image")
        return ArtworkArtifact(
            title=spec.title,
            image_path=image_path,
            prompt=f"{profile.visual_style} cover art for {track.title}",
            seed=spec.seed,
        )


@pytest.fixture()
def repository(tmp_path: Path) -> TrackManifestRepository:
    return TrackManifestRepository(base_path=tmp_path)


def test_produce_track_creates_manifest_with_artwork(
    artist_profile: ArtistProfile,
    repository: TrackManifestRepository,
    tmp_path: Path,
) -> None:
    lyric_gen = StubLyricGenerator()
    audio_gen = StubAudioGenerator(tmp_path)
    artwork_gen = StubArtworkGenerator(tmp_path)
    fixed_time = datetime(2099, 1, 1, 0, 0, 0)

    service = CreationEngineService(
        lyric_generator=lyric_gen,
        audio_generator=audio_gen,
        artwork_generator=artwork_gen,
        repository=repository,
        clock=lambda: fixed_time,
    )

    brief = CreationBrief(
        track=TrackJobSpec(
            title="Signal Burn",
            mood="fierce",
            tempo_bpm=132,
            key="Am",
            references=("Kavinsky",),
            narrative="A neon vigilante patrols the ruins.",
        ),
        artwork=ArtworkJobSpec(title="Signal Burn", style="retro poster", seed=99),
        narrative="Full asset bundle for synth metal single.",
    )

    result = service.produce_track(artist_profile, brief)
    manifest_path = result["manifest_path"]

    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["artist"] == artist_profile.slug
    assert data["title"] == "Signal Burn"
    assert data["track"]["audio_path"].endswith("signal_burn.wav")
    assert data["artwork"]["image_path"].endswith("signal_burn.png")
    assert data["artwork_job"]["style"] == "retro poster"
    assert data["track_job"]["tempo_bpm"] == 132
    assert data["narrative"] == "Full asset bundle for synth metal single."
    assert data["created_at"] == fixed_time.isoformat()

    assert lyric_gen.calls
    assert audio_gen.calls
    assert artwork_gen.calls


def test_produce_track_without_artwork(
    artist_profile: ArtistProfile,
    repository: TrackManifestRepository,
    tmp_path: Path,
) -> None:
    lyric_gen = StubLyricGenerator()
    audio_gen = StubAudioGenerator(tmp_path)
    service = CreationEngineService(
        lyric_generator=lyric_gen,
        audio_generator=audio_gen,
        artwork_generator=None,
        repository=repository,
        clock=lambda: datetime(2100, 1, 1, 0, 0, 0),
    )

    brief = CreationBrief(
        track=TrackJobSpec(title="Dust Runner", mood="brooding"),
        artwork=None,
    )

    result = service.produce_track(artist_profile, brief)
    manifest_path = result["manifest_path"]

    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "artwork" not in data
    assert "artwork_job" not in data
    assert data["track_job"]["mood"] == "brooding"
