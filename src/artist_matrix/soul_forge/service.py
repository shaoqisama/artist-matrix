"""Soul Forge service for creating and persisting artist personas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping

from artist_matrix.interfaces.creative import (
    AvatarBlueprint,
    AvatarGenerator,
    PersonaGenerator,
    PersonaRequest,
)

from .profiles import ArtistProfile

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DATA_DIR = _PROJECT_ROOT / "data" / "artists"


@dataclass
class SoulForgeRequest:
    """Request envelope used by the Soul Forge service."""

    name: str
    genre: str
    mood: str
    influences: Iterable[str]
    descriptors: Iterable[str] = ()
    brief: str | None = None
    visual_palette: Iterable[str] = ()
    narrative_tone: str | None = None
    safety_notes: str | None = None

    def to_persona_request(self) -> PersonaRequest:
        return PersonaRequest(
            name=self.name,
            genre=self.genre,
            mood=self.mood,
            influences=tuple(self.influences),
            descriptors=tuple(self.descriptors),
            brief=self.brief,
            visual_palette=tuple(self.visual_palette),
            narrative_tone=self.narrative_tone,
            safety_notes=self.safety_notes,
        )


class ArtistProfileRepository:
    """Handles persistence of artist profile manifests."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or _DEFAULT_DATA_DIR

    def save(
        self,
        profile: ArtistProfile,
        *,
        avatar: AvatarBlueprint | None = None,
    ) -> Path:
        self.base_path.mkdir(parents=True, exist_ok=True)
        manifest = profile.manifest()
        if avatar is not None:
            manifest["avatar"] = {
                "prompt": avatar.prompt,
                "seed": avatar.seed,
                "asset_path": str(avatar.asset_path) if avatar.asset_path else None,
            }
        target = self.base_path / f"{profile.slug}.json"
        target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return target


class SoulForgeService:
    """Coordinates persona creation via injected generators."""

    def __init__(
        self,
        persona_generator: PersonaGenerator,
        avatar_generator: AvatarGenerator | None,
        repository: ArtistProfileRepository | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        version: str = "1.0",
    ) -> None:
        self.persona_generator = persona_generator
        self.avatar_generator = avatar_generator
        self.repository = repository or ArtistProfileRepository()
        self._clock = clock or datetime.utcnow
        self._version = version

    def generate(self, request: SoulForgeRequest) -> Mapping[str, object]:
        persona_request = request.to_persona_request()
        draft = self.persona_generator.draft_persona(persona_request)
        profile = ArtistProfile.from_draft(draft, created_at=self._clock(), version=self._version)

        avatar = None
        if self.avatar_generator is not None:
            avatar = self.avatar_generator.generate_avatar(profile)

        manifest_path = self.repository.save(profile, avatar=avatar)
        return {
            "profile": profile,
            "manifest_path": manifest_path,
            "avatar": avatar,
        }


__all__ = [
    "SoulForgeRequest",
    "ArtistProfileRepository",
    "SoulForgeService",
]
