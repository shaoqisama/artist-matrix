"""Configurable persona and avatar generators for the Soul Forge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from pydantic import BaseModel

from artist_matrix.interfaces.creative import (
    AvatarBlueprint,
    AvatarGenerator,
    PersonaDraft,
    PersonaGenerator,
    PersonaRequest,
)
from artist_matrix.soul_forge.profiles import ArtistProfile
from artist_matrix.state import ArtistMatrixSettings


@dataclass
class StubPersonaGenerator(PersonaGenerator):
    """Basic persona generator used when external LLMs are not configured."""

    def draft_persona(self, request: PersonaRequest) -> PersonaDraft:
        influences = tuple(request.influences)
        descriptors = tuple(request.descriptors)
        persona_tags = descriptors or (request.mood, "tui-forged")
        lyric_style = f"{request.genre} narratives"
        visual_style = f"{request.genre} holographic"
        safety_notes = "Ensure generated content remains suitable for all audiences."
        return PersonaDraft(
            name=request.name,
            persona_tags=persona_tags,
            lyric_style=lyric_style,
            visual_style=visual_style,
            influences=influences or ("synthetic muse",),
            safety_notes=safety_notes,
            visual_palette=tuple(request.visual_palette),
            narrative_tone=request.narrative_tone,
        )


@dataclass
class PersonaPromptAgent(Protocol):
    def invoke(self, variables: PersonaPromptVariables) -> PersonaLLMOutput:
        ...


@dataclass
class LLMTemplatePersonaGenerator(PersonaGenerator):
    """Template-based persona generator mimicking an external LLM response."""

    provider: str
    model: str
    api_key: str | None = None
    prompt_agent: PersonaPromptAgent | None = None

    def draft_persona(self, request: PersonaRequest) -> PersonaDraft:
        if self.prompt_agent and self.api_key:
            variables = PersonaPromptVariables(
                name=request.name,
                genre=request.genre,
                mood=request.mood,
                influences=list(request.influences),
                descriptors=list(request.descriptors),
                brief=request.brief,
                visual_palette=list(request.visual_palette),
                narrative_tone=request.narrative_tone,
                safety_notes=request.safety_notes,
                refinement_instructions=list(request.refinement_instructions),
            )
            try:
                payload = self.prompt_agent.invoke(variables)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"AI persona generation failed: {exc}") from exc
            return PersonaDraft(
                name=payload.name,
                persona_tags=tuple(payload.persona_tags),
                lyric_style=payload.lyric_style,
                visual_style=payload.visual_style,
                influences=tuple(payload.influences),
                safety_notes=payload.safety_notes,
                visual_palette=tuple(payload.visual_palette),
                narrative_tone=payload.narrative_tone,
            )

        influences = tuple(request.influences) or ("experimental muse",)
        descriptors = tuple(request.descriptors)
        persona_tags = descriptors or (request.genre, self.provider)
        lyric_style = f"{request.genre} {self.provider} narratives"
        visual_style = f"{request.genre} holographic {self.provider}"
        safety_notes = (
            "Generated via {provider} model {model}; review for content safety."
        ).format(provider=self.provider, model=self.model)
        if self.api_key:
            safety_notes += " (api key supplied)"
        visual_palette = tuple(request.visual_palette) or (f"{request.genre} neon",)
        narrative_tone = request.narrative_tone or f"{request.mood} chronicle"
        if request.refinement_instructions:
            narrative_tone = f"{narrative_tone} | {'; '.join(request.refinement_instructions)}"
        return PersonaDraft(
            name=request.name,
            persona_tags=persona_tags,
            lyric_style=lyric_style,
            visual_style=visual_style,
            influences=influences,
            safety_notes=safety_notes,
            visual_palette=visual_palette,
            narrative_tone=narrative_tone,
        )


@dataclass
class StubAvatarGenerator(AvatarGenerator):
    """Diffusion stub that records prompt metadata to a local file."""

    asset_root: Path
    prompt_template: Callable[[ArtistProfile], str] | None = None

    def __post_init__(self) -> None:
        self.asset_root.mkdir(parents=True, exist_ok=True)

    def generate_avatar(self, profile: ArtistProfile) -> AvatarBlueprint:
        prompt = (
            self.prompt_template(profile)
            if self.prompt_template
            else f"pixel art portrait of {profile.name} in {profile.visual_style} style"
        )
        asset_path = self.asset_root / f"{profile.slug}.txt"
        asset_path.write_text(
            f"prompt: {prompt}\nvisual_style: {profile.visual_style}\n",
            encoding="utf-8",
        )
        return AvatarBlueprint(prompt=prompt, seed=42, asset_path=asset_path)


@dataclass
class DiffusionAvatarGenerator(AvatarGenerator):
    """Simulated diffusion generator writing metadata for downstream rendering."""

    provider: str
    model: str
    asset_root: Path
    prompt_template: Callable[[ArtistProfile], str] | None = None
    api_key: str | None = None

    def __post_init__(self) -> None:
        self.asset_root.mkdir(parents=True, exist_ok=True)

    def generate_avatar(self, profile: ArtistProfile) -> AvatarBlueprint:
        prompt = (
            self.prompt_template(profile)
            if self.prompt_template
            else f"{profile.visual_style} portrait of {profile.name}"
        )
        metadata: dict[str, object] = {
            "provider": self.provider,
            "model": self.model,
            "prompt": prompt,
            "persona_tags": list(profile.persona_tags),
        }
        if self.api_key:
            metadata["api_key_present"] = True
        asset_path = self.asset_root / f"{profile.slug}-{self.provider}.json"
        asset_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return AvatarBlueprint(prompt=prompt, seed=108, asset_path=asset_path)


def build_persona_generator(settings: ArtistMatrixSettings) -> PersonaGenerator:
    provider = settings.persona_provider.lower()
    if provider in {"stub", "local"}:
        return StubPersonaGenerator()
    if provider in {"deepseek", "claude"}:
        api_key = settings.persona_api_key
        model = settings.persona_model or "persona-default"
        # Real LLM integration can be wired by supplying a PersonaPromptAgent instance.
        return LLMTemplatePersonaGenerator(
            provider=provider,
            model=model,
            api_key=api_key,
            prompt_agent=None,
        )
    raise NotImplementedError(
        f"Persona provider '{settings.persona_provider}' is not implemented."
    )


def build_avatar_generator(settings: ArtistMatrixSettings) -> AvatarGenerator:
    provider = settings.avatar_provider.lower()
    asset_root = settings.data_root / "avatars"
    if provider in {"stub", "local"}:
        return StubAvatarGenerator(asset_root=asset_root)
    if provider in {"sdxl", "diffusion", "runway"}:
        model = settings.avatar_model or "sdxl-stub"
        return DiffusionAvatarGenerator(
            provider=provider,
            model=model,
            asset_root=asset_root,
            api_key=settings.avatar_api_key,
        )
    raise NotImplementedError(
        f"Avatar provider '{settings.avatar_provider}' is not implemented."
    )


__all__ = [
    "StubPersonaGenerator",
    "LLMTemplatePersonaGenerator",
    "StubAvatarGenerator",
    "DiffusionAvatarGenerator",
    "build_persona_generator",
    "build_avatar_generator",
]
class PersonaLLMOutput(BaseModel):
    name: str
    persona_tags: list[str]
    lyric_style: str
    visual_style: str
    influences: list[str]
    safety_notes: str | None = None
    visual_palette: list[str] = []
    narrative_tone: str | None = None


class PersonaPromptVariables(BaseModel):
    name: str
    genre: str
    mood: str
    influences: list[str]
    descriptors: list[str]
    brief: str | None
    visual_palette: list[str]
    narrative_tone: str | None
    safety_notes: str | None
    refinement_instructions: list[str]
