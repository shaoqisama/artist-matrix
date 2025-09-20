"""Protocols for persona and avatar generation connectors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, Sequence

if TYPE_CHECKING:
    from artist_matrix.soul_forge.profiles import ArtistProfile
else:
    ArtistProfile = Any


@dataclass(frozen=True)
class PersonaRequest:
    """Input signal describing the desired virtual artist persona."""

    name: str
    genre: str
    mood: str
    influences: Sequence[str]
    descriptors: Sequence[str] = ()
    brief: str | None = None
    visual_palette: Sequence[str] = ()
    narrative_tone: str | None = None
    safety_notes: str | None = None
    refinement_instructions: Sequence[str] = ()


@dataclass(frozen=True)
class PersonaDraft:
    """Structured description returned by upstream LLM persona generator."""

    name: str
    persona_tags: Sequence[str]
    lyric_style: str
    visual_style: str
    influences: Sequence[str]
    safety_notes: str | None = None
    visual_palette: Sequence[str] = ()
    narrative_tone: str | None = None


@dataclass(frozen=True)
class AvatarBlueprint:
    """Metadata describing an avatar render request or artifact."""

    prompt: str
    seed: int | None = None
    asset_path: Path | None = None


class PersonaGenerator(Protocol):
    """Interface for drafting persona data via LLM routing."""

    def draft_persona(self, request: PersonaRequest) -> PersonaDraft:
        ...


class AvatarGenerator(Protocol):
    """Interface for producing avatar artwork via diffusion models."""

    def generate_avatar(self, profile: "ArtistProfile") -> AvatarBlueprint:
        ...


__all__ = [
    "PersonaRequest",
    "PersonaDraft",
    "AvatarBlueprint",
    "PersonaGenerator",
    "AvatarGenerator",
]
