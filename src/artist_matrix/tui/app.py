"""Terminal UI shell for the Artist Matrix experience."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict

from artist_matrix.interfaces.creative import AvatarBlueprint
from artist_matrix.soul_forge import (
    ArtistProfile,
    ArtistProfileRepository,
    SoulForgeRequest,
    SoulForgeService,
    build_avatar_generator,
    build_persona_generator,
)
from artist_matrix.state import ArtistMatrixSettings

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ASSET_DIR = _PROJECT_ROOT / "assets" / "tui"


def _to_sequence(raw: str) -> tuple[str, ...]:
    items = [segment.strip() for segment in raw.split(",") if segment.strip()]
    return tuple(items)
@dataclass
class SessionState:
    last_profile: ArtistProfile | None = None
    last_manifest_path: Path | None = None
    last_avatar: AvatarBlueprint | None = None


@dataclass
class TuiAssets:
    """Lazy loader for banner art and palette metadata."""

    base_path: Path = _ASSET_DIR
    _banner_cache: str | None = field(default=None, init=False)
    _palette_cache: Dict[str, str] | None = field(default=None, init=False)

    def banner(self) -> str:
        if self._banner_cache is None:
            banner_path = self.base_path / "banner.txt"
            self._banner_cache = banner_path.read_text(encoding="utf-8").rstrip()
        return self._banner_cache

    def palette(self) -> Dict[str, str]:
        if self._palette_cache is None:
            palette_path = self.base_path / "palette.json"
            self._palette_cache = json.loads(palette_path.read_text(encoding="utf-8"))
        return self._palette_cache


def _build_default_soul_forge() -> SoulForgeService:
    settings = ArtistMatrixSettings()
    persona_gen = build_persona_generator(settings)
    avatar_gen = build_avatar_generator(settings)
    return SoulForgeService(
        persona_generator=persona_gen,
        avatar_generator=avatar_gen,
        repository=ArtistProfileRepository(base_path=settings.data_root / "artists"),
    )


class TuiApp:
    """Interactive shell coordinating avatar selection and creation."""

    def __init__(
        self,
        *,
        input_func: Callable[[str], str] | None = None,
        output_func: Callable[[str], None] | None = None,
        assets: TuiAssets | None = None,
        soul_forge_service: SoulForgeService | None = None,
        session: SessionState | None = None,
    ) -> None:
        self._input = input_func or input
        self._output = output_func or print
        self.assets = assets or TuiAssets()
        self.soul_forge = soul_forge_service or _build_default_soul_forge()
        self.session = session or SessionState()

    def build_main_menu(self) -> str:
        palette = self.assets.palette()
        palette_line = (
            f"[{palette['primary']}] Primary  :: [{palette['accent']}] Accent  ::"
            f" [{palette['warning']}] Alert"
        )
        menu_lines = [
            self.assets.banner(),
            "",
            "// Frequency Map",
            palette_line,
            "",
            " [1] Generate Avatar    -> Soul Forge",
            " [2] Select Avatar      -> Archives",
            " [Q] Quit Terminal      -> Sleep Cycle",
            "",
        ]
        return "\n".join(menu_lines)

    def run(self) -> None:
        while True:
            self.output(self.build_main_menu())
            choice = self._input("Select mode (1/2/Q): ").strip().lower()
            if choice in {"1", "g", "generate"}:
                self.handle_generate()
            elif choice in {"2", "s", "select"}:
                self.handle_select()
            elif choice in {"q", "quit", "exit"}:
                self.output("Shutting down Artist Matrix shell. See you in the wasteland.")
                break
            else:
                self.output("Invalid selection. Enter 1, 2, or Q to exit.")

    def handle_generate(self) -> None:
        self.output("\n>> Soul Forge // Persona constructor engaged")
        name = self._prompt_required("Artist alias")
        genre = self._prompt_required("Primary genre")
        mood = self._prompt_required("Mood or energy signature")
        influences_raw = self._prompt_optional(
            "Influences (comma-separated, leave blank if none)"
        )
        descriptors_raw = self._prompt_optional(
            "Descriptors or persona tags (comma-separated)"
        )
        brief = self._prompt_optional(
            "One-line creative brief (optional)", allow_empty=True
        )

        influences = _to_sequence(influences_raw)
        descriptors = _to_sequence(descriptors_raw)

        summary_lines = [
            "",
            ":: Persona Draft Summary ::",
            f" Name       : {name}",
            f" Genre      : {genre}",
            f" Mood       : {mood}",
            f" Influences : {', '.join(influences) if influences else '—'}",
            f" Descriptors: {', '.join(descriptors) if descriptors else '—'}",
            f" Brief      : {brief or '—'}",
        ]
        self.output("\n".join(summary_lines))

        if not self._prompt_confirm("Forge this persona? (y/n)"):
            self.output("\n>> Persona creation cancelled. Returning to main menu.")
            return

        self.output("\n>> Forging persona... stand by")
        try:
            result = self.soul_forge.generate(
                SoulForgeRequest(
                    name=name,
                    genre=genre,
                    mood=mood,
                    influences=influences or ("experimental muse",),
                    descriptors=descriptors,
                    brief=brief or None,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.output(f"!! Forge failure: {exc}")
            if self.session.last_manifest_path:
                self.output(
                    f"Last successful manifest stored at {self.session.last_manifest_path}"
                )
            return

        profile = result.get("profile")
        manifest_path = Path(str(result.get("manifest_path")))
        avatar = result.get("avatar")

        if isinstance(profile, ArtistProfile):
            self.session.last_profile = profile
        self.session.last_manifest_path = manifest_path
        if isinstance(avatar, AvatarBlueprint):
            self.session.last_avatar = avatar

        summary = [
            "\nPersona forged successfully!",
            f" → Manifest saved: {manifest_path}",
        ]
        if isinstance(profile, ArtistProfile):
            summary.extend(
                [
                    f" → Artist slug : {profile.slug}",
                    f" → Lyric style: {profile.lyric_style}",
                    f" → Visual mode: {profile.visual_style}",
                ]
            )
        if isinstance(avatar, AvatarBlueprint):
            summary.extend(
                [
                    " → Avatar prompt preview:",
                    f"   '{avatar.prompt}' (seed={avatar.seed or 'n/a'})",
                    f"   asset: {avatar.asset_path or 'n/a'}",
                ]
            )
        self.output("\n".join(summary))

    def handle_select(self) -> None:
        self.output("\n>> Accessing artist archives...")
        if self.session.last_profile and self.session.last_manifest_path:
            profile = self.session.last_profile
            manifest_path = self.session.last_manifest_path
            self.output(
                f" Most recent persona: {profile.name} ({profile.slug})\n"
                f" Manifest: {manifest_path}"
            )
            return

        self.output(
            " No personas forged this session. Run 'Generate Avatar' to craft one."
        )

    def output(self, message: str) -> None:
        self._output(message)

    def _prompt_required(self, prompt: str) -> str:
        while True:
            value = self._input(f"{prompt}: ").strip()
            if value:
                return value
            self.output("  Please provide a value.")

    def _prompt_optional(self, prompt: str, *, allow_empty: bool = True) -> str:
        while True:
            value = self._input(f"{prompt}: ").strip()
            if value:
                return value
            if allow_empty:
                return ""
            self.output("  Please provide a value or leave blank if not required.")

    def _prompt_confirm(self, prompt: str) -> bool:
        while True:
            selection = self._input(f"{prompt} ").strip().lower()
            if selection in {"y", "yes"}:
                return True
            if selection in {"n", "no"}:
                return False
            self.output("  Enter 'y' or 'n'.")


def main() -> None:
    """Entry point for python -m artist_matrix.tui."""

    TuiApp().run()


__all__ = ["TuiApp", "main", "TuiAssets", "SessionState"]
