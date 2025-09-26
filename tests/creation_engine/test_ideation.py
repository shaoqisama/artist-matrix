from __future__ import annotations

from pathlib import Path

from artist_matrix.creation_engine import (
    ChatTurn,
    TrackIdeationDraft,
    TrackIdeationStore,
    apply_llm_guidance,
)
from artist_matrix.state import ArtistMatrixSettings


def test_save_and_load_draft(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path)
    store = TrackIdeationStore(settings)
    draft = TrackIdeationDraft(persona_slug="neon-wasteland", title="Signal Burn", prompt="Neon city")

    path = store.save_draft(draft)
    assert path.exists()

    loaded = store.load_draft("neon-wasteland")
    assert loaded is not None
    assert loaded.title == "Signal Burn"
    assert loaded.prompt == "Neon city"


def test_transcript_roundtrip(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path)
    store = TrackIdeationStore(settings)
    turns = [
        ChatTurn(role="system", content="Hello"),
        ChatTurn(role="user", content="Let's make a track"),
    ]

    path = store.append_transcript("neon-wasteland", turns)
    assert path.exists()

    replay = store.load_transcript("neon-wasteland")
    assert len(replay) == 2
    assert replay[1].content == "Let's make a track"


def test_apply_llm_guidance_appends_notes() -> None:
    class DummyLLM:
        def chat(self, persona_summary: str, prompt: str, transcript):
            assert "Neon" in persona_summary
            return "Consider layering retro arps."

    draft = TrackIdeationDraft(persona_slug="neon-wasteland", title="Signal Burn")
    turns = [ChatTurn(role="user", content="Add more energy.")]

    response, updated, payload = apply_llm_guidance(DummyLLM(), "Neon Wasteland persona", "Add more energy.", turns, draft)

    assert response is not None
    assert "draft updated" in response.lower()
    assert any("retro" in note.lower() for note in updated.notes)
    assert payload is None
