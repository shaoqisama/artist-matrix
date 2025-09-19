from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.interfaces.creative import AvatarBlueprint
from artist_matrix.tui import SessionState, TuiApp


class StubSoulForgeService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.requests = []

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
        avatar = AvatarBlueprint(prompt="pixel art", seed=108)
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
            "y",  # confirm forge
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
    assert session.last_profile is not None
    assert session.last_manifest_path is not None
    assert any("Persona forged successfully" in line for line in captured)
    assert captured[-1] == "Shutting down Artist Matrix shell. See you in the wasteland."
