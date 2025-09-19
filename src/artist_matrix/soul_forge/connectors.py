"""Configurable persona and avatar generators for the Soul Forge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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


def build_persona_generator(settings: ArtistMatrixSettings) -> PersonaGenerator:
    provider = settings.persona_provider.lower()
    if provider in {"stub", "local"}:
        return StubPersonaGenerator()
    raise NotImplementedError(
        f"Persona provider '{settings.persona_provider}' is not implemented."
    )


def build_avatar_generator(settings: ArtistMatrixSettings) -> AvatarGenerator:
    provider = settings.avatar_provider.lower()
    asset_root = settings.data_root / "avatars"
    if provider in {"stub", "local"}:
        return StubAvatarGenerator(asset_root=asset_root)
    raise NotImplementedError(
        f"Avatar provider '{settings.avatar_provider}' is not implemented."
    )


__all__ = [
    "StubPersonaGenerator",
    "StubAvatarGenerator",
    "build_persona_generator",
    "build_avatar_generator",
]
