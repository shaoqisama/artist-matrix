from __future__ import annotations

from pathlib import Path
from typing import Iterator

from artist_matrix.tui import TuiApp

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def load_snapshot(name: str) -> str:
    return (SNAPSHOT_DIR / name).read_text(encoding="utf-8").rstrip()


def test_main_menu_snapshot() -> None:
    app = TuiApp()
    menu = app.build_main_menu().rstrip()
    assert menu == load_snapshot("test_shell--main_menu.txt")


def test_generate_branch_outputs_sequence(monkeypatch) -> None:
    inputs: Iterator[str] = iter(["1", "q"])
    captured: list[str] = []

    def fake_input(prompt: str) -> str:
        return next(inputs)

    app = TuiApp(input_func=fake_input, output_func=captured.append)
    app.run()

    assert any("Initiating Soul Forge" in line for line in captured)
    assert captured[-1] == "Shutting down Artist Matrix shell. See you in the wasteland."


def test_select_branch_outputs_sequence(monkeypatch) -> None:
    inputs: Iterator[str] = iter(["2", "q"])
    captured: list[str] = []

    def fake_input(prompt: str) -> str:
        return next(inputs)

    app = TuiApp(input_func=fake_input, output_func=captured.append)
    app.run()

    assert any("Accessing artist archives" in line for line in captured)
    assert captured[-1] == "Shutting down Artist Matrix shell. See you in the wasteland."
