from __future__ import annotations

import json
from pathlib import Path

from artist_matrix.interfaces.creative import PersonaRequest
from artist_matrix.soul_forge.connectors import (
    DiffusionAvatarGenerator,
    LLMTemplatePersonaGenerator,
    StubPersonaGenerator,
    build_avatar_generator,
    build_persona_generator,
)
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state import ArtistMatrixSettings


def test_build_persona_generator_stub() -> None:
    settings = ArtistMatrixSettings(persona_provider="stub")
    generator = build_persona_generator(settings)
    assert isinstance(generator, StubPersonaGenerator)


def test_build_persona_generator_deepseek(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(
        data_root=tmp_path,
        persona_provider="deepseek",
        persona_model="deepseek-music",
        persona_api_key="sk-deepseek-test",
    )
    generator = build_persona_generator(settings)
    assert isinstance(generator, LLMTemplatePersonaGenerator)
    assert generator.api_key == "sk-deepseek-test"
    draft = generator.draft_persona(
        PersonaRequest(
            name="Neon Wasteland",
            genre="synthwave",
            mood="fierce",
            influences=("Kavinsky",),
            descriptors=("retro",),
        )
    )
    assert "deepseek" in draft.persona_tags or "deepseek" in draft.lyric_style


def test_build_avatar_generator_sdxl(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(
        data_root=tmp_path,
        avatar_provider="sdxl",
        avatar_model="sdxl-music",
        avatar_api_key="sk-sdxl-test",
    )
    generator = build_avatar_generator(settings)
    assert isinstance(generator, DiffusionAvatarGenerator)
    assert generator.api_key == "sk-sdxl-test"
    profile = ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("retro",),
        lyric_style="synthwave",
        visual_style="neon glitch",
        influences=("Kavinsky",),
    )
    avatar = generator.generate_avatar(profile)
    assert avatar.asset_path is not None
    metadata = json.loads(Path(avatar.asset_path).read_text(encoding="utf-8"))
    assert metadata["provider"] == "sdxl"
    assert metadata["model"] == "sdxl-music"
