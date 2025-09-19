"""Terminal UI shell for the Artist Matrix experience."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ASSET_DIR = _PROJECT_ROOT / "assets" / "tui"


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


class TuiApp:
    """Interactive shell coordinating avatar selection and creation."""

    def __init__(
        self,
        *,
        input_func: Callable[[str], str] | None = None,
        output_func: Callable[[str], None] | None = None,
        assets: TuiAssets | None = None,
    ) -> None:
        self._input = input_func or input
        self._output = output_func or print
        self.assets = assets or TuiAssets()

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
        self.output(
            "\n>> Initiating Soul Forge pipeline...\n"
            "   - Collecting persona traits\n"
            "   - Routing prompts to LLM/SDXL nodes\n"
            "   - Preparing manifest for archival\n"
        )

    def handle_select(self) -> None:
        self.output(
            "\n>> Accessing artist archives...\n"
            "   - Loading stored profiles\n"
            "   - Ready to deploy chosen persona\n"
        )

    def output(self, message: str) -> None:
        self._output(message)


def main() -> None:
    """Entry point for python -m artist_matrix.tui."""

    TuiApp().run()


__all__ = ["TuiApp", "main", "TuiAssets"]
