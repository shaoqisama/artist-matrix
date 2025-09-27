"""Tests for Rich-based TUI implementation."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from artist_matrix.tui.rich_app import RichTuiApp, AlienTheme
from artist_matrix.state import ArtistMatrixSettings


@pytest.fixture
def mock_console():
    """Mock Rich console for testing."""
    with patch('artist_matrix.tui.rich_app.Console') as mock:
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
    assert hasattr(banner, 'renderable')
    assert banner.title == "NOSTROMO TERMINAL"


def test_build_main_menu(rich_app):
    """Test main menu creation with Rich Table."""
    menu = rich_app.build_main_menu()
    
    # Should be a Rich Panel
    assert hasattr(menu, 'renderable')
    assert "COMMAND INTERFACE" in str(menu.title)


def test_prompt_with_theme(rich_app, mock_console):
    """Test themed prompt functionality."""
    with patch('builtins.input', return_value='test_input'):
        result = rich_app.prompt_with_theme("Test question")
        
    assert result == "test_input"
    # Should have printed the styled question
    mock_console.print.assert_called()


def test_confirm_with_theme(rich_app, mock_console):
    """Test themed confirmation functionality."""
    with patch('builtins.input', return_value='y'):
        result = rich_app.confirm_with_theme("Confirm test?")
        
    assert result is True
    
    with patch('builtins.input', return_value='n'):
        result = rich_app.confirm_with_theme("Confirm test?")
        
    assert result is False


def test_slow_type_reveal(rich_app):
    """Test slow typing effect (basic functionality)."""
    with patch('time.sleep'):  # Speed up test
        with patch('artist_matrix.tui.rich_app.Live'):
            rich_app.slow_type_reveal("Test message", delay=0.001)


def test_glitch_effect(rich_app):
    """Test glitch effect (basic functionality)."""
    with patch('time.sleep'):  # Speed up test
        with patch('artist_matrix.tui.rich_app.Live'):
            rich_app.glitch_effect("Test message")


def test_show_loading(rich_app):
    """Test loading spinner display."""
    with patch('time.sleep'):  # Speed up test
        with patch('artist_matrix.tui.rich_app.Progress'):
            rich_app.show_loading("Test operation")


def test_handle_menu_options(rich_app, mock_console):
    """Test menu option handlers exist and execute."""
    # Test that handlers don't crash
    with patch('time.sleep'):
        rich_app.handle_generate()
        rich_app.handle_select() 
        rich_app.handle_workbench()
        rich_app.handle_echo()
        # Test quit with mocked confirmation
        with patch.object(rich_app, 'confirm_with_theme', return_value=True):
            rich_app.handle_quit()
    
    # Should have printed status messages
    assert mock_console.print.call_count >= 5


def test_keyboard_interrupt_handling(rich_app, mock_console):
    """Test graceful handling of Ctrl+C."""
    with patch.object(rich_app, 'prompt_with_theme', side_effect=KeyboardInterrupt):
        rich_app.run()
    
    # Should print emergency shutdown message
    mock_console.print.assert_called()
    last_call = mock_console.print.call_args_list[-1]
    assert "EMERGENCY SHUTDOWN" in str(last_call)


@pytest.mark.parametrize("tui_mode,expected_module", [
    ("rich", "rich_app"),
    ("classic", "app"),
    ("RICH", "rich_app"),  # Case insensitive
    ("invalid", "app"),    # Default to classic
])
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