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


def test_select_branch_without_persona(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(tmp_path))

    inputs: Iterator[str] = iter(["q"])
    captured: list[str] = []

    app = TuiApp(input_func=lambda _: next(inputs), output_func=captured.append)
    app.handle_select()

    assert any("No personas available" in line for line in captured)
