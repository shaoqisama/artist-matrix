from __future__ import annotations

import json
from pathlib import Path

from artist_matrix.interfaces.creative import PersonaRequest
from artist_matrix.soul_forge.connectors import DeepSeekPersonaAgent
from artist_matrix.soul_forge import connectors
from artist_matrix.soul_forge.connectors import (
    DiffusionAvatarGenerator,
    LLMTemplatePersonaGenerator,
    PersonaLLMOutput,
    PersonaPromptVariables,
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


class _StubAgent:
    def __init__(self, output: PersonaLLMOutput) -> None:
        self.output = output

    def invoke(self, variables: PersonaPromptVariables) -> PersonaLLMOutput:
        return self.output


def test_deepseek_generator_with_stub_agent(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(
        data_root=tmp_path,
        persona_provider="deepseek",
        persona_model="deepseek-music",
        persona_api_key="sk-deepseek-test",
    )
    generator = build_persona_generator(settings)
    assert isinstance(generator, LLMTemplatePersonaGenerator)
    generator.prompt_agent = _StubAgent(
        PersonaLLMOutput(
            name="Neon Wasteland",
            persona_tags=["retro", "deepseek"],
            lyric_style="synthwave chronicles",
            visual_style="neon glitch",
            influences=["Kavinsky"],
            safety_notes="Keep it clean.",
            visual_palette=["neon magenta"],
            narrative_tone="epic",
        )
    )

    draft = generator.draft_persona(
        PersonaRequest(
            name="Neon Wasteland",
            genre="synthwave",
            mood="fierce",
            influences=("Kavinsky",),
            descriptors=("retro",),
            brief="",
            visual_palette=("neon magenta",),
            narrative_tone="epic",
            safety_notes="Keep it clean.",
        )
    )

    assert draft.name == "Neon Wasteland"
    assert "deepseek" in draft.persona_tags
    assert draft.visual_palette == ("neon magenta",)


def test_deepseek_persona_agent_http(monkeypatch, tmp_path: Path) -> None:
    template = "Name: {name}\nInfluences: {influences}"
    captured: dict[str, object] = {}

    import json as json_module

    def fake_post(url, headers, json, timeout):  # noqa: ANN001
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json

        class _Response:
            def raise_for_status(self) -> None:
                pass

            def json(self):  # noqa: ANN001
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json_module.dumps(
                                    {
                                        "name": "Neon Wasteland",
                                        "persona_tags": ["retro"],
                                        "lyric_style": "synthwave saga",
                                        "visual_style": "neon",
                                        "influences": ["Kavinsky"],
                                        "safety_notes": "Clean.",
                                        "visual_palette": ["magenta"],
                                        "narrative_tone": "epic",
                                    }
                                )
                            }
                        }
                    ]
                }

        return _Response()

    monkeypatch.setattr(connectors.httpx, "post", fake_post)

    agent = DeepSeekPersonaAgent(
        template=template,
        api_key="sk-test",
        model="deepseek-chat",
        endpoint="https://api.deepseek.com/v1/chat/completions",
    )

    variables = PersonaPromptVariables(
        name="Neon Wasteland",
        genre="synthwave",
        mood="fierce",
        influences=["Kavinsky"],
        descriptors=["retro"],
        brief="",
        visual_palette=["magenta"],
        narrative_tone="epic",
        safety_notes="Clean.",
        refinement_instructions=[],
    )

    output = agent.invoke(variables)

    assert output.name == "Neon Wasteland"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "deepseek-chat"


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
