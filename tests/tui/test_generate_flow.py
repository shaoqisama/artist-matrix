from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.interfaces.creative import AvatarBlueprint
from artist_matrix.soul_forge.connectors import (
    LLMTemplatePersonaGenerator,
    PersonaLLMOutput,
    PersonaPromptVariables,
)
from artist_matrix.tui import SessionState, TuiApp


class _PromptAgentStub:
    def invoke(self, variables: PersonaPromptVariables) -> PersonaLLMOutput:
        instruction_suffix = (
            variables.refinement_instructions[-1]
            if variables.refinement_instructions
            else "baseline"
        )
        return PersonaLLMOutput(
            name=variables.name,
            persona_tags=[*variables.descriptors, instruction_suffix],
            lyric_style=f"{variables.genre} chronicles",
            visual_style=f"{variables.genre} neon",
            influences=variables.influences or ["Kavinsky"],
            safety_notes=variables.safety_notes,
            visual_palette=variables.visual_palette or ["neon magenta"],
            narrative_tone=variables.narrative_tone or instruction_suffix,
        )


class StubSoulForgeService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.requests = []
        self.persona_generator = LLMTemplatePersonaGenerator(
            provider="deepseek",
            model="deepseek-music",
            api_key="sk-test",
            prompt_agent=_PromptAgentStub(),
        )

    def generate(self, request):
        self.requests.append(request)
        manifest_path = self.tmp_path / "neon-wasteland.json"
        manifest_path.write_text("{}", encoding="utf-8")
        profile = ArtistProfile(
            name="Neon Wasteland",
            persona_tags=("retro",),
            lyric_style="synthwave narratives",
            visual_style="neon glitch",
            influences=("Kavinsky",),
        )
        avatar_path = self.tmp_path / "neon-wasteland-avatar.txt"
        avatar_path.write_text("avatar", encoding="utf-8")
        avatar = AvatarBlueprint(prompt="pixel art", seed=108, asset_path=avatar_path)
        return {
            "profile": profile,
            "manifest_path": manifest_path,
            "avatar": avatar,
        }


@pytest.fixture()
def stub_service(tmp_path: Path) -> StubSoulForgeService:
    return StubSoulForgeService(tmp_path)


def test_generate_avatar_flow_success(tmp_path: Path, stub_service: StubSoulForgeService) -> None:
    inputs: Iterator[str] = iter(
        [
            "1",  # main menu -> generate
            "Neon Wasteland",  # name
            "synthwave",  # genre
            "fierce",  # mood
            "Kavinsky",  # influences
            "retro, cinematic",  # descriptors
            "A neon vigilante",  # brief
            "neon magenta, chrome",  # visual palette
            "epic monologue",  # narrative tone
            "avoid explicit content",  # safety notes
            "f",  # summary action -> forge
            "m",  # back to menu
            "q",  # exit application
        ]
    )
    captured: list[str] = []

    session = SessionState()
    app = TuiApp(
        input_func=lambda _: next(inputs),
        output_func=captured.append,
        soul_forge_service=stub_service,
        session=session,
    )

    app.run()

    assert stub_service.requests
    request = stub_service.requests[0]
    assert request.visual_palette == ("neon magenta", "chrome")
    assert request.narrative_tone == "epic monologue"
    assert request.safety_notes == "avoid explicit content"
    assert session.last_profile is not None
    assert session.last_manifest_path is not None
    assert any("Persona forged successfully" in line for line in captured)
    assert captured[-1] == "Shutting down Artist Matrix shell. See you in the wasteland."


def test_generate_avatar_flow_edit_back(tmp_path: Path, stub_service: StubSoulForgeService) -> None:
    inputs: Iterator[str] = iter(
        [
            "1",
            "Neon Wasteland",
            "synthwave",
            "fierce",
            "",
            "",
            "",
            "",
            "",
            "",
            "e",
            "4",
            "Kavinsky, Gunship",
            ".",
            ".",
            ".",
            ".",
            ".",
            "f",
            "m",
            "q",
        ]
    )
    captured: list[str] = []

    session = SessionState()
    app = TuiApp(
        input_func=lambda _: next(inputs),
        output_func=captured.append,
        soul_forge_service=stub_service,
        session=session,
    )

    app.run()

    assert stub_service.requests
    request = stub_service.requests[-1]
    assert request.influences == ("Kavinsky", "Gunship")
    assert captured[-1] == "Shutting down Artist Matrix shell. See you in the wasteland."


def test_generate_avatar_flow_refine_with_ai(tmp_path: Path, stub_service: StubSoulForgeService) -> None:
    inputs: Iterator[str] = iter(
        [
            "1",
            "Neon Wasteland",
            "synthwave",
            "fierce",
            "Kavinsky",
            "retro",
            "",
            "",
            "",
            "",
            "r",
            "Add cyberpunk edge",
            "y",
            "f",
            "m",
            "q",
        ]
    )
    captured: list[str] = []

    session = SessionState()
    app = TuiApp(
        input_func=lambda _: next(inputs),
        output_func=captured.append,
        soul_forge_service=stub_service,
        session=session,
    )

    app.run()

    assert stub_service.requests
    request = stub_service.requests[-1]
    assert "Add cyberpunk edge" in request.refinement_instructions
    assert session.last_profile is not None
    assert captured[-1] == "Shutting down Artist Matrix shell. See you in the wasteland."
