from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_tui(commands: list[str], env: dict[str, str], timeout: float = 15.0) -> tuple[int, str]:
    joined = "\n".join(commands) + "\n"
    process = subprocess.Popen(
        [sys.executable, "-m", "artist_matrix.tui"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, **env},
    )
    output, _ = process.communicate(joined, timeout=timeout)
    return process.returncode or 0, output


def test_creation_workbench_end_to_end(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    artists_dir = data_root / "artists"
    artists_dir.mkdir(parents=True)

    persona = {
        "name": "Neon Wasteland",
        "slug": "neon-wasteland",
        "persona_tags": ["cyberpunk"],
        "lyric_style": "synth metal narration",
        "visual_style": "retro neon",
        "influences": ["Perturbator"],
        "safety_notes": "Keep it safe",
        "created_at": "2099-01-01T00:00:00",
        "avatar": {
            "prompt": "pixel art",
            "seed": 108,
        },
    }
    (artists_dir / "neon-wasteland.json").write_text(json.dumps(persona, indent=2), encoding="utf-8")

    env = {
        "ARTIST_MATRIX_DATA_ROOT": str(data_root),
        "ARTIST_MATRIX_PERSONA_PROVIDER": "stub",
        "ARTIST_MATRIX_CREATION_AUDIO_PROVIDER": "stub",
        "ARTIST_MATRIX_PERSONA_LOG_DIR": str(tmp_path / "logs"),
        "ARTIST_MATRIX_TUI_LOG_DIR": str(tmp_path / "logs" / "tui"),
    }

    commands = [
        "2",  # select persona menu
        "1",  # first persona
        "y",  # confirm load
        "c",  # creation workbench
        "1",  # discuss
        "title: Solar Ache",
        "style: bittersweet funk",
        "tags: funky, melancholy",
        "instrumental: no",
        "lyrics: Verse line",
        "done",
        "3",  # finalize
        "s",  # save final draft
        "b",  # back
        "4",  # render
        "y",  # confirm render
        "m",  # acknowledge post persona prompt
        "b",  # exit creation menu
        "q",  # quit
    ]

    code, output = _run_tui(commands, env)
    assert code == 0, output
    assert "Final draft saved" in output
    assert "Session log saved to" in output
    assert "Creation Engine complete" in output

    final_path = data_root / "artists" / "neon-wasteland" / "drafts" / "final_brief.json"
    manifest_path = data_root / "artists" / "neon-wasteland" / "tracks" / "solar-ache.json"
    assert final_path.exists()
    assert manifest_path.exists()

    log_dir = tmp_path / "logs" / "tui"
    logs = list(log_dir.glob("session_*.jsonl"))
    assert logs

    final_data = json.loads(final_path.read_text(encoding="utf-8"))
    assert final_data["title"] == "Solar Ache"
    assert final_data.get("instrumental") is False
