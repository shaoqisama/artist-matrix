"""Rich-based Terminal UI shell for the Artist Matrix experience with Alien: Earth theming."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn

from artist_matrix.state import ArtistMatrixSettings

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ASSET_DIR = _PROJECT_ROOT / "assets" / "tui"


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
        
        # For compatibility with existing interface
        self._input = input_fn or input
        self._output = output_fn or self.console.print
    
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
                
                if choice in {"1", "g", "generate"}:
                    self.handle_generate()
                elif choice in {"2", "s", "select"}:
                    self.handle_select()
                elif choice in {"3", "c", "create", "workbench"}:
                    self.handle_workbench()
                elif choice in {"4", "e", "echo"}:
                    self.handle_echo()
                elif choice in {"q", "quit", "exit"}:
                    self.handle_quit()
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
    
    def handle_generate(self) -> None:
        """Handle avatar generation flow."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} SOUL FORGE ACTIVATED",
            style=self.theme.warning_style
        )
        self.show_loading("Generating Avatar")
        # TODO: Implement Rich-based wizard
    
    def handle_select(self) -> None:
        """Handle avatar selection flow."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} ACCESSING ARCHIVES",
            style=self.theme.warning_style
        )
        self.show_loading("Scanning Personnel Files")
        # TODO: Implement Rich-based selection
    
    def handle_workbench(self) -> None:
        """Handle creation workbench flow."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} TRACK FORGE ONLINE",
            style=self.theme.warning_style
        )
        self.show_loading("Initializing Creation Matrix")
        # TODO: Implement Rich-based workbench
    
    def handle_echo(self) -> None:
        """Handle echo chamber flow."""
        self.console.print(
            f"{self.theme.weyland_yutani_tag} BROADCAST ARRAY ACTIVE",
            style=self.theme.warning_style
        )
        self.show_loading("Establishing Communications")
        # TODO: Implement Rich-based echo chamber
    
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