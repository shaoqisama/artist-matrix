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
class PersonaWizardDraft:
    name: str = ""
    genre: str = ""
    mood: str = ""
    influences: tuple[str, ...] = ()
    descriptors: tuple[str, ...] = ()
    brief: str = ""
    visual_palette: tuple[str, ...] = ()
    narrative_tone: str = ""
    safety_notes: str = ""


@dataclass
class SessionState:
    last_profile: ArtistProfile | None = None
    last_manifest_path: Path | None = None
    last_avatar: AvatarBlueprint | None = None
    draft: PersonaWizardDraft = field(default_factory=PersonaWizardDraft)


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
        draft = self._collect_persona_draft()
        if draft is None:
            self.output("\n>> Persona creation cancelled. Returning to main menu.")
            return

        self.session.draft = draft
        self.output("\n>> Forging persona... stand by")
        try:
            result = self.soul_forge.generate(
                SoulForgeRequest(
                    name=draft.name,
                    genre=draft.genre,
                    mood=draft.mood,
                    influences=draft.influences or ("experimental muse",),
                    descriptors=draft.descriptors,
                    brief=draft.brief or None,
                    visual_palette=draft.visual_palette,
                    narrative_tone=draft.narrative_tone or None,
                    safety_notes=draft.safety_notes or None,
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
        if draft.visual_palette:
            summary.append(
                f" → Visual palette: {', '.join(draft.visual_palette)}"
            )
        if draft.narrative_tone:
            summary.append(f" → Narrative tone: {draft.narrative_tone}")
        if draft.safety_notes:
            summary.append(f" → Safety notes : {draft.safety_notes}")
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

    # --- Wizard helpers -------------------------------------------------

    def _collect_persona_draft(self) -> PersonaWizardDraft | None:
        draft = PersonaWizardDraft(
            name=self.session.draft.name,
            genre=self.session.draft.genre,
            mood=self.session.draft.mood,
            influences=self.session.draft.influences,
            descriptors=self.session.draft.descriptors,
            brief=self.session.draft.brief,
            visual_palette=self.session.draft.visual_palette,
            narrative_tone=self.session.draft.narrative_tone,
            safety_notes=self.session.draft.safety_notes,
        )

        steps = [
            ("name", "Artist alias", True, "text"),
            ("genre", "Primary genre", True, "text"),
            ("mood", "Mood or energy signature", True, "text"),
            (
                "influences",
                "Influences (comma-separated, leave blank if none)",
                False,
                "sequence",
            ),
            (
                "descriptors",
                "Descriptors or persona tags (comma-separated)",
                False,
                "sequence",
            ),
            (
                "brief",
                "One-line creative brief (optional)",
                False,
                "text",
            ),
            (
                "visual_palette",
                "Visual palette cues (comma-separated)",
                False,
                "sequence",
            ),
            (
                "narrative_tone",
                "Narrative tone (optional)",
                False,
                "text",
            ),
            (
                "safety_notes",
                "Safety guardrails (optional)",
                False,
                "text",
            ),
        ]

        self.output("Enter '<' to go back, '.' to keep the current value.")
        index = 0
        while index < len(steps):
            key, prompt, required, kind = steps[index]
            current_value = getattr(draft, key)
            display_value = (
                ", ".join(current_value)
                if isinstance(current_value, tuple)
                else current_value or "—"
            )
            raw = self._input(f"{prompt} [{display_value}]: ").strip()
            if raw in {"<", "b", "back"}:
                if index == 0:
                    self.output("  Already at the first step.")
                    continue
                index -= 1
                continue
            if raw == ".":
                index += 1
                continue
            if not raw:
                if required and not current_value:
                    self.output("  Please provide a value.")
                    continue
                if kind == "sequence":
                    setattr(draft, key, tuple() if not raw else _to_sequence(raw))
                else:
                    setattr(draft, key, current_value if current_value else "")
                index += 1
                continue

            try:
                if kind == "sequence":
                    parsed = _to_sequence(raw)
                    setattr(draft, key, parsed)
                else:
                    setattr(draft, key, raw)
            except ValueError as exc:  # pragma: no cover - defensive
                self.output(f"  Invalid input: {exc}")
                continue
            index += 1

        # Summary + confirmation loop
        while True:
            self.output("\n".join(self._summary_lines(draft)))
            action = self._input("Action [f]orge / [e]dit / [c]ancel: ").strip().lower()
            if action in {"f", "forge"}:
                return draft
            if action in {"c", "cancel"}:
                self.session.draft = draft
                return None
            if action in {"e", "edit"}:
                target = self._input(" Step number to edit (blank for first): ").strip()
                if target.isdigit():
                    idx = int(target) - 1
                    if 0 <= idx < len(steps):
                        index = idx
                    else:
                        self.output("  Invalid step number.")
                        continue
                else:
                    index = 0
                while index < len(steps):
                    key, prompt, required, kind = steps[index]
                    current_value = getattr(draft, key)
                    display_value = (
                        ", ".join(current_value)
                        if isinstance(current_value, tuple)
                        else current_value or "—"
                    )
                    raw = self._input(f"{prompt} [{display_value}]: ").strip()
                    if raw in {"<", "b", "back"}:
                        if index == 0:
                            self.output("  Already at the first step.")
                            continue
                        index -= 1
                        continue
                    if raw == ".":
                        index += 1
                        continue
                    if not raw:
                        if required and not current_value:
                            self.output("  Please provide a value.")
                            continue
                        if kind == "sequence":
                            setattr(draft, key, current_value if isinstance(current_value, tuple) else tuple())
                        else:
                            setattr(draft, key, current_value if current_value else "")
                        index += 1
                        continue
                    if kind == "sequence":
                        setattr(draft, key, _to_sequence(raw))
                    else:
                        setattr(draft, key, raw)
                    index += 1
                continue
            self.output("  Enter 'f', 'e', or 'c'.")

    def _summary_lines(self, draft: PersonaWizardDraft) -> list[str]:
        def fmt(value: object) -> str:
            if isinstance(value, tuple):
                return ", ".join(value) if value else "—"
            return value if isinstance(value, str) and value else "—"

        return [
            "",
            ":: Persona Draft Summary ::",
            f" 1. Name            : {fmt(draft.name)}",
            f" 2. Genre           : {fmt(draft.genre)}",
            f" 3. Mood            : {fmt(draft.mood)}",
            f" 4. Influences      : {fmt(draft.influences)}",
            f" 5. Descriptors     : {fmt(draft.descriptors)}",
            f" 6. Brief           : {fmt(draft.brief)}",
            f" 7. Visual palette  : {fmt(draft.visual_palette)}",
            f" 8. Narrative tone  : {fmt(draft.narrative_tone)}",
            f" 9. Safety notes    : {fmt(draft.safety_notes)}",
        ]

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
