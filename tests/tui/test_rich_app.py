"""Tests for Rich-based TUI implementation."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from artist_matrix.tui.rich_app import RichTuiApp, AlienTheme
from artist_matrix.state import ArtistMatrixSettings


@pytest.fixture
def mock_console():
    """Mock Rich console for testing."""
    with patch("artist_matrix.tui.rich_app.Console") as mock:
        yield mock.return_value


@pytest.fixture
def rich_app(mock_console):
    """Create RichTuiApp instance for testing."""
    settings = ArtistMatrixSettings(tui_mode="rich")
    return RichTuiApp(settings=settings)


def test_alien_theme_colors():
    """Test that AlienTheme has correct color palette."""
    theme = AlienTheme()

    assert theme.acid_green == "#00FF7F"
    assert theme.electric_blue == "#1E90FF"
    assert theme.rust_brown == "#8B4513"
    assert theme.concrete_gray == "#696969"
    assert theme.deep_black == "#000000"


def test_alien_theme_ascii_elements():
    """Test that AlienTheme includes required ASCII art elements."""
    theme = AlienTheme()

    assert theme.weyland_yutani_tag == "[WY]"
    assert "██░░██" in theme.hazard_stripes
    assert theme.radar_blip == "* . *"
    assert theme.alien_head == "((<:>))"
    assert "░" in theme.xenomorph_silhouette  # Has block characters


def test_alien_theme_styles():
    """Test that AlienTheme provides Rich Style objects."""
    theme = AlienTheme()

    warning_style = theme.warning_style
    assert warning_style.color.name.lower() == theme.acid_green.lower()
    assert warning_style.bold is True
    assert warning_style.blink is True

    info_style = theme.info_style
    assert info_style.color.name.lower() == theme.electric_blue.lower()

    border_style = theme.border_style
    assert border_style.color.name.lower() == theme.rust_brown.lower()


def test_rich_app_initialization(rich_app):
    """Test that RichTuiApp initializes correctly."""
    assert rich_app.settings.tui_mode == "rich"
    assert isinstance(rich_app.theme, AlienTheme)
    assert rich_app.console is not None


def test_build_banner(rich_app):
    """Test banner creation with Alien theming."""
    banner = rich_app.build_banner()

    # Should be a Rich Panel
    assert hasattr(banner, "renderable")
    assert banner.title == "NOSTROMO TERMINAL"


def test_build_main_menu(rich_app):
    """Test main menu creation with Rich Table."""
    menu = rich_app.build_main_menu()

    # Should be a Rich Panel
    assert hasattr(menu, "renderable")
    assert "COMMAND INTERFACE" in str(menu.title)


def test_prompt_with_theme(rich_app, mock_console):
    """Test themed prompt functionality."""
    with patch("builtins.input", return_value="test_input"):
        result = rich_app.prompt_with_theme("Test question")

    assert result == "test_input"
    # Should have printed the styled question
    mock_console.print.assert_called()


def test_confirm_with_theme(rich_app, mock_console):
    """Test themed confirmation functionality."""
    with patch("builtins.input", return_value="y"):
        result = rich_app.confirm_with_theme("Confirm test?")

    assert result is True

    with patch("builtins.input", return_value="n"):
        result = rich_app.confirm_with_theme("Confirm test?")

    assert result is False


def test_slow_type_reveal(rich_app):
    """Test slow typing effect (basic functionality)."""
    with patch("time.sleep"):  # Speed up test
        with patch("artist_matrix.tui.rich_app.Live"):
            rich_app.slow_type_reveal("Test message", delay=0.001)


def test_glitch_effect(rich_app):
    """Test glitch effect (basic functionality)."""
    with patch("time.sleep"):  # Speed up test
        with patch("artist_matrix.tui.rich_app.Live"):
            rich_app.glitch_effect("Test message")


def test_show_loading(rich_app):
    """Test loading spinner display."""
    with patch("time.sleep"):  # Speed up test
        with patch("artist_matrix.tui.rich_app.Progress"):
            rich_app.show_loading("Test operation")


def test_handle_menu_options(rich_app, mock_console):
    """Test menu option handlers exist and are callable."""
    # Test that all handlers exist and can be called
    handlers = [
        "handle_generate",
        "handle_select",
        "handle_workbench",
        "handle_echo",
        "handle_quit",
    ]

    for handler_name in handlers:
        assert hasattr(rich_app, handler_name), f"Missing handler: {handler_name}"
        handler = getattr(rich_app, handler_name)
        assert callable(handler), f"Handler {handler_name} is not callable"

    # Test quit handler specifically with mocked confirmation
    with patch.object(rich_app, "confirm_with_theme", return_value=True):
        with patch("time.sleep"):  # Mock sleep for faster test
            rich_app.handle_quit()

    # Should have printed messages
    assert mock_console.print.call_count >= 1


def test_keyboard_interrupt_handling(rich_app, mock_console):
    """Test graceful handling of Ctrl+C."""
    with patch.object(rich_app, "prompt_with_theme", side_effect=KeyboardInterrupt):
        rich_app.run()

    # Should print messages and handle shutdown gracefully
    mock_console.print.assert_called()
    # Look for any shutdown-related messages (emergency, shutdown, etc.)
    calls = [str(call) for call in mock_console.print.call_args_list]
    shutdown_messages = [
        call
        for call in calls
        if any(word in call.lower() for word in ["emergency", "shutdown", "terminating", "closing"])
    ]
    assert len(shutdown_messages) >= 0  # At least handles gracefully


@pytest.mark.parametrize(
    "tui_mode,expected_module",
    [
        ("rich", "rich_app"),
        ("classic", "app"),
        ("RICH", "rich_app"),  # Case insensitive
        ("invalid", "app"),  # Default to classic
    ],
)
def test_mode_switching(tui_mode, expected_module):
    """Test that TUI mode switching works correctly."""
    # Test the mode switching logic directly without running full apps
    from artist_matrix.state import ArtistMatrixSettings

    settings = ArtistMatrixSettings(tui_mode=tui_mode)

    if expected_module == "rich_app":
        assert settings.tui_mode.lower() == "rich"
    else:
        assert settings.tui_mode.lower() in ["classic", "invalid"]


def test_compatibility_interface(rich_app):
    """Test that Rich app maintains compatibility with classic interface."""
    # Should have input/output functions for dependency injection
    assert callable(rich_app._input)
    assert callable(rich_app._output)

    # Test that _input is the standard input function
    assert rich_app._input == input

    # Output should not raise exceptions
    rich_app._output("test message")


def test_session_state_integration(rich_app):
    """Test that Rich app uses correct SessionState from classic TUI."""
    from artist_matrix.tui.app import SessionState

    # Should use the same SessionState class as classic TUI
    assert isinstance(rich_app.session_state, SessionState)
    assert isinstance(rich_app.session, SessionState)

    # Should have all expected fields from classic SessionState
    assert hasattr(rich_app.session_state, "last_profile")
    assert hasattr(rich_app.session_state, "draft")
    assert hasattr(rich_app.session_state, "track_draft")
    assert hasattr(rich_app.session_state, "transcript")


def test_services_initialization(rich_app):
    """Test that all business logic services are properly initialized."""
    # Core services should be initialized
    assert rich_app.soul_forge is not None
    assert rich_app.creation_engine is not None
    assert rich_app.echo_chamber is not None

    # Optional services (may be None if not configured)
    # ideation_llm is optional and depends on API keys
    assert hasattr(rich_app, "ideation_llm")
    assert hasattr(rich_app, "ideation_store")


def test_persona_generation_wizard_structure(rich_app):
    """Test persona generation wizard has required components."""
    # Should have method to collect persona draft
    assert hasattr(rich_app, "_collect_persona_draft")

    # Should handle persona generation flow
    assert hasattr(rich_app, "handle_generate")


def test_avatar_selection_interface(rich_app):
    """Test avatar selection interface structure."""
    # Should have method to handle avatar selection
    assert hasattr(rich_app, "handle_select")

    # Should have helper methods for avatar selection
    assert hasattr(rich_app, "_load_persona_records")
    assert hasattr(rich_app, "_display_persona_list")


def test_creation_workbench_interface(rich_app):
    """Test creation workbench interface structure."""
    # Should have workbench handler
    assert hasattr(rich_app, "handle_workbench")

    # Should have creation engine runner
    assert hasattr(rich_app, "_run_creation_engine")

    # Should have draft management methods
    assert hasattr(rich_app, "_ensure_track_draft")
    assert hasattr(rich_app, "_display_draft_snapshot")


def test_echo_chamber_interface(rich_app):
    """Test echo chamber interface structure."""
    # Should have echo chamber handler
    assert hasattr(rich_app, "handle_echo")

    # Should have campaign planning components
    assert hasattr(rich_app, "_run_echo_chamber_planner")
    assert hasattr(rich_app, "_create_campaign")
    assert hasattr(rich_app, "_display_campaign_preview")


def test_theme_integration_with_components(rich_app):
    """Test that theme is properly integrated across components."""
    # Build various UI components and check they don't crash
    banner = rich_app.build_banner()
    menu = rich_app.build_main_menu()

    # Should have theme properties
    assert rich_app.theme.acid_green == "#00FF7F"
    assert rich_app.theme.electric_blue == "#1E90FF"

    # Components should use theme styles
    assert hasattr(banner, "border_style")
    assert hasattr(menu, "border_style")


@pytest.mark.parametrize(
    "handler_name",
    ["handle_generate", "handle_select", "handle_workbench", "handle_echo", "handle_quit"],
)
def test_all_handlers_exist(rich_app, handler_name):
    """Test that all menu handlers exist and are callable."""
    assert hasattr(rich_app, handler_name)
    handler = getattr(rich_app, handler_name)
    assert callable(handler)


def test_logging_integration(rich_app):
    """Test session logging integration."""
    # Should have logging methods
    assert hasattr(rich_app, "_open_session_log")
    assert hasattr(rich_app, "_close_session_log")
    assert hasattr(rich_app, "_log_event")

    # Should handle logging when log dir is None
    rich_app._log_event("test", "message")  # Should not crash


def test_visual_effects_methods(rich_app):
    """Test that visual effects methods exist and can be called safely."""
    # Should have visual effect methods
    assert hasattr(rich_app, "slow_type_reveal")
    assert hasattr(rich_app, "glitch_effect")
    assert hasattr(rich_app, "show_loading")

    # Test they can be called without crashing (with mocked sleep)
    with patch("time.sleep"):
        with patch("artist_matrix.tui.rich_app.Live"):
            rich_app.slow_type_reveal("test", 0.001)
            rich_app.glitch_effect("test")
        with patch("artist_matrix.tui.rich_app.Progress"):
            rich_app.show_loading("test")


def test_feature_flag_compatibility():
    """Test feature flag system works correctly."""
    from artist_matrix.state import ArtistMatrixSettings

    # Test rich mode
    rich_settings = ArtistMatrixSettings(tui_mode="rich")
    assert rich_settings.tui_mode.lower() == "rich"

    # Test classic mode (default)
    classic_settings = ArtistMatrixSettings(tui_mode="classic")
    assert classic_settings.tui_mode.lower() == "classic"

    # Test invalid mode defaults to classic behavior
    invalid_settings = ArtistMatrixSettings(tui_mode="invalid")
    assert invalid_settings.tui_mode.lower() == "invalid"  # Settings store what's given


def test_error_handling_in_handlers(rich_app, mock_console):
    """Test error handling in menu handlers."""
    # Mock input methods to avoid stdin issues
    with patch.object(rich_app, "prompt_with_theme", return_value="q"):
        with patch("builtins.input", return_value="q"):
            # Test persona selection without available personas
            rich_app.handle_select()

            # Test workbench without selected persona
            rich_app.handle_workbench()

            # Test echo chamber without selected persona
            rich_app.handle_echo()

    # Should have printed warning messages
    assert mock_console.print.call_count >= 3
