from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from artist_matrix.interfaces.creative import (
    AvatarBlueprint,
    PersonaDraft,
    PersonaRequest,
)
from artist_matrix.soul_forge import (
    ArtistProfile,
    ArtistProfileRepository,
    SoulForgeRequest,
    SoulForgeService,
)


class StubPersonaGenerator:
    def __init__(self) -> None:
        self.requests: list[PersonaRequest] = []

    def draft_persona(self, request: PersonaRequest) -> PersonaDraft:
        self.requests.append(request)
        return PersonaDraft(
            name=request.name,
            persona_tags=request.descriptors or ("post-apocalyptic", "8-bit"),
            lyric_style=f"{request.genre} narratives",
            visual_style="retro synthwave",
            influences=request.influences,
            safety_notes="Ensure lyrical content respects platform policies.",
        )


class StubAvatarGenerator:
    def __init__(self) -> None:
        self.profiles: list[ArtistProfile] = []

    def generate_avatar(self, profile: ArtistProfile) -> AvatarBlueprint:
        self.profiles.append(profile)
        return AvatarBlueprint(prompt=f"pixel portrait of {profile.name}", seed=42)


@pytest.fixture()
def repository(tmp_path: Path) -> ArtistProfileRepository:
    return ArtistProfileRepository(base_path=tmp_path)


def test_generate_creates_manifest_on_disk(repository: ArtistProfileRepository) -> None:
    persona_gen = StubPersonaGenerator()
    avatar_gen = StubAvatarGenerator()
    fixed_time = datetime(2099, 12, 31, 23, 59, 59)

    service = SoulForgeService(
        persona_generator=persona_gen,
        avatar_generator=avatar_gen,
        repository=repository,
        clock=lambda: fixed_time,
        version="1.0",
    )

    result = service.generate(
        SoulForgeRequest(
            name="Neon Wasteland",
            genre="synth metal",
            mood="frenetic",
            influences=("Nine Inch Nails", "Perturbator"),
            descriptors=("cyberpunk", "cinematic"),
            brief="Create a persona who bridges industrial grit with arcade nostalgia.",
        )
    )

    profile = result["profile"]
    manifest_path = result["manifest_path"]
    avatar = result["avatar"]

    assert isinstance(profile, ArtistProfile)
    assert profile.name == "Neon Wasteland"
    assert profile.slug == "neon-wasteland"
    assert profile.created_at == fixed_time

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["name"] == "Neon Wasteland"
    assert data["slug"] == "neon-wasteland"
    assert data["created_at"] == fixed_time.isoformat()
    assert data["avatar"]["prompt"] == "pixel portrait of Neon Wasteland"
    assert avatar is not None and avatar.seed == 42

    assert persona_gen.requests[0].brief.startswith("Create a persona")
    assert avatar_gen.profiles[0] == profile


def test_repository_handles_missing_avatar(tmp_path: Path) -> None:
    repository = ArtistProfileRepository(base_path=tmp_path)
    profile = ArtistProfile(
        name="Void Signal",
        persona_tags=("ambient",),
        lyric_style="whispered transmissions",
        visual_style="infrared glitch",
        influences=("Aphex Twin",),
        safety_notes=None,
        created_at=datetime(2100, 1, 1, 0, 0, 0),
        version="1.0",
    )

    path = repository.save(profile, avatar=None)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert "avatar" not in data
    assert data["created_at"] == "2100-01-01T00:00:00"
    assert data["slug"] == "void-signal"
