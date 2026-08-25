from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from artist_matrix.interfaces.production import LyricDraft, TrackArtifact
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.tui import SessionState, TuiApp


class _StubCreationEngine:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.calls = 0

    def produce_track(self, profile: ArtistProfile, brief):  # pragma: no cover - duck typing
        self.calls += 1
        manifest_path = self.tmp_path / "manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        track_path = self.tmp_path / "track.wav"
        track_path.write_text("audio", encoding="utf-8")
        track = TrackArtifact(
            title=brief.track.title, audio_path=track_path, duration_seconds=186.0
        )
        lyrics = LyricDraft(
            title=brief.track.title, body="lyrics", references=brief.track.references
        )
        return {
            "manifest_path": manifest_path,
            "track": track,
            "lyrics": lyrics,
            "logs": (),
        }


class _StubLLM:
    def chat(self, persona_summary: str, prompt: str, transcript):  # pragma: no cover - duck typing
        assert persona_summary
        assert transcript
        return """
```
{
  "title": "Signal Bloom",
  "style": "glossy synthwave",
  "tags": ["neon", "pulse"],
  "lyrics": "glow in the ultralight"
}
```
"""


@pytest.fixture()
def workbench_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(tmp_path))
    session = SessionState()
    profile = ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("retro",),
        lyric_style="synthwave narratives",
        visual_style="neon glitch",
        influences=("Kavinsky", "Gunship"),
    )
    session.last_profile = profile
    return session, profile, tmp_path


def test_workbench_chat_adopt_finalize(workbench_env) -> None:
    session, profile, tmp_path = workbench_env

    inputs: Iterator[str] = iter(
        [
            "Let's craft a neon anthem",
            "/adopt",
            "/edit notes: airy vocals",
            "/undo",
            "/edit notes: airy vocals",
            "/show",
            "/finalize",
            "y",
            "m",
        ]
    )
    captured: list[str] = []

    app = TuiApp(
        input_func=lambda _: next(inputs),
        output_func=captured.append,
        creation_service=_StubCreationEngine(tmp_path),
        session=session,
    )
    app.ideation_llm = _StubLLM()

    app.handle_creation_workbench()

    draft = session.track_draft
    assert draft is not None
    assert draft.title == "Signal Bloom"
    assert tuple(draft.tags) == ("neon", "pulse")
    assert draft.notes and draft.notes[-1] == "airy vocals"

    # ensure files persisted for the persona
    draft_path = tmp_path / "artists" / profile.slug / "drafts" / "latest_draft.json"
    assert draft_path.exists()

    # creation engine invoked
    assert app.creation_engine.calls == 1  # type: ignore[attr-defined]

    summary = "\n".join(captured)
    assert "AI suggests (use /adopt to apply):" in summary
    assert "Adopted" in summary
    assert "Creation Engine complete" in summary
