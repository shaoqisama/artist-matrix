from __future__ import annotations

from pathlib import Path
from typing import Iterator

from artist_matrix.creation_engine import CreationBrief
from artist_matrix.interfaces.production import LyricDraft, TrackArtifact
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state.jobs import ArtworkJobSpec, TrackJobSpec
from artist_matrix.tui.app import SessionState, TuiApp


class RecordingCreationEngine:
    def __init__(self, manifest_path: Path, audio_path: Path) -> None:
        self.calls: list[tuple[ArtistProfile, CreationBrief]] = []
        self.manifest_path = manifest_path
        self.audio_path = audio_path
        self.log_dir = manifest_path.parent / "logs"

    def produce_track(
        self,
        profile: ArtistProfile,
        brief: CreationBrief,
    ) -> dict[str, object]:
        self.calls.append((profile, brief))
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text("{}", encoding="utf-8")
        self.audio_path.parent.mkdir(parents=True, exist_ok=True)
        self.audio_path.write_bytes(b"audio")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / "test-log.json"
        log_path.write_text("{\n  \"status\": \"SUCCESS\"\n}", encoding="utf-8")
        return {
            "lyrics": LyricDraft(title=brief.track.title, body="line one\nline two"),
            "track": TrackArtifact(
                title=brief.track.title,
                audio_path=self.audio_path,
                duration_seconds=120.0,
            ),
            "manifest_path": self.manifest_path,
            "logs": (log_path,),
        }


def test_handle_creation_engine_invokes_service(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ARTIST_MATRIX_PERSONA_PROVIDER", "stub")
    monkeypatch.setenv("ARTIST_MATRIX_CREATION_AUDIO_PROVIDER", "stub")
    profile = ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("cyberpunk",),
        lyric_style="synth metal narration",
        visual_style="retro neon",
        influences=("Perturbator",),
    )
    brief = CreationBrief(
        track=TrackJobSpec(title="Signal Burn", mood="fierce", references=("future",)),
        artwork=ArtworkJobSpec(title="Signal Burn", style="retro"),
    )

    manifest_path = tmp_path / "artists" / profile.slug / "tracks" / "signal_burn.json"
    audio_path = tmp_path / "artists" / profile.slug / "tracks" / "signal_burn.mp3"
    fake_engine = RecordingCreationEngine(manifest_path, audio_path)

    inputs: Iterator[str] = iter(["y", "m"])
    outputs: list[str] = []

    session = SessionState(last_profile=profile, track_brief=brief)
    app = TuiApp(
        input_func=lambda prompt: next(inputs),
        output_func=outputs.append,
        creation_service=fake_engine,  # type: ignore[arg-type]
        session=session,
    )

    app.handle_creation_engine()

    assert fake_engine.calls
    assert session.last_track_manifest == manifest_path
    joined_output = "\n".join(outputs)
    assert "Creation Engine complete" in joined_output
    assert str(manifest_path) in joined_output
    assert str(audio_path) in joined_output
    assert "Logs captured" in joined_output
