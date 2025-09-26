from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from artist_matrix.tui import TuiApp
from artist_matrix.tui.app import SessionState


@pytest.fixture()
def manifest_dir(tmp_path: Path) -> Path:
    artists_dir = tmp_path / "artists"
    avatars_dir = tmp_path / "avatars"
    artists_dir.mkdir(parents=True)
    avatars_dir.mkdir(parents=True)
    manifest = {
        "name": "Neon Wasteland",
        "persona_tags": ["retro", "cyberpunk"],
        "lyric_style": "Synthwave monologue",
        "visual_style": "Magenta chrome",
        "influences": ["Kavinsky"],
        "safety_notes": "No explicit content",
        "visual_palette": ["magenta", "chrome"],
        "narrative_tone": "epic",
        "slug": "neon-wasteland",
        "created_at": "2025-01-01T00:00:00",
        "avatar": {
            "prompt": "pixel art",
            "seed": 42,
            "asset_path": str(avatars_dir / "neon-wasteland.png"),
        },
    }
    (artists_dir / "neon-wasteland.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (avatars_dir / "neon-wasteland.png").write_text("fake")
    return tmp_path


def test_select_avatar_flow(monkeypatch, manifest_dir: Path) -> None:
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(manifest_dir))

    inputs: Iterator[str] = iter(["1", "y", "m"])
    outputs: list[str] = []

    session = SessionState()
    app = TuiApp(
        input_func=lambda prompt='': next(inputs),
        output_func=outputs.append,
        session=session,
    )

    app.handle_select()

    assert session.last_profile is not None
    assert session.last_manifest_path and session.last_manifest_path.name == "neon-wasteland.json"
    assert any("Persona 'Neon Wasteland' loaded" in line for line in outputs)


def test_select_avatar_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(tmp_path))

    inputs: Iterator[str] = iter(["q"])
    outputs: list[str] = []

    app = TuiApp(
        input_func=lambda prompt='': next(inputs),
        output_func=outputs.append,
        session=SessionState(),
    )

    app.handle_select()

    assert any("No personas available" in line for line in outputs)


def test_creation_engine_suggestion(monkeypatch, manifest_dir: Path) -> None:
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(manifest_dir))
    monkeypatch.setenv("ARTIST_MATRIX_PERSONA_PROVIDER", "stub")
    monkeypatch.setenv("ARTIST_MATRIX_CREATION_AUDIO_PROVIDER", "stub")

    outputs: list[str] = []
    app = TuiApp(input_func=lambda _: "", output_func=outputs.append)
    records = app._load_persona_records()
    assert records
    app._apply_persona_selection(records[0])
    outputs.clear()

    app.handle_creation_engine()

    assert any("Suno Payload Preview" in line for line in outputs)
    assert any("Title" in line for line in outputs)


def test_echo_chamber_suggestion(monkeypatch, manifest_dir: Path) -> None:
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(manifest_dir))
    monkeypatch.setenv("ARTIST_MATRIX_PERSONA_PROVIDER", "stub")
    monkeypatch.setenv("ARTIST_MATRIX_CREATION_AUDIO_PROVIDER", "stub")

    outputs: list[str] = []
    app = TuiApp(input_func=lambda _: "", output_func=outputs.append)
    records = app._load_persona_records()
    app._apply_persona_selection(records[0])
    outputs.clear()

    app.handle_echo_chamber()

    assert any("Echo Chamber" in line for line in outputs)
    assert any("Beats:" in line for line in outputs)
