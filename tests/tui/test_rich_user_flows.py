"""End-to-end user flow tests for Rich TUI."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile

from artist_matrix.tui.rich_app import RichTuiApp
from artist_matrix.state import ArtistMatrixSettings
from artist_matrix.soul_forge import ArtistProfile


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def rich_app_with_mocks(temp_data_dir):
    """Create RichTuiApp with mocked external dependencies."""
    settings = ArtistMatrixSettings(
        tui_mode="rich", data_root=temp_data_dir, tui_log_dir=temp_data_dir / "logs"
    )

    with patch("artist_matrix.tui.rich_app.Console") as mock_console_class:
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        # Import mock LLM from conftest
        from conftest import MockTrackIdeationLLM

        mock_llm = MockTrackIdeationLLM()

        # Mock external services to avoid API calls
        with patch("artist_matrix.soul_forge.service.SoulForgeService"):
            with patch("artist_matrix.creation_engine.service.CreationEngineService"):
                with patch(
                    "artist_matrix.creation_engine.llm.TrackIdeationLLM.build",
                    return_value=mock_llm,
                ):
                    app = RichTuiApp(settings)
                    app.console = mock_console
                    yield app, mock_console


def test_complete_persona_creation_flow(rich_app_with_mocks):
    """Test complete persona creation from start to finish."""
    app, mock_console = rich_app_with_mocks

    # Mock user inputs for persona creation
    inputs = [
        "Test Artist",  # name
        "Electronic",  # genre
        "Dark",  # mood
        "Kraftwerk",  # influences
        "atmospheric",  # descriptors
        "Dark electronic music",  # brief
        "Neon colors",  # visual_palette
        "Futuristic",  # narrative_tone
        "Clean",  # safety_notes
        "f",  # forge (confirm submission)
        "q",  # quit after creation
    ]

    # Mock the persona generation result
    mock_profile = ArtistProfile(
        name="Test Artist", lyric_style="Electronic", visual_style="Dark and atmospheric"
    )

    with patch("builtins.input", side_effect=inputs):
        with patch.object(app, "soul_forge") as mock_soul_forge:
            mock_soul_forge.generate.return_value = {
                "profile": mock_profile,
                "manifest_path": "/tmp/test-manifest.json",
                "avatar": None,
            }

            # Test persona creation flow
            app.handle_generate()

            # Verify soul forge was called
            mock_soul_forge.generate.assert_called_once()

            # Verify persona was stored in session
            assert app.session_state.last_profile == mock_profile


def test_avatar_selection_flow(rich_app_with_mocks):
    """Test avatar selection with existing personas."""
    app, mock_console = rich_app_with_mocks

    # Create mock persona files
    personas_dir = app.settings.data_root / "artists"
    personas_dir.mkdir(parents=True, exist_ok=True)

    # Create a mock persona file
    test_persona_file = personas_dir / "test-artist.json"
    test_persona_data = {
        "name": "Test Artist",
        "slug": "test-artist",
        "persona": "Electronic artist",
        "metadata": {"genre": "Electronic"},
    }

    with patch(
        "builtins.input", side_effect=["1", "y", "q"]
    ):  # Select first persona, confirm load, then quit
        with patch.object(app, "_load_persona_records") as mock_load:
            mock_record = MagicMock()
            mock_record.path = test_persona_file
            mock_record.manifest = test_persona_data
            mock_load.return_value = [mock_record]

            with patch("json.loads", return_value=test_persona_data):
                app.handle_select()

                # Verify persona was loaded
                mock_load.assert_called_once()


def test_creation_workbench_flow_without_persona(rich_app_with_mocks):
    """Test creation workbench shows error when no persona selected."""
    app, mock_console = rich_app_with_mocks

    # Ensure no persona is selected
    app.session_state.last_profile = None

    app.handle_workbench()

    # Should print a Panel with error message about no persona
    mock_console.print.assert_called()
    # Check that a Panel was printed (Rich objects)
    called_with_panel = any("Panel" in str(call) for call in mock_console.print.call_args_list)
    assert called_with_panel, "Expected Panel to be printed for no persona error"


def test_creation_workbench_flow_with_persona(rich_app_with_mocks):
    """Test creation workbench with selected persona."""
    app, mock_console = rich_app_with_mocks

    # Set up a mock persona
    mock_profile = ArtistProfile(
        name="Test Artist", lyric_style="Electronic", visual_style="Dark and atmospheric"
    )
    app.session_state.last_profile = mock_profile

    # Mock chat inputs - help command then exit workbench
    inputs = ["/help", "/back"]

    with patch("builtins.input", side_effect=inputs):
        with patch.object(app, "_ensure_track_draft") as mock_ensure_draft:
            mock_draft = MagicMock()
            mock_ensure_draft.return_value = mock_draft

            # Should not crash and should show help
            app.handle_workbench()

            # Verify draft was initialized
            mock_ensure_draft.assert_called_once()


def test_echo_chamber_flow_without_persona(rich_app_with_mocks):
    """Test echo chamber shows error when no persona selected."""
    app, mock_console = rich_app_with_mocks

    # Ensure no persona is selected
    app.session_state.last_profile = None

    app.handle_echo()

    # Should print warning message about no persona
    mock_console.print.assert_called()
    # Check that a message with WY tag was printed
    calls = [str(call) for call in mock_console.print.call_args_list]
    wy_messages = [call for call in calls if "[WY]" in call or "persona" in call.lower()]
    assert len(wy_messages) > 0, f"Expected WY tag or persona message, got: {calls}"


def test_echo_chamber_campaign_creation_flow(rich_app_with_mocks):
    """Test echo chamber campaign creation flow."""
    app, mock_console = rich_app_with_mocks

    # Set up a mock persona
    mock_profile = ArtistProfile(
        name="Test Artist", lyric_style="Electronic", visual_style="Dark and atmospheric"
    )
    app.session_state.last_profile = mock_profile

    # Mock inputs for campaign creation
    inputs = [
        "1",  # Create new campaign
        "Album Launch",  # Campaign title
        "twitter",  # Platform
        "Dropping new track!",  # Beat 1
        "Check out the video",  # Beat 2
        "",  # Empty line to finish beats
        "60",  # Cadence in minutes
        "y",  # Save campaign
        "q",  # Quit
    ]

    with patch("builtins.input", side_effect=inputs):
        with patch.object(app, "prompt_with_theme", side_effect=inputs):
            with patch.object(app, "confirm_with_theme", return_value=True):
                app.handle_echo()

                # Should have printed campaign creation messages
                mock_console.print.assert_called()


def test_session_logging_integration(rich_app_with_mocks):
    """Test that session logging works correctly."""
    app, mock_console = rich_app_with_mocks

    # Enable session logging
    app._open_session_log()

    # Log an event
    app._log_event("test", "Test message")

    # Close logging
    app._close_session_log()

    # Should have created a log file
    log_files = list((app.settings.data_root / "logs").glob("*.jsonl"))
    assert len(log_files) > 0


def test_visual_effects_dont_crash(rich_app_with_mocks):
    """Test that visual effects can be called without crashing."""
    app, mock_console = rich_app_with_mocks

    with patch("time.sleep"):  # Speed up tests
        with patch("artist_matrix.tui.rich_app.Live"):
            app.slow_type_reveal("Test message", 0.001)
            app.glitch_effect("Test message")

        with patch("artist_matrix.tui.rich_app.Progress"):
            app.show_loading("Test operation")


def test_keyboard_interrupt_handling(rich_app_with_mocks):
    """Test graceful handling of keyboard interrupts."""
    app, mock_console = rich_app_with_mocks

    with patch.object(app, "prompt_with_theme", side_effect=KeyboardInterrupt):
        # Should handle KeyboardInterrupt gracefully
        app.run()

        # Should have printed some messages
        mock_console.print.assert_called()


def test_theme_components_render_correctly(rich_app_with_mocks):
    """Test that all theme components render without errors."""
    app, mock_console = rich_app_with_mocks

    # Test banner rendering
    banner = app.build_banner()
    assert banner is not None

    # Test menu rendering
    menu = app.build_main_menu()
    assert menu is not None

    # Test themed prompts don't crash
    with patch("builtins.input", return_value="test"):
        result = app.prompt_with_theme("Test prompt")
        assert result == "test"

    # Test themed confirmations
    with patch("builtins.input", return_value="y"):
        result = app.confirm_with_theme("Test confirmation")
        assert result is True


@pytest.mark.parametrize(
    "handler_name",
    ["handle_generate", "handle_select", "handle_workbench", "handle_echo", "handle_quit"],
)
def test_all_handlers_handle_quit_gracefully(rich_app_with_mocks, handler_name):
    """Test that all handlers handle 'q' input gracefully."""
    app, mock_console = rich_app_with_mocks

    # Set up a persona for handlers that need it
    if handler_name in ["handle_workbench", "handle_echo"]:
        mock_profile = ArtistProfile(
            name="Test Artist", lyric_style="Electronic", visual_style="Dark and atmospheric"
        )
        app.session_state.last_profile = mock_profile

    # Mock inputs to immediately quit (handle_generate needs special treatment)
    if handler_name == "handle_generate":
        # handle_generate needs full persona creation inputs then quit
        inputs = [
            "Test Artist",  # name
            "Electronic",  # genre
            "Dark",  # mood
            "Kraftwerk",  # influences
            "atmospheric",  # descriptors
            "Dark electronic music",  # brief
            "Neon colors",  # visual_palette
            "Futuristic",  # narrative_tone
            "Clean",  # safety_notes
            "c",  # cancel instead of forge to quit gracefully
        ]

        with patch("builtins.input", side_effect=inputs):
            with patch.object(app, "prompt_with_theme", side_effect=inputs):
                with patch.object(app, "confirm_with_theme", return_value=True):
                    with patch("time.sleep"):  # Speed up visual effects
                        handler = getattr(app, handler_name)
                        # Should not crash
                        handler()
    elif handler_name == "handle_workbench":
        # handle_workbench needs "/back" to quit
        with patch("builtins.input", return_value="/back"):
            with patch.object(app, "prompt_with_theme", return_value="/back"):
                with patch.object(app, "confirm_with_theme", return_value=True):
                    with patch("time.sleep"):  # Speed up visual effects
                        handler = getattr(app, handler_name)
                        # Should not crash
                        handler()
    else:
        # Other handlers can quit immediately
        with patch("builtins.input", return_value="q"):
            with patch.object(app, "prompt_with_theme", return_value="q"):
                with patch.object(app, "confirm_with_theme", return_value=True):
                    with patch("time.sleep"):  # Speed up visual effects
                        handler = getattr(app, handler_name)
                        # Should not crash
                        handler()


def test_error_recovery_in_flows(rich_app_with_mocks):
    """Test error recovery in user flows."""
    app, mock_console = rich_app_with_mocks

    # Test that invalid menu selections are handled
    with patch("builtins.input", side_effect=["invalid", "q"]):
        with patch.object(app, "prompt_with_theme", side_effect=["invalid", "q"]):
            app.handle_echo()

            # Should have printed error message about invalid selection
            mock_console.print.assert_called()


def test_full_user_journey_simulation(rich_app_with_mocks):
    """Simulate a complete user journey through all features."""
    app, mock_console = rich_app_with_mocks

    # Step 1: Create a persona
    persona_inputs = [
        "AI Artist",  # name
        "Synthwave",  # genre
        "Nostalgic",  # mood
        "Daft Punk",  # influences
        "atmospheric",  # descriptors
        "Retro-futuristic electronic music",  # brief
        "Neon purple",  # visual_palette
        "Retro-futuristic",  # narrative_tone
        "Family-friendly",  # safety_notes
        "f",  # forge (confirm)
        "q",  # quit
    ]

    mock_profile = ArtistProfile(
        name="AI Artist", lyric_style="Synthwave", visual_style="Nostalgic and retro-futuristic"
    )

    with patch("builtins.input", side_effect=persona_inputs):
        with patch.object(
            app.soul_forge,
            "generate",
            return_value={
                "profile": mock_profile,
                "manifest_path": "/tmp/test-manifest.json",
                "avatar": None,
            },
        ):
            app.handle_generate()

    # Step 2: Verify persona was created and selected
    assert app.session_state.last_profile == mock_profile

    # Step 3: Test workbench with the created persona
    workbench_inputs = ["/help", "/back"]
    with patch("builtins.input", side_effect=workbench_inputs):
        with patch.object(app, "_ensure_track_draft"):
            app.handle_workbench()

    # Step 4: Test echo chamber with the persona
    echo_inputs = ["4", "q"]  # Analytics then quit
    with patch("builtins.input", side_effect=echo_inputs):
        with patch.object(app, "prompt_with_theme", side_effect=echo_inputs):
            app.handle_echo()

    # Journey completed successfully
    assert True  # If we got here without exceptions, the journey worked


def test_workbench_llm_interaction(rich_app_with_mocks):
    """Test that workbench can handle LLM interactions with mock."""
    app, mock_console = rich_app_with_mocks

    # Set up a mock persona
    mock_profile = ArtistProfile(
        name="Test Artist", lyric_style="Electronic", visual_style="Dark and atmospheric"
    )
    app.session_state.last_profile = mock_profile

    # Verify mock LLM is available
    assert app.ideation_llm is not None

    # Test that draft creation works
    draft = app._ensure_track_draft(mock_profile)
    assert draft is not None
    assert draft.persona_slug == mock_profile.slug

    # Test that LLM can be called (would be used in actual workbench interaction)
    from artist_matrix.creation_engine.llm import apply_llm_guidance

    response_text, fields_dict, json_text = apply_llm_guidance(
        app.ideation_llm,
        f"Artist: {mock_profile.name}, Style: {mock_profile.lyric_style}",
        "create an electronic track",
        [],
        draft,
    )

    # Should get response from mock
    assert response_text is not None
    assert "electronic" in response_text.lower()
    assert isinstance(fields_dict, dict)
    assert len(fields_dict) > 0
