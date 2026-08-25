from __future__ import annotations

import json
from pathlib import Path

from artist_matrix.agent_runtime.actions import (
    ActionExecutor,
    ActionKind,
    ActionLedger,
    ActionStatus,
)
from artist_matrix.agent_runtime.domain_handlers import build_action_handlers
from artist_matrix.soul_forge.profiles import ArtistProfile
from artist_matrix.soul_forge.service import ArtistProfileRepository
from artist_matrix.state import ArtistMatrixSettings


def test_approved_persona_uses_existing_avatar_and_profile_services(
    tmp_path: Path,
) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path, avatar_provider="stub")
    ledger = ActionLedger(settings)
    action = ledger.propose(
        ActionKind.SAVE_PERSONA,
        {
            "profile": {
                "name": "Neon Wasteland",
                "persona_tags": ["retro"],
                "lyric_style": "synthwave stories",
                "visual_style": "neon glitch",
                "influences": ["Kavinsky"],
            }
        },
    )

    result = ActionExecutor(
        ledger,
        handlers=build_action_handlers(settings),
    ).approve_and_execute(action.action_id)

    assert result.status == ActionStatus.COMPLETED
    assert result.result is not None
    assert Path(str(result.result["manifest_path"])).exists()
    assert Path(str(result.result["avatar_asset_path"])).exists()
    manifest_path = Path(str(result.result["manifest_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["avatar"]["seed"] == 42


def test_approved_local_render_uses_existing_creation_engine(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path, creation_audio_provider="stub")
    profile = ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("retro",),
        lyric_style="synthwave stories",
        visual_style="neon glitch",
        influences=("Kavinsky",),
    )
    ArtistProfileRepository(base_path=tmp_path / "artists").save(profile)
    ledger = ActionLedger(settings)
    action = ledger.propose(
        ActionKind.RENDER_TRACK,
        {
            "artist_slug": profile.slug,
            "draft": {
                "persona_slug": profile.slug,
                "title": "Signal Burn",
                "style": "tense synthwave",
                "tags": ["neon", "cinematic"],
                "lyrics": "Signals burn across the midnight skyline.",
            },
        },
    )

    result = ActionExecutor(
        ledger,
        handlers=build_action_handlers(settings),
    ).approve_and_execute(action.action_id)

    assert result.status == ActionStatus.COMPLETED
    assert result.result is not None
    assert result.result["provider"] == "stub"
    assert Path(str(result.result["audio_path"])).exists()
    manifest_path = Path(str(result.result["manifest_path"]))
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["lyrics"]["body"] == "Signals burn across the midnight skyline."


def test_remote_audio_requires_an_idempotent_adapter_before_execution(
    tmp_path: Path,
) -> None:
    settings = ArtistMatrixSettings(
        data_root=tmp_path,
        creation_audio_provider="suno",
        creation_audio_api_key="configured-but-never-called",
    )

    assert ActionKind.RENDER_TRACK not in build_action_handlers(settings)
