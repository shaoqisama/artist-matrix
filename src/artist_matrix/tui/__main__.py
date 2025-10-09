"""Module entry point for launching the Artist Matrix TUI."""

from __future__ import annotations

from artist_matrix.state import ArtistMatrixSettings


def main() -> None:
    """Main entry point with mode switching support."""
    settings = ArtistMatrixSettings()
    
    if settings.tui_mode.lower() == "rich":
        from .rich_app import main as rich_main
        rich_main()
    else:
        from .app import main as classic_main
        classic_main()


if __name__ == "__main__":
    main()
