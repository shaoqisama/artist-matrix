"""Rich-based Terminal UI shell for the Artist Matrix experience with Alien: Earth theming."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn

from artist_matrix.interfaces.creative import AvatarBlueprint
from artist_matrix.soul_forge import (
    ArtistProfile,
    ArtistProfileRepository,
    SoulForgeRequest,
    SoulForgeService,
    build_avatar_generator,
    build_persona_generator,
)
from artist_matrix.creation_engine import (
    ChatTurn,
    CreationEngineService,
    SunoPayloadPreview,
    TrackIdeationDraft,
    TrackIdeationLLM,
    TrackIdeationStore,
    TrackManifestRepository,
    apply_llm_guidance,
    build_audio_generator,
    build_lyric_generator,
    build_suno_preview,
)
from artist_matrix.creation_engine.service import TrackJobSpec
from artist_matrix.interfaces.production import TrackArtifact
from artist_matrix.echo_chamber import SocialCampaign
from artist_matrix.echo_chamber.service import EchoChamberService
from artist_matrix.state import ArtistMatrixSettings
from artist_matrix.tui.logging import SessionLogger
from artist_matrix.tui.app import SessionState, PersonaWizardDraft

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ASSET_DIR = _PROJECT_ROOT / "assets" / "tui"


def _to_sequence(raw: str) -> tuple[str, ...]:
    items = [segment.strip() for segment in raw.split(",") if segment.strip()]
    return tuple(items)


@dataclass
class PersonaRecord:
    path: Path
    manifest: dict[str, object]


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


@dataclass
class AlienTheme:
    """Alien: Earth visual theme configuration."""
    
    # Color palette from docs/tui_visual_guide.md
    acid_green = "#00FF7F"      # warnings, active text, cursor blink
    electric_blue = "#1E90FF"   # neutral/system info
    rust_brown = "#8B4513"      # frame borders, separators
    concrete_gray = "#696969"   # frame borders, separators
    deep_black = "#000000"      # background
    
    # ASCII art elements
    xenomorph_silhouette = r"""
    ░░░░░░░░░░░▄▄▄▄▄▄▄▄░░░░░░░░░
    ░░░░░░░▄█████████████▄░░░░░░
    ░░░░░▄██▀░░░░░░░░░░░▀██▄░░░░
    ░░░▄██▀░░░░░░░░░░░░░░░▀██▄░░
    ░░██▀░░░░░░░░░░░░░░░░░░░▀██░
    ░██░░░░░░░░░░░░░░░░░░░░░░░██
    ██░░░░░░░░░░░░░░░░░░░░░░░░░██
    ██░░░░░░░░░░░░░░░░░░░░░░░░░██
    ██░░░░░░░░░░░░░░░░░░░░░░░░░██
    ░██░░░░░░░░░░░░░░░░░░░░░░░██░
    ░░██▄░░░░░░░░░░░░░░░░░░░▄██░░
    ░░░▀██▄░░░░░░░░░░░░░░░▄██▀░░░
    ░░░░░▀██▄░░░░░░░░░░░▄██▀░░░░░
    ░░░░░░░▀█████████████▀░░░░░░░
    ░░░░░░░░░░░▀▀▀▀▀▀▀▀▀░░░░░░░░░
    """
    
    weyland_yutani_tag = "[WY]"
    hazard_stripes = "██░░██░░██░░██"
    radar_blip = "* . *"
    alien_head = "((<:>))"
    
    @property
    def warning_style(self) -> Style:
        return Style(color=self.acid_green, bold=True, blink=True)
    
    @property
    def info_style(self) -> Style:
        return Style(color=self.electric_blue)
    
    @property
    def border_style(self) -> Style:
        return Style(color=self.rust_brown)
    
    @property
    def accent_style(self) -> Style:
        return Style(color=self.concrete_gray)
    
    @property
    def title_style(self) -> Style:
        return Style(color=self.acid_green, bold=True)


class RichTuiApp:
    """Rich-based TUI application with Alien: Earth theming."""
    
    def __init__(
        self,
        settings: ArtistMatrixSettings | None = None,
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ):
        self.settings = settings or ArtistMatrixSettings()
        self.theme = AlienTheme()
        self.console = Console()
        self.assets = TuiAssets()
        self.session = SessionState()
        
        # Initialize services
        self.soul_forge = SoulForgeService(
            persona_generator=build_persona_generator(self.settings),
            avatar_generator=build_avatar_generator(self.settings),
            repository=ArtistProfileRepository(self.settings.data_root),
        )
        
        self.creation_engine = CreationEngineService(
            lyric_generator=build_lyric_generator(self.settings),
            audio_generator=build_audio_generator(self.settings),
            repository=TrackManifestRepository(self.settings.data_root),
        )
        
        self.ideation_llm = TrackIdeationLLM.build(self.settings)
        self.ideation_store = TrackIdeationStore(self.settings)
        
        # Initialize echo chamber service with empty clients for now
        # In a full implementation, these would be configured from settings
        self.echo_chamber = EchoChamberService(clients=[])
        
        # Session logging
        self._session_logger: SessionLogger | None = None
        
        # For compatibility with existing interface
        self._input = input_fn or input
        self._output = output_fn or self.console.print
    
    @property
    def session_state(self) -> SessionState:
        """Access to session state."""
        return self.session
    
    def _open_session_log(self) -> None:
        """Initialize session logging."""
        if self.settings.tui_log_dir:
            self._session_logger = SessionLogger(self.settings.tui_log_dir)
    
    def _close_session_log(self) -> None:
        """Close session logging."""
        if self._session_logger:
            self._session_logger.close()
            self._session_logger = None
    
    def _log_event(self, source: str, message: str) -> None:
        """Log an event to the session log."""
        if self._session_logger:
            self._session_logger.write_event(role=source, message=message)
    
    def build_banner(self) -> Panel:
        """Create stylized ASCII banner with Alien theme."""
        banner_text = Text()
        banner_text.append("ARTIST MATRIX", style=self.theme.title_style)
        banner_text.append("\n")
        banner_text.append("WEYLAND-YUTANI CORP", style=self.theme.accent_style)
        banner_text.append(" [WY] ", style=self.theme.warning_style)
        banner_text.append("PRIORITY TRANSMISSION", style=self.theme.accent_style)
        
        # Add hazard stripes
        banner_text.append("\n")
        banner_text.append(self.theme.hazard_stripes, style=self.theme.warning_style)
        
        return Panel(
            banner_text,
            style=self.theme.border_style,
            border_style=self.theme.rust_brown,
            title="NOSTROMO TERMINAL",
            title_align="center",
        )
    
    def build_main_menu(self) -> Panel:
        """Create main menu with Rich Table layout."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Option", style=self.theme.info_style)
        table.add_column("Arrow", style=self.theme.accent_style) 
        table.add_column("Destination", style=self.theme.warning_style)
        table.add_column("Status", style=self.theme.accent_style)
        
        # Menu options with alien-themed descriptions
        table.add_row("[1] Generate Avatar", "→", "Soul Forge", f"{self.theme.radar_blip}")
        table.add_row("[2] Select Avatar", "→", "Archives", f"{self.theme.radar_blip}")
        table.add_row("[3] Creation Workbench", "→", "Track Forge", f"{self.theme.radar_blip}")
        table.add_row("[4] Launch Echo Chamber", "→", "Broadcast", f"{self.theme.radar_blip}")
        table.add_row("[Q] Quit Terminal", "→", "Sleep Cycle", f"{self.theme.alien_head}")
        
        return Panel(
            table,
            style=self.theme.border_style,
            border_style=self.theme.rust_brown,
            title="COMMAND INTERFACE",
            subtitle=f"STATUS: OPERATIONAL {self.theme.weyland_yutani_tag}",
            subtitle_align="right",
        )
    
    def slow_type_reveal(self, text: str, delay: float = 0.03) -> None:
        """Display text with slow typing effect for atmosphere."""
        with Live(Text(""), refresh_per_second=30) as live:
            display_text = Text()
            for char in text:
                display_text.append(char, style=self.theme.info_style)
                live.update(display_text)
                time.sleep(delay)
    
    def glitch_effect(self, text: str) -> None:
        """Display text with glitch/static effect."""
        glitch_chars = ["█", "▓", "▒", "░", "▄", "▀"]
        
        with Live(Text(""), refresh_per_second=10) as live:
            # Show glitch
            for _ in range(3):
                glitch_text = Text()
                for char in text:
                    if char.isalnum():
                        glitch_text.append(
                            glitch_chars[hash(char) % len(glitch_chars)],
                            style=self.theme.warning_style
                        )
                    else:
                        glitch_text.append(char, style=self.theme.accent_style)
                live.update(glitch_text)
                time.sleep(0.1)
            
            # Reveal actual text
            final_text = Text(text, style=self.theme.info_style)
            live.update(final_text)
            time.sleep(0.5)
    
    def show_loading(self, message: str) -> None:
        """Display loading spinner with alien theming."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                f"{self.theme.weyland_yutani_tag} {message}...",
                total=None
            )
            time.sleep(2)  # Simulate work
            progress.remove_task(task)
    
    def prompt_with_theme(self, question: str, default: str | None = None) -> str:
        """Rich-themed input prompt."""
        styled_question = Text()
        styled_question.append(f"{self.theme.radar_blip} ", style=self.theme.warning_style)
        styled_question.append(question, style=self.theme.info_style)
        if default:
            styled_question.append(f" [{default}]", style=self.theme.accent_style)
        styled_question.append(": ", style=self.theme.warning_style)
        
        self.console.print(styled_question, end="")
        return input() or default or ""
    
    def confirm_with_theme(self, question: str) -> bool:
        """Rich-themed confirmation prompt."""
        styled_question = Text()
        styled_question.append(f"{self.theme.weyland_yutani_tag} ", style=self.theme.warning_style)
        styled_question.append(question, style=self.theme.info_style)
        styled_question.append(" [y/N]", style=self.theme.accent_style)
        styled_question.append(": ", style=self.theme.warning_style)
        
        self.console.print(styled_question, end="")
        response = input().lower()
        return response in ('y', 'yes')
    
    def run(self) -> None:
        """Main application loop with Rich interface."""
        self._open_session_log()
        try:
            # Boot sequence with effects
            self.slow_type_reveal("INITIALIZING ARTIST MATRIX TERMINAL...", 0.05)
            self.console.print()
            self.glitch_effect("ESTABLISHING SECURE CONNECTION...")
            self.console.print()
            
            while True:
                # Clear and show interface
                self.console.clear()
                self.console.print(self.build_banner())
                self.console.print()
                self.console.print(self.build_main_menu())
                self.console.print()
                
                # Get user choice with themed prompt
                choice = self.prompt_with_theme("Select mode", "1").strip().lower()
                self._log_event("user", choice)
                
                if choice in {"1", "g", "generate"}:
                    self.handle_generate()
                elif choice in {"2", "s", "select"}:
                    self.handle_select()
                elif choice in {"3", "c", "create", "workbench"}:
                    self.handle_workbench()
                elif choice in {"4", "e", "echo"}:
                    self.handle_echo()
                elif choice in {"q", "quit", "exit"}:
                    self.console.print(
                        f"{self.theme.weyland_yutani_tag} SHUTTING DOWN ARTIST MATRIX SHELL",
                        style=self.theme.warning_style
                    )
                    self.slow_type_reveal("See you in the wasteland...", 0.1)
                    self._log_event("assistant", "session_exit")
                    break
                else:
                    self.console.print(
                        f"{self.theme.weyland_yutani_tag} INVALID COMMAND",
                        style=self.theme.warning_style
                    )
                    time.sleep(1)
        
        except KeyboardInterrupt:
            self.console.print(
                f"\n{self.theme.weyland_yutani_tag} EMERGENCY SHUTDOWN INITIATED",
                style=self.theme.warning_style
            )
        except Exception as exc:
            self.console.print(
                f"\n{self.theme.weyland_yutani_tag} SYSTEM ERROR: {exc}",
                style=self.theme.warning_style
            )
        finally:
            log_path = self._session_logger.path if self._session_logger else None
            self._close_session_log()
            if log_path:
                self.console.print(f"Session log saved to {log_path}")
    
    def handle_generate(self) -> None:
        """Handle avatar generation flow."""
        self.console.print(
            f"\n{self.theme.weyland_yutani_tag} SOUL FORGE // Persona constructor engaged",
            style=self.theme.warning_style
        )
        
        draft = self._collect_persona_draft()
        if draft is None:
            self.console.print(
                f"\n{self.theme.weyland_yutani_tag} Persona creation cancelled. Returning to main menu.",
                style=self.theme.info_style
            )
            return

        self.session_state.draft = draft
        self.console.print(
            f"\n{self.theme.weyland_yutani_tag} Forging persona... stand by",
            style=self.theme.warning_style
        )
        
        # Show loading with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("Initializing Soul Forge matrix...", total=None)
            
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
                        refinement_instructions=draft.refinement_instructions,
                    )
                )
                progress.remove_task(task)
            except Exception as exc:
                progress.remove_task(task)
                self.console.print(
                    f"\n{self.theme.weyland_yutani_tag} FORGE FAILURE: {exc}",
                    style=self.theme.warning_style
                )
                if self.session_state.last_manifest_path:
                    self.console.print(
                        f"Last successful manifest stored at {self.session_state.last_manifest_path}",
                        style=self.theme.info_style
                    )
                return

        # Process results
        profile_obj = result.get("profile")
        manifest_path = Path(str(result.get("manifest_path")))
        avatar_obj = result.get("avatar")

        # Ensure types for display
        profile: ArtistProfile | None = profile_obj if isinstance(profile_obj, ArtistProfile) else None
        avatar: AvatarBlueprint | None = avatar_obj if isinstance(avatar_obj, AvatarBlueprint) else None

        if profile:
            self.session_state.last_profile = profile
            self._update_suggestions(profile, draft)
            
        self.session_state.last_manifest_path = manifest_path
        if avatar:
            self.session_state.last_avatar = avatar

        # Display success with Rich formatting
        self._display_generation_success(profile, avatar, manifest_path, draft)
        self._log_event("assistant", "persona_generated")
        self._post_persona_prompt()
    
    def _collect_persona_draft(self) -> PersonaWizardDraft | None:
        """Collect persona information with Rich UI."""
        draft = PersonaWizardDraft(
            name=self.session_state.draft.name,
            genre=self.session_state.draft.genre,
            mood=self.session_state.draft.mood,
            influences=self.session_state.draft.influences,
            descriptors=self.session_state.draft.descriptors,
            brief=self.session_state.draft.brief,
            visual_palette=self.session_state.draft.visual_palette,
            narrative_tone=self.session_state.draft.narrative_tone,
            safety_notes=self.session_state.draft.safety_notes,
        )

        steps = [
            ("name", "Artist alias", True, "text"),
            ("genre", "Primary genre", True, "text"),
            ("mood", "Mood or energy signature", True, "text"),
            ("influences", "Influences (comma-separated, leave blank if none)", False, "sequence"),
            ("descriptors", "Descriptors or persona tags (comma-separated)", False, "sequence"),
            ("brief", "One-line creative brief (optional)", False, "text"),
            ("visual_palette", "Visual palette cues (comma-separated)", False, "sequence"),
            ("narrative_tone", "Narrative tone (optional)", False, "text"),
            ("safety_notes", "Safety guardrails (optional)", False, "text"),
        ]

        # Display instructions
        instructions_panel = Panel(
            Text("Enter '<' to go back, '.' to keep the current value, or provide new input.", 
                 style=self.theme.info_style),
            title="[WY] Navigation Instructions",
            border_style=self.theme.border_style
        )
        self.console.print(instructions_panel)

        index = 0
        while True:
            # Reset to start of editing steps
            while index < len(steps):
                key, prompt, required, kind = steps[index]
                current_value = getattr(draft, key)
                display_value = (
                    ", ".join(current_value) if isinstance(current_value, tuple) 
                    else current_value or "—"
                )
                
                # Create styled prompt
                styled_prompt = Text()
                styled_prompt.append(f"{self.theme.radar_blip} ", style=self.theme.warning_style)
                styled_prompt.append(f"Step {index + 1}/{len(steps)}: {prompt}", style=self.theme.info_style)
                styled_prompt.append(f" [{display_value}]", style=self.theme.accent_style)
                styled_prompt.append(": ", style=self.theme.warning_style)
                
                self.console.print(styled_prompt, end="")
                raw = input().strip()
                
                if raw in {"<", "b", "back"}:
                    if index == 0:
                        self.console.print("  Already at the first step.", style=self.theme.accent_style)
                        continue
                    index -= 1
                    continue
                if raw == ".":
                    index += 1
                    continue
                if not raw:
                    if required and not current_value:
                        self.console.print("  Please provide a value.", style=self.theme.warning_style)
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
                except ValueError as exc:
                    self.console.print(f"  Invalid input: {exc}", style=self.theme.warning_style)
                    continue
                index += 1

            # Summary and confirmation loop
            while True:
                self._display_draft_summary(draft)
                
                action_prompt = Text()
                action_prompt.append(f"{self.theme.weyland_yutani_tag} Action ", style=self.theme.warning_style)
                action_prompt.append("[f]orge / [r]efine / [e]dit / [c]ancel", style=self.theme.info_style)
                action_prompt.append(": ", style=self.theme.warning_style)
                
                self.console.print(action_prompt, end="")
                action = input().strip().lower()
                
                if action in {"f", "forge"}:
                    return draft
                if action in {"c", "cancel"}:
                    self.session_state.draft = draft
                    return None
                if action in {"r", "refine"}:
                    refined = self._refine_with_ai(draft)
                    if refined is None:
                        self.session_state.draft = draft
                        return None
                    draft = refined
                    continue
                if action in {"e", "edit"}:
                    target = self.prompt_with_theme(" Step number to edit (blank for first)")
                    if target.isdigit():
                        idx = int(target) - 1
                        if 0 <= idx < len(steps):
                            index = idx
                        else:
                            self.console.print("  Invalid step number.", style=self.theme.warning_style)
                            continue
                    else:
                        index = 0
                    # Re-enter the editing loop
                    break
                self.console.print("  Enter 'f', 'e', or 'c'.", style=self.theme.accent_style)
    
    def _display_draft_summary(self, draft: PersonaWizardDraft) -> None:
        """Display draft summary in Rich Table format."""
        def fmt(value: object) -> str:
            if isinstance(value, tuple):
                return ", ".join(value) if value else "—"
            return value if isinstance(value, str) and value else "—"

        table = Table(title="PERSONA DRAFT SUMMARY", title_style=self.theme.title_style)
        table.add_column("Field", style=self.theme.accent_style)
        table.add_column("Value", style=self.theme.info_style)
        
        table.add_row("1. Name", fmt(draft.name))
        table.add_row("2. Genre", fmt(draft.genre))
        table.add_row("3. Mood", fmt(draft.mood))
        table.add_row("4. Influences", fmt(draft.influences))
        table.add_row("5. Descriptors", fmt(draft.descriptors))
        table.add_row("6. Brief", fmt(draft.brief))
        table.add_row("7. Visual palette", fmt(draft.visual_palette))
        table.add_row("8. Narrative tone", fmt(draft.narrative_tone))
        table.add_row("9. Safety notes", fmt(draft.safety_notes))
        table.add_row("10. Refinement instr", fmt(draft.refinement_instructions))
        
        summary_panel = Panel(table, border_style=self.theme.border_style)
        self.console.print(summary_panel)
    
    def _refine_with_ai(self, draft: PersonaWizardDraft) -> PersonaWizardDraft | None:
        """Refine draft with AI assistance."""
        generator = getattr(self.soul_forge, "persona_generator", None)
        if generator is None:
            self.console.print("  Persona generator unavailable.", style=self.theme.warning_style)
            return draft
        if getattr(generator, "prompt_agent", None) is None:
            self.console.print("  No AI provider configured; using heuristic fallback.", style=self.theme.info_style)

        instructions = list(draft.refinement_instructions)
        
        self.console.print(
            Panel("Enter refinement instructions for the AI. Type 'done' when finished.", 
                  title="[WY] AI Refinement Mode", border_style=self.theme.border_style)
        )
        
        while True:
            instruction_prompt = Text()
            instruction_prompt.append(f"{self.theme.alien_head} ", style=self.theme.warning_style)
            instruction_prompt.append("Refinement note (blank to finish, 'c' to cancel)", style=self.theme.info_style)
            instruction_prompt.append(": ", style=self.theme.warning_style)
            
            self.console.print(instruction_prompt, end="")
            instruction = input().strip()
            
            if not instruction or instruction.lower() == "done":
                if not instructions:
                    self.console.print("  No instructions provided; skipping refinement.", style=self.theme.accent_style)
                    return draft
                break
            if instruction.lower() in {"c", "cancel"}:
                self.console.print("  Refinement cancelled.", style=self.theme.accent_style)
                return draft
            instructions.append(instruction)
            self.console.print(f"  Added: {instruction}", style=self.theme.accent_style)

        # Store refinement instructions
        object.__setattr__(draft, "refinement_instructions", tuple(instructions))
        self.console.print("  AI refinement complete.", style=self.theme.info_style)
        return draft
    
    def _display_generation_success(self, profile: ArtistProfile | None, avatar: AvatarBlueprint | None, 
                                   manifest_path: Path, draft: PersonaWizardDraft) -> None:
        """Display successful persona generation results."""
        success_text = Text()
        success_text.append(f"{self.theme.weyland_yutani_tag} ", style=self.theme.warning_style)
        success_text.append("Persona forged successfully!", style=self.theme.info_style)
        
        table = Table(title="FORGE RESULTS", title_style=self.theme.title_style)
        table.add_column("Component", style=self.theme.accent_style)
        table.add_column("Status", style=self.theme.info_style)
        
        table.add_row("Manifest", str(manifest_path))
        
        if isinstance(profile, ArtistProfile):
            table.add_row("Artist slug", profile.slug)
            table.add_row("Lyric style", profile.lyric_style)
            table.add_row("Visual mode", profile.visual_style)
            
        if isinstance(avatar, AvatarBlueprint):
            table.add_row("Avatar prompt", f"'{avatar.prompt}' (seed={avatar.seed or 'n/a'})")
            table.add_row("Avatar asset", str(avatar.asset_path) if avatar.asset_path else "n/a")
            
        if draft.visual_palette:
            table.add_row("Visual palette", ", ".join(draft.visual_palette))
        if draft.narrative_tone:
            table.add_row("Narrative tone", draft.narrative_tone)
        if draft.safety_notes:
            table.add_row("Safety notes", draft.safety_notes)
        
        result_panel = Panel(table, border_style=self.theme.border_style)
        self.console.print(success_text)
        self.console.print(result_panel)
    
    def _update_suggestions(self, profile: ArtistProfile, draft: PersonaWizardDraft) -> None:
        """Update session suggestions based on generated profile."""
        # Create track brief suggestion
        seed_tags = tuple(
            tag.strip()
            for tag in (
                tuple(draft.descriptors)
                or tuple(draft.influences)
                or tuple(profile.influences)
            )
            if isinstance(tag, str) and tag.strip()
        )
        seed_notes = tuple(
            note.strip()
            for note in (draft.brief, draft.narrative_tone)
            if isinstance(note, str) and note.strip()
        )
        default_draft = TrackIdeationDraft(
            persona_slug=profile.slug,
            title=f"{profile.name} Anthem",
            style=draft.mood or profile.visual_style or profile.lyric_style,
            tags=seed_tags,
            notes=seed_notes,
            allow_instrumental=True,
        )
        self.session_state.track_draft = default_draft
        self.session_state.transcript = []
        try:
            self.ideation_store.save_draft(default_draft)
        except Exception as exc:
            self.console.print(f" Warning: unable to persist initial track draft ({exc}).", style=self.theme.warning_style)
    
    def _post_persona_prompt(self) -> None:
        """Prompt user for next action after persona generation."""
        next_panel = Panel(
            Text("What would you like to do next?", style=self.theme.info_style),
            title="[WY] Next Actions Available",
            border_style=self.theme.border_style
        )
        self.console.print(next_panel)
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Option", style=self.theme.info_style)
        table.add_column("Action", style=self.theme.warning_style)
        
        table.add_row("[3] Creation Workbench", "→ Start track ideation")
        table.add_row("[4] Echo Chamber", "→ Plan social campaign")
        table.add_row("[Enter] Main Menu", "→ Return to main interface")
        
        self.console.print(table)
        
        choice_prompt = Text()
        choice_prompt.append(f"{self.theme.radar_blip} ", style=self.theme.warning_style)
        choice_prompt.append("Quick jump (3/4/Enter)", style=self.theme.info_style)
        choice_prompt.append(": ", style=self.theme.warning_style)
        
        self.console.print(choice_prompt, end="")
        choice = input().strip().lower()
        
        if choice in {"3", "c", "creation", "workbench"}:
            self.handle_workbench()
        elif choice in {"4", "e", "echo"}:
            self.handle_echo()
        # Otherwise return to main menu
    
    def handle_select(self) -> None:
        """Handle avatar selection flow."""
        self.console.print(
            f"\n{self.theme.weyland_yutani_tag} ACCESSING ARCHIVES",
            style=self.theme.warning_style
        )
        
        # Show loading effect
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("Scanning Personnel Files...", total=None)
            records = self._load_persona_records()
            progress.remove_task(task)
        
        if not records:
            no_personas_panel = Panel(
                Text("No personas available. Use 'Generate Avatar' to forge a new profile.", 
                     style=self.theme.info_style),
                title="[WY] Archive Status",
                border_style=self.theme.border_style
            )
            self.console.print(no_personas_panel)
            return

        while True:
            self._display_persona_list(records)
            
            choice_prompt = Text()
            choice_prompt.append(f"{self.theme.radar_blip} ", style=self.theme.warning_style)
            choice_prompt.append("Select persona number or Q to cancel", style=self.theme.info_style)
            choice_prompt.append(": ", style=self.theme.warning_style)
            
            self.console.print(choice_prompt, end="")
            choice = input().strip().lower()
            
            if choice in {"q", "quit", "exit"}:
                self.console.print(
                    f" {self.theme.weyland_yutani_tag} Selection cancelled; returning to main menu.",
                    style=self.theme.info_style
                )
                return
            if not choice.isdigit():
                self.console.print("  Enter a valid number or Q to cancel.", style=self.theme.warning_style)
                continue

            index = int(choice) - 1
            if index < 0 or index >= len(records):
                self.console.print("  Invalid selection. Try again.", style=self.theme.warning_style)
                continue

            record = records[index]
            self._display_manifest_preview(record.manifest)
            
            if self.confirm_with_theme("Load this persona?"):
                if self._apply_persona_selection(record):
                    success_text = Text()
                    success_text.append(f"{self.theme.weyland_yutani_tag} ", style=self.theme.warning_style)
                    success_text.append(f"Persona '{record.manifest.get('name', '<unknown>')}' loaded into session.", 
                                       style=self.theme.info_style)
                    self.console.print(success_text)
                    self._post_persona_prompt()
                    return
                self.console.print("  Unable to load persona; select another entry.", style=self.theme.warning_style)
    
    def _display_persona_list(self, records: list[PersonaRecord]) -> None:
        """Display available personas in Rich Table format."""
        table = Table(title="AVAILABLE PERSONAS", title_style=self.theme.title_style)
        table.add_column("#", style=self.theme.accent_style, width=3)
        table.add_column("Name", style=self.theme.info_style)
        table.add_column("Slug", style=self.theme.accent_style)
        table.add_column("Lyric Style", style=self.theme.info_style)
        table.add_column("Status", style=self.theme.warning_style)
        
        for idx, record in enumerate(records, 1):
            manifest = record.manifest
            name = manifest.get("name", "<unknown>")
            slug = manifest.get("slug", "?")
            lyric = manifest.get("lyric_style", "n/a")
            
            table.add_row(
                str(idx),
                str(name),
                str(slug),
                str(lyric),
                self.theme.radar_blip
            )
        
        archive_panel = Panel(table, border_style=self.theme.border_style)
        self.console.print(archive_panel)
    
    def _display_manifest_preview(self, manifest: dict[str, object]) -> None:
        """Display detailed manifest preview."""
        def fmt_list(value: object) -> str:
            items = self._as_str_list(value)
            return ", ".join(items) if items else "—"

        table = Table(title="PERSONA PREVIEW", title_style=self.theme.title_style)
        table.add_column("Field", style=self.theme.accent_style)
        table.add_column("Value", style=self.theme.info_style)
        
        table.add_row("Name", str(manifest.get('name', '<unknown>')))
        table.add_row("Slug", str(manifest.get('slug', '—')))
        table.add_row("Lyric style", str(manifest.get('lyric_style', '—')))
        table.add_row("Visual mode", str(manifest.get('visual_style', '—')))
        table.add_row("Tags", fmt_list(manifest.get('persona_tags', [])))
        table.add_row("Influences", fmt_list(manifest.get('influences', [])))
        table.add_row("Visuals", fmt_list(manifest.get('visual_palette', [])))
        table.add_row("Narrative", str(manifest.get('narrative_tone', '—')))
        table.add_row("Safeguards", str(manifest.get('safety_notes', '—')))
        
        preview_panel = Panel(table, border_style=self.theme.border_style)
        self.console.print(preview_panel)
    
    def _load_persona_records(self) -> list[PersonaRecord]:
        """Load persona records from data directory."""
        artists_dir = self.settings.data_root / "artists"
        if not artists_dir.exists():
            return []

        records: list[PersonaRecord] = []
        for path in sorted(artists_dir.glob("*.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                records.append(PersonaRecord(path=path, manifest=manifest))
            except (OSError, json.JSONDecodeError) as exc:
                self.console.print(f"  Skipping corrupt manifest {path.name}: {exc}", style=self.theme.warning_style)
        return records
    
    def _apply_persona_selection(self, record: PersonaRecord) -> bool:
        """Apply selected persona to current session."""
        manifest = record.manifest
        path = record.path
        try:
            from pydantic import ValidationError
            profile = ArtistProfile.model_validate(manifest)
        except ValidationError as exc:
            self.console.print(f"  Manifest validation failed: {exc}", style=self.theme.warning_style)
            return False

        avatar_data = manifest.get("avatar")
        avatar = None
        if isinstance(avatar_data, dict):
            asset_path = avatar_data.get("asset_path")
            avatar = AvatarBlueprint(
                prompt=avatar_data.get("prompt", ""),
                seed=avatar_data.get("seed"),
                asset_path=Path(asset_path) if asset_path else None,
            )

        self.session_state.last_profile = profile
        self.session_state.last_manifest_path = path
        self.session_state.last_avatar = avatar
        self.session_state.draft = PersonaWizardDraft(
            name=profile.name,
            genre=str(manifest.get("genre", profile.lyric_style)),
            mood=str(manifest.get("mood", "")),
            influences=tuple(self._as_str_list(manifest.get("influences", []))),
            descriptors=tuple(self._as_str_list(manifest.get("persona_tags", []))),
            brief=str(manifest.get("brief", "")),
            visual_palette=tuple(self._as_str_list(manifest.get("visual_palette", []))),
            narrative_tone=str(manifest.get("narrative_tone", "")),
            safety_notes=str(manifest.get("safety_notes", "")),
        )
        
        # Update suggestions for downstream workflows
        self._update_suggestions(profile, self.session_state.draft)
        return True
    
    def _as_str_list(self, value: object) -> list[str]:
        """Convert value to list of strings."""
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if item]
        return []
    
    def handle_workbench(self) -> None:
        """Handle creation workbench flow."""
        profile = self.session_state.last_profile
        if profile is None:
            no_persona_panel = Panel(
                Text("No persona selected. Generate or select a profile first.", 
                     style=self.theme.info_style),
                title="[WY] Workbench Status",
                border_style=self.theme.border_style
            )
            self.console.print(no_persona_panel)
            return

        self.console.print(
            f"\n{self.theme.weyland_yutani_tag} TRACK FORGE ONLINE",
            style=self.theme.warning_style
        )

        draft = self._ensure_track_draft(profile)
        transcript = list(self.session_state.transcript)
        session_turns: list[ChatTurn] = []
        pending_fields: dict[str, object] | None = None
        history: list[TrackIdeationDraft] = []
        last_assistant_text: str | None = None

        # Display workbench intro
        intro_panel = Panel(
            Text.from_markup(
                "Type a message to brainstorm with the assistant.\n"
                "Commands: [bold]/help[/], [bold]/show[/], [bold]/adopt[/], "
                "[bold]/edit <field>: <value>[/], [bold]/undo[/], [bold]/finalize[/], [bold]/back[/]\n"
                "Only [bold]/adopt[/] or [bold]/edit[/] updates the draft."
            ),
            title="[WY] Creation Workbench // Chat Mode",
            border_style=self.theme.border_style
        )
        self.console.print(intro_panel)
        
        if self.ideation_llm is None:
            self.console.print(
                "AI assistant disabled (configure ARTIST_MATRIX_PERSONA_PROVIDER/MODEL/API_KEY for DeepSeek).",
                style=self.theme.accent_style
            )

        while True:
            # Create workbench prompt
            workbench_prompt = Text()
            workbench_prompt.append(f"{self.theme.alien_head} ", style=self.theme.warning_style)
            workbench_prompt.append("workbench", style=self.theme.info_style)
            workbench_prompt.append("> ", style=self.theme.warning_style)
            
            self.console.print(workbench_prompt, end="")
            user_input = input().strip()
            
            if not user_input:
                continue

            if user_input.startswith("/"):
                command = user_input[1:].strip()
                lowered = command.lower()

                if lowered in {"back", "exit", "quit"}:
                    break

                if lowered == "help":
                    self._show_workbench_help()
                    continue

                if lowered == "show":
                    self._display_draft_snapshot(draft, pending_fields)
                    continue

                if lowered == "undo":
                    if not history:
                        self.console.print(" Nothing to undo.", style=self.theme.accent_style)
                        continue
                    draft = history.pop()
                    self.session_state.track_draft = draft
                    pending_fields = None
                    self._log_event("user", "draft:undo")
                    self.console.print(" Reverted last change.", style=self.theme.info_style)
                    continue

                if lowered == "adopt":
                    if not pending_fields:
                        self.console.print(" No pending suggestion to adopt.", style=self.theme.accent_style)
                        continue
                    
                    new_draft, applied, errors = self._apply_draft_updates(
                        draft, pending_fields, mode="adopt", summary=last_assistant_text
                    )
                    
                    if errors:
                        for message in errors:
                            self.console.print(f" ! {message}", style=self.theme.warning_style)
                    if not applied:
                        self.console.print(" Nothing applied from the suggestion.", style=self.theme.accent_style)
                        pending_fields = None
                        continue
                    
                    history.append(draft)
                    draft = new_draft
                    self.session_state.track_draft = draft
                    pending_fields = None
                    self._log_event("assistant", f"draft:adopt:{','.join(applied)}")
                    self.console.print(f" Adopted: {', '.join(applied)}.", style=self.theme.info_style)
                    continue

                if lowered.startswith("edit"):
                    remainder = command[4:].strip()
                    if not remainder:
                        self.console.print(" Usage: /edit field: value", style=self.theme.accent_style)
                        continue
                    if ":" not in remainder:
                        self.console.print(" Use format field: value", style=self.theme.accent_style)
                        continue
                    
                    field_name, raw_value = remainder.split(":", 1)
                    field_key = self._normalize_field_name(field_name.strip())
                    if not field_key:
                        self.console.print(f" Unknown field '{field_name.strip()}'.", style=self.theme.warning_style)
                        continue
                    
                    updates: dict[str, object] = {field_key: raw_value.strip()}
                    new_draft, applied, errors = self._apply_draft_updates(
                        draft, updates, mode="manual", summary=last_assistant_text
                    )
                    
                    if errors:
                        for message in errors:
                            self.console.print(f" ! {message}", style=self.theme.warning_style)
                    if not applied:
                        self.console.print(" No changes applied.", style=self.theme.accent_style)
                        continue
                    
                    history.append(draft)
                    draft = new_draft
                    self.session_state.track_draft = draft
                    pending_fields = None
                    self._log_event("user", f"draft:edit:{','.join(applied)}")
                    self.console.print(f" Updated {', '.join(applied)}.", style=self.theme.info_style)
                    continue

                if lowered == "finalize":
                    ready, missing = self._draft_readiness(draft)
                    if not ready:
                        self.console.print(f" Draft not ready: {', '.join(missing)}", style=self.theme.warning_style)
                        continue
                    
                    preview = build_suno_preview(draft)
                    self._display_suno_preview(preview)
                    
                    if self.confirm_with_theme("Render with Suno now?"):
                        self._persist_chat_session(profile, draft, transcript, session_turns, final=True)
                        self._run_creation_engine(profile, draft)
                        return
                    else:
                        self.console.print(" Preview complete. Continue editing or /back to exit.", style=self.theme.info_style)
                        continue

                self.console.print(f" Unknown command: {command}", style=self.theme.warning_style)
                continue

            # Handle regular chat input
            if self.ideation_llm is None:
                self.console.print(" AI assistant not available. Use commands only.", style=self.theme.accent_style)
                continue

            # Process AI chat with actual LLM
            self.console.print(f"{self.theme.radar_blip} Processing with AI...", style=self.theme.info_style)
            
            try:
                # Get persona summary for LLM context
                persona_summary = f"Artist: {profile.name}, Style: {profile.lyric_style}, Visual: {profile.visual_style}, Influences: {', '.join(profile.influences) if profile.influences else 'None'}"
                
                # Use apply_llm_guidance to get both response and structured data
                response_text, fields_dict, json_text = apply_llm_guidance(
                    self.ideation_llm,
                    persona_summary,
                    user_input,
                    transcript + session_turns,
                    draft
                )
                
                if response_text:
                    assistant_response = response_text
                else:
                    assistant_response = "No response from AI assistant."
                
                # Display the assistant's response  
                self.console.print(f"Assistant: {assistant_response}", style=self.theme.info_style)
                
                # If structured data was extracted, update pending fields
                if fields_dict:
                    pending_fields = fields_dict
                    self.console.print(
                        f"{self.theme.weyland_yutani_tag} Detected field updates. Use /adopt to apply or /show to review.",
                        style=self.theme.accent_style
                    )
                    
            except Exception as llm_exc:
                assistant_response = f"Error communicating with AI assistant: {llm_exc}"
                self.console.print(f"Assistant: {assistant_response}", style=self.theme.warning_style)
            
            # Add to session turns
            session_turns.append(ChatTurn(role="user", content=user_input))
            session_turns.append(ChatTurn(role="assistant", content=assistant_response))
            last_assistant_text = assistant_response
    
    def _ensure_track_draft(self, profile: ArtistProfile) -> TrackIdeationDraft:
        """Ensure we have a track draft for the current profile."""
        if self.session_state.track_draft and self.session_state.track_draft.persona_slug == profile.slug:
            return self.session_state.track_draft
        
        # Create new draft based on profile
        default_draft = TrackIdeationDraft(
            persona_slug=profile.slug,
            title=f"{profile.name} Anthem",
            style=profile.lyric_style,
            tags=tuple(profile.influences[:3]) if profile.influences else (),
            notes=(),
            allow_instrumental=True,
        )
        self.session_state.track_draft = default_draft
        try:
            self.ideation_store.save_draft(default_draft)
        except Exception as exc:
            self.console.print(f"Warning: unable to persist track draft ({exc}).", style=self.theme.warning_style)
        return default_draft
    
    def _show_workbench_help(self) -> None:
        """Display workbench help information."""
        help_table = Table(title="WORKBENCH COMMANDS", title_style=self.theme.title_style)
        help_table.add_column("Command", style=self.theme.warning_style)
        help_table.add_column("Description", style=self.theme.info_style)
        
        help_table.add_row("/help", "Show this help message")
        help_table.add_row("/show", "Display current draft snapshot")
        help_table.add_row("/adopt", "Adopt pending AI suggestion")
        help_table.add_row("/edit field: value", "Manually edit a draft field")
        help_table.add_row("/undo", "Revert last change")
        help_table.add_row("/finalize", "Preview and render with Suno")
        help_table.add_row("/back", "Exit workbench")
        
        help_panel = Panel(help_table, border_style=self.theme.border_style)
        self.console.print(help_panel)
    
    def _display_draft_snapshot(self, draft: TrackIdeationDraft, pending_fields: dict[str, object] | None) -> None:
        """Display current draft status."""
        table = Table(title="DRAFT SNAPSHOT", title_style=self.theme.title_style)
        table.add_column("Field", style=self.theme.accent_style)
        table.add_column("Value", style=self.theme.info_style)
        
        table.add_row("Title", draft.title or "—")
        table.add_row("Style", draft.style or "—")
        table.add_row("Tags", ", ".join(draft.tags) if draft.tags else "—")
        table.add_row("Lyrics", (draft.lyrics[:50] + "...") if draft.lyrics and len(draft.lyrics) > 50 else (draft.lyrics or "—"))
        table.add_row("Notes", ", ".join(draft.notes) if draft.notes else "—")
        table.add_row("Duration", f"{draft.duration_sec}s" if draft.duration_sec else "—")
        table.add_row("Instrumental", "Yes" if draft.allow_instrumental else "No")
        table.add_row("Reference URL", draft.ref_url or "—")
        
        ready, missing = self._draft_readiness(draft)
        status_text = "ready for /finalize" if ready else f"pending ({', '.join(missing)})"
        table.add_row("Status", status_text)
        
        if pending_fields:
            table.add_row("Pending", "AI suggestion available → /adopt")
        
        snapshot_panel = Panel(table, border_style=self.theme.border_style)
        self.console.print(snapshot_panel)
    
    def _draft_readiness(self, draft: TrackIdeationDraft) -> tuple[bool, list[str]]:
        """Check if draft is ready for finalization."""
        missing = []
        if not draft.title:
            missing.append("title")
        if not draft.tags:
            missing.append("tags")
        if not draft.lyrics and not (draft.style and draft.notes):
            missing.append("lyrics or detailed style/notes")
        return len(missing) == 0, missing
    
    def _normalize_field_name(self, field_name: str) -> str | None:
        """Normalize field name for draft updates."""
        field_map = {
            "title": "title",
            "style": "style", 
            "tags": "tags",
            "lyrics": "lyrics",
            "notes": "notes",
            "duration": "duration_sec",
            "instrumental": "allow_instrumental",
            "url": "ref_url",
            "ref": "ref_url",
        }
        return field_map.get(field_name.lower())
    
    def _apply_draft_updates(self, draft: TrackIdeationDraft, updates: dict[str, object], 
                           mode: str, summary: str | None) -> tuple[TrackIdeationDraft, list[str], list[str]]:
        """Apply updates to draft and return new draft, applied fields, and errors."""
        applied: list[str] = []
        errors: list[str] = []
        
        try:
            # Create a copy of the draft to modify
            new_draft = TrackIdeationDraft(
                persona_slug=draft.persona_slug,
                title=draft.title,
                style=draft.style,
                tags=list(draft.tags),
                lyrics=draft.lyrics,
                notes=draft.notes,
                duration_sec=draft.duration_sec,
                allow_instrumental=draft.allow_instrumental,
                ref_url=draft.ref_url
            )
            
            # Apply each update
            for key, value in updates.items():
                if hasattr(new_draft, key):
                    if key == "tags" and isinstance(value, list):
                        new_draft.tags = tuple(value)
                    elif key == "allow_instrumental" and isinstance(value, bool):
                        new_draft.allow_instrumental = value
                    elif key == "duration_sec" and isinstance(value, (int, float)):
                        new_draft.duration_sec = int(value)
                    elif isinstance(value, str):
                        setattr(new_draft, key, value)
                    else:
                        setattr(new_draft, key, str(value) if value is not None else "")
                    applied.append(key)
                else:
                    errors.append(f"Unknown field: {key}")
            
            return new_draft, applied, errors
        except Exception as exc:
            errors.append(f"Update failed: {exc}")
            return draft, applied, errors
    
    def _display_suno_preview(self, preview: SunoPayloadPreview) -> None:
        """Display Suno payload preview."""
        table = Table(title="SUNO PAYLOAD PREVIEW", title_style=self.theme.title_style)
        table.add_column("Field", style=self.theme.accent_style)
        table.add_column("Value", style=self.theme.info_style)
        
        table.add_row("Title", preview.title)
        table.add_row("Style", preview.style or "—")
        table.add_row("Lyrics", (preview.lyrics[:100] + "...") if preview.lyrics and len(preview.lyrics) > 100 else (preview.lyrics or "—"))
        table.add_row("Instrumental", "Yes" if preview.allow_instrumental else "No")
        table.add_row("Tags", ", ".join(preview.tags) if preview.tags else "—")
        
        preview_panel = Panel(table, border_style=self.theme.border_style)
        self.console.print(preview_panel)
    
    def _persist_chat_session(self, profile: ArtistProfile, draft: TrackIdeationDraft, 
                            transcript: list[ChatTurn], session_turns: list[ChatTurn], 
                            final: bool = False) -> None:
        """Persist chat session to storage."""
        try:
            # Update transcript with session turns
            all_turns = transcript + session_turns
            self.session_state.transcript = all_turns
            
            # Save draft
            self.ideation_store.save_draft(draft)
            self.console.print("Session persisted. Draft saved.", style=self.theme.accent_style)
        except Exception as exc:
            self.console.print(f"Warning: unable to persist session ({exc}).", style=self.theme.warning_style)
    
    def _run_creation_engine(self, profile: ArtistProfile, draft: TrackIdeationDraft) -> None:
        """Run the creation engine to generate audio."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} Initializing audio generation...",
            style=self.theme.warning_style
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task("Submitting to Suno...", total=None)
            
            try:
                # Create track job spec with correct parameters
                track_spec = TrackJobSpec(
                    title=draft.title or f"{profile.name} Track",
                    mood=draft.style or "upbeat",
                    tempo_bpm=None,
                    key=None,
                    references=tuple(),
                    narrative=". ".join(draft.notes) if draft.notes else None
                )
                
                # Create creation brief
                from artist_matrix.creation_engine.service import CreationBrief
                brief = CreationBrief(track=track_spec)
                
                # Submit to creation engine
                result = self.creation_engine.produce_track(profile, brief)
                progress.remove_task(task)
                
                # Display results
                if isinstance(result, TrackArtifact):
                    success_table = Table(title="TRACK GENERATION COMPLETE", title_style=self.theme.title_style)
                    success_table.add_column("Component", style=self.theme.accent_style)
                    success_table.add_column("Value", style=self.theme.info_style)
                    
                    success_table.add_row("Title", result.title)
                    success_table.add_row("Audio", str(result.audio_path))
                    if result.duration_seconds:
                        success_table.add_row("Duration", f"{result.duration_seconds:.1f}s")
                    if result.preview_url:
                        success_table.add_row("Preview", result.preview_url)
                    
                    result_panel = Panel(success_table, border_style=self.theme.border_style)
                    self.console.print(result_panel)
                else:
                    self.console.print("Track generation completed successfully.", style=self.theme.info_style)
                    
            except Exception as exc:
                progress.remove_task(task)
                self.console.print(
                    f"{self.theme.weyland_yutani_tag} Generation failed: {exc}",
                    style=self.theme.warning_style
                )
    
    def handle_echo(self) -> None:
        """Handle echo chamber campaign planning flow."""
        if not self.session_state.last_profile:
            self.console.print(
                f"{self.theme.weyland_yutani_tag} No persona selected. Select an artist first.",
                style=self.theme.warning_style
            )
            return
        
        self.console.print(
            f"{self.theme.weyland_yutani_tag} BROADCAST ARRAY ACTIVE",
            style=self.theme.warning_style
        )
        self.show_loading("Establishing Communications")
        
        try:
            self._run_echo_chamber_planner()
        except KeyboardInterrupt:
            self.console.print(
                f"\n{self.theme.weyland_yutani_tag} Campaign planning aborted.",
                style=self.theme.info_style
            )
    
    def _run_echo_chamber_planner(self) -> None:
        """Run the Echo Chamber campaign planning interface."""
        profile = self.session_state.last_profile
        if not profile:
            return
        
        # Display persona header
        persona_header = Panel(
            f"Campaign Planner for [bold]{profile.name}[/bold]\n"
            f"Style: {profile.lyric_style}\n"
            f"Visual: {profile.visual_style}",
            title=f"{self.theme.weyland_yutani_tag} ARTIST PROFILE",
            border_style=self.theme.border_style
        )
        self.console.print(persona_header)
        
        while True:
            self.console.print()
            menu_table = Table(title="CAMPAIGN COMMAND CENTER", title_style=self.theme.title_style)
            menu_table.add_column("Option", style=self.theme.accent_style, width=4)
            menu_table.add_column("Action", style=self.theme.info_style)
            
            menu_table.add_row("1", "Create New Campaign")
            menu_table.add_row("2", "Review Existing Campaigns")
            menu_table.add_row("3", "Schedule Posts")
            menu_table.add_row("4", "Analytics Dashboard")
            menu_table.add_row("q", "Return to Main Menu")
            
            menu_panel = Panel(menu_table, border_style=self.theme.border_style)
            self.console.print(menu_panel)
            
            choice = self.prompt_with_theme("Select operation")
            
            if choice.lower() == "q":
                break
            elif choice == "1":
                self._create_campaign(profile)
            elif choice == "2":
                self._review_campaigns(profile)
            elif choice == "3":
                self._schedule_posts(profile)
            elif choice == "4":
                self._show_analytics(profile)
            else:
                self.console.print(
                    f"{self.theme.weyland_yutani_tag} Invalid selection",
                    style=self.theme.warning_style
                )
    
    def _create_campaign(self, profile: ArtistProfile) -> None:
        """Create a new social media campaign."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} CAMPAIGN CREATION PROTOCOL",
            style=self.theme.warning_style
        )
        
        # Collect campaign details
        title = self.prompt_with_theme("Campaign title")
        if not title:
            self.console.print("Campaign creation cancelled.", style=self.theme.info_style)
            return
        
        platform = self.prompt_with_theme("Target platform (twitter/instagram/discord)")
        if platform.lower() not in ["twitter", "instagram", "discord"]:
            self.console.print("Invalid platform. Defaulting to twitter.", style=self.theme.warning_style)
            platform = "twitter"
        
        # Collect campaign beats
        beats = []
        self.console.print("\nEnter campaign beats (empty line to finish):")
        beat_num = 1
        while True:
            beat = self.prompt_with_theme(f"Beat {beat_num}")
            if not beat:
                break
            beats.append(beat)
            beat_num += 1
        
        if not beats:
            self.console.print("No beats provided. Campaign creation cancelled.", style=self.theme.warning_style)
            return
        
        cadence = self.prompt_with_theme("Cadence in minutes (default: 120)")
        try:
            cadence_minutes = int(cadence) if cadence else 120
        except ValueError:
            cadence_minutes = 120
            self.console.print("Invalid cadence. Using default 120 minutes.", style=self.theme.warning_style)
        
        # Create campaign object
        from artist_matrix.echo_chamber.planner import SocialCampaign
        campaign = SocialCampaign(
            title=title,
            platform=platform,
            beats=beats,
            cadence_minutes=cadence_minutes
        )
        
        # Display campaign preview
        self._display_campaign_preview(campaign)
        
        if self.confirm_with_theme("Save this campaign?"):
            # In a real implementation, we'd save to disk
            self.console.print(
                f"{self.theme.weyland_yutani_tag} Campaign '{title}' created successfully",
                style=self.theme.info_style
            )
        else:
            self.console.print("Campaign creation cancelled.", style=self.theme.info_style)
    
    def _display_campaign_preview(self, campaign: SocialCampaign) -> None:
        """Display a preview of the campaign."""
        preview_table = Table(title="CAMPAIGN PREVIEW", title_style=self.theme.title_style)
        preview_table.add_column("Field", style=self.theme.accent_style)
        preview_table.add_column("Value", style=self.theme.info_style)
        
        preview_table.add_row("Title", campaign.title)
        preview_table.add_row("Platform", campaign.platform.upper())
        preview_table.add_row("Beats", str(len(campaign.beats)))
        preview_table.add_row("Cadence", f"{campaign.cadence_minutes} minutes")
        
        preview_panel = Panel(preview_table, border_style=self.theme.border_style)
        self.console.print(preview_panel)
        
        # Show beats timeline
        beats_table = Table(title="CONTENT TIMELINE", title_style=self.theme.title_style)
        beats_table.add_column("#", style=self.theme.accent_style, width=3)
        beats_table.add_column("Offset", style=self.theme.info_style, width=12)
        beats_table.add_column("Content", style=self.theme.info_style)
        
        for i, beat in enumerate(campaign.beats, 1):
            offset_hours = (i - 1) * campaign.cadence_minutes / 60
            offset_str = f"T+{offset_hours:.1f}h"
            # Truncate long beats for display
            display_beat = beat[:60] + "..." if len(beat) > 60 else beat
            beats_table.add_row(str(i), offset_str, display_beat)
        
        beats_panel = Panel(beats_table, border_style=self.theme.border_style)
        self.console.print(beats_panel)
    
    def _review_campaigns(self, profile: ArtistProfile) -> None:
        """Review existing campaigns."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} CAMPAIGN ARCHIVES",
            style=self.theme.warning_style
        )
        
        # In a real implementation, we'd load from disk
        campaigns_table = Table(title="STORED CAMPAIGNS", title_style=self.theme.title_style)
        campaigns_table.add_column("ID", style=self.theme.accent_style, width=4)
        campaigns_table.add_column("Title", style=self.theme.info_style)
        campaigns_table.add_column("Platform", style=self.theme.info_style, width=12)
        campaigns_table.add_column("Beats", style=self.theme.info_style, width=8)
        campaigns_table.add_column("Status", style=self.theme.info_style, width=12)
        
        # Placeholder data
        campaigns_table.add_row("001", "Album Release Hype", "Twitter", "5", "DRAFT")
        campaigns_table.add_row("002", "Tour Announcement", "Instagram", "3", "SCHEDULED")
        campaigns_table.add_row("003", "Fan Engagement", "Discord", "8", "ACTIVE")
        
        campaigns_panel = Panel(campaigns_table, border_style=self.theme.border_style)
        self.console.print(campaigns_panel)
        
        self.console.print("\nCampaign management features coming soon...", style=self.theme.info_style)
    
    def _schedule_posts(self, profile: ArtistProfile) -> None:
        """Schedule posts for campaigns."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} POST SCHEDULER",
            style=self.theme.warning_style
        )
        
        # Show upcoming scheduled posts
        schedule_table = Table(title="SCHEDULED TRANSMISSIONS", title_style=self.theme.title_style)
        schedule_table.add_column("Time", style=self.theme.accent_style, width=16)
        schedule_table.add_column("Platform", style=self.theme.info_style, width=12)
        schedule_table.add_column("Content", style=self.theme.info_style)
        schedule_table.add_column("Status", style=self.theme.info_style, width=12)
        
        # Placeholder scheduled posts
        schedule_table.add_row("2024-01-15 14:00", "Twitter", "New track dropping tomorrow! 🎵", "PENDING")
        schedule_table.add_row("2024-01-16 09:00", "Instagram", "Behind the scenes studio shot", "PENDING")
        schedule_table.add_row("2024-01-16 18:00", "Twitter", "Track is live! Link in bio", "PENDING")
        
        schedule_panel = Panel(schedule_table, border_style=self.theme.border_style)
        self.console.print(schedule_panel)
        
        self.console.print("\nPost scheduling features coming soon...", style=self.theme.info_style)
    
    def _show_analytics(self, profile: ArtistProfile) -> None:
        """Show campaign analytics."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} ANALYTICS DASHBOARD",
            style=self.theme.warning_style
        )
        
        # Analytics overview
        analytics_table = Table(title="ENGAGEMENT METRICS", title_style=self.theme.title_style)
        analytics_table.add_column("Metric", style=self.theme.accent_style)
        analytics_table.add_column("Value", style=self.theme.info_style)
        analytics_table.add_column("Change", style=self.theme.info_style)
        
        analytics_table.add_row("Total Posts", "42", "+12 this week")
        analytics_table.add_row("Engagement Rate", "3.2%", "+0.8%")
        analytics_table.add_row("Followers", "1,337", "+89")
        analytics_table.add_row("Reach", "15.6K", "+2.1K")
        
        analytics_panel = Panel(analytics_table, border_style=self.theme.border_style)
        self.console.print(analytics_panel)
        
        # Platform breakdown
        platform_table = Table(title="PLATFORM BREAKDOWN", title_style=self.theme.title_style)
        platform_table.add_column("Platform", style=self.theme.accent_style)
        platform_table.add_column("Posts", style=self.theme.info_style)
        platform_table.add_column("Engagement", style=self.theme.info_style)
        platform_table.add_column("Best Time", style=self.theme.info_style)
        
        platform_table.add_row("Twitter", "28", "4.1%", "6:00 PM")
        platform_table.add_row("Instagram", "12", "2.8%", "8:00 AM")
        platform_table.add_row("Discord", "2", "1.5%", "11:00 PM")
        
        platform_panel = Panel(platform_table, border_style=self.theme.border_style)
        self.console.print(platform_panel)
        
        self.console.print("\nDetailed analytics features coming soon...", style=self.theme.info_style)
    
    def handle_quit(self) -> None:
        """Handle application exit."""
        if self.confirm_with_theme("Initiate sleep cycle?"):
            self.slow_type_reveal("ENTERING HYPERSLEEP MODE...", 0.1)
            self.console.print()
            self.console.print(
                f"{self.theme.alien_head} Pleasant dreams...",
                style=self.theme.accent_style
            )


def main() -> None:
    """Entry point for Rich TUI."""
    settings = ArtistMatrixSettings()
    app = RichTuiApp(settings)
    app.run()


if __name__ == "__main__":
    main()