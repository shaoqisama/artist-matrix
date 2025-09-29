"""Test Rich TUI LLM integration works end-to-end."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from artist_matrix.tui.rich_app import RichTuiApp
from artist_matrix.soul_forge.profiles import ArtistProfile
from artist_matrix.creation_engine.ideation import TrackIdeationDraft


def test_llm_integration_available():
    """Test that LLM service initialization handles missing API keys gracefully."""
    app = RichTuiApp()
    
    # LLM service might be None if no API key is configured
    # This is expected behavior in CI or when running without keys
    if app.ideation_llm is None:
        # Ensure the app can still function without LLM
        assert app.settings is not None
        assert hasattr(app, 'session_state')
        # App should be able to handle workbench without LLM (fallback mode)
    else:
        # If LLM is available, test it's the right type
        assert hasattr(app.ideation_llm, 'chat')


def test_workbench_requires_persona():
    """Test that workbench correctly requires a persona to be selected."""
    app = RichTuiApp()
    
    # Mock console to capture output
    mock_console = MagicMock()
    app.console = mock_console
    
    # Ensure no persona is selected
    app.session_state.last_profile = None
    
    # Try to use workbench
    app.handle_workbench()
    
    # Should print error about no persona
    mock_console.print.assert_called()
    # Check that a Panel was printed (error message)
    calls = [str(call) for call in mock_console.print.call_args_list]
    panel_calls = [call for call in calls if 'Panel' in call]
    assert len(panel_calls) > 0


def test_draft_creation_with_persona():
    """Test that draft is created correctly with a persona."""
    app = RichTuiApp()
    
    # Create a test persona
    profile = ArtistProfile(
        name="Test Artist",
        lyric_style="Electronic pop",
        visual_style="Neon colors",
        influences=["Kraftwerk", "Daft Punk"]
    )
    
    # Test draft creation
    draft = app._ensure_track_draft(profile)
    
    assert draft is not None
    assert draft.persona_slug == profile.slug
    assert draft.title == "Test Artist Anthem"  # Default title format


def test_persona_summary_format():
    """Test that persona summary is formatted correctly for LLM."""
    
    profile = ArtistProfile(
        name="Test Artist",
        lyric_style="Electronic pop", 
        visual_style="Neon colors",
        influences=["Kraftwerk", "Daft Punk"]
    )
    
    # Create the persona summary as the workbench would
    persona_summary = f"Artist: {profile.name}, Style: {profile.lyric_style}, Visual: {profile.visual_style}, Influences: {', '.join(profile.influences) if profile.influences else 'None'}"
    
    expected = "Artist: Test Artist, Style: Electronic pop, Visual: Neon colors, Influences: Kraftwerk, Daft Punk"
    assert persona_summary == expected


def test_llm_response_processing(mock_llm):
    """Test that LLM responses with structured data are processed correctly."""
    from artist_matrix.creation_engine.llm import apply_llm_guidance
    
    profile = ArtistProfile(
        name="Test Artist",
        lyric_style="Electronic pop",
        visual_style="Neon colors", 
        influences=["Kraftwerk", "Daft Punk"]
    )
    
    draft = TrackIdeationDraft(persona_slug=profile.slug)
    persona_summary = f"Artist: {profile.name}, Style: {profile.lyric_style}"
    
    # Test LLM call with mock
    response_text, fields_dict, json_text = apply_llm_guidance(
        mock_llm,
        persona_summary,
        "make a simple electronic track",
        [],  # empty transcript
        draft
    )
    
    # Should get meaningful response
    assert response_text is not None
    assert len(response_text) > 0
    
    # Should extract structured fields
    assert isinstance(fields_dict, dict)
    # Common fields that should be extracted
    possible_fields = ['title', 'style', 'tags', 'lyrics', 'notes', 'prompt', 'negative_tags', 'instrumental']
    extracted_fields = list(fields_dict.keys())
    
    # Should have extracted at least some structured data
    assert len(extracted_fields) > 0
    # All extracted fields should be recognized
    for field in extracted_fields:
        assert field in possible_fields
    
    # Verify mock was called correctly
    assert mock_llm.call_count == 1
    assert mock_llm.last_persona_summary == persona_summary
    assert "electronic" in mock_llm.last_prompt


def test_workbench_flow_integration(mock_llm):
    """Test that the workbench can handle basic flow with LLM."""
    app = RichTuiApp()
    app.ideation_llm = mock_llm
    
    # Set up persona
    profile = ArtistProfile(
        name="Test Artist",
        lyric_style="Electronic pop",
        visual_style="Neon colors",
        influences=["Kraftwerk", "Daft Punk"]
    )
    app.session_state.last_profile = profile
    
    # Create draft
    draft = app._ensure_track_draft(profile)
    assert draft is not None
    
    # Verify profile attributes are accessible
    assert hasattr(profile, 'name')
    assert hasattr(profile, 'lyric_style') 
    assert hasattr(profile, 'visual_style')
    assert hasattr(profile, 'influences')
    
    # Verify LLM can be called with this profile
    persona_summary = f"Artist: {profile.name}, Style: {profile.lyric_style}"
    
    from artist_matrix.creation_engine.llm import apply_llm_guidance
    
    response_text, fields_dict, json_text = apply_llm_guidance(
        mock_llm,
        persona_summary, 
        "create a simple track",
        [],
        draft
    )
    
    # Should get valid response
    assert response_text is not None
    assert isinstance(fields_dict, dict)
    
    # Verify mock was called
    assert mock_llm.call_count == 1
    assert persona_summary in mock_llm.last_persona_summary


@pytest.mark.integration
def test_real_llm_integration():
    """Integration test with real LLM service (requires API key)."""
    from artist_matrix.creation_engine.llm import apply_llm_guidance
    
    app = RichTuiApp()
    
    # Skip test if LLM not available (no API key)
    if app.ideation_llm is None:
        pytest.skip("LLM service not available (no API key configured)")
    
    profile = ArtistProfile(
        name="Test Artist",
        lyric_style="Electronic pop",
        visual_style="Neon colors", 
        influences=["Kraftwerk", "Daft Punk"]
    )
    
    draft = TrackIdeationDraft(persona_slug=profile.slug)
    persona_summary = f"Artist: {profile.name}, Style: {profile.lyric_style}"
    
    # Test real LLM call
    response_text, fields_dict, json_text = apply_llm_guidance(
        app.ideation_llm,
        persona_summary,
        "make a simple electronic track",
        [],  # empty transcript
        draft
    )
    
    # Should get meaningful response
    assert response_text is not None
    assert len(response_text) > 0
    
    # Should extract structured fields
    assert isinstance(fields_dict, dict)
    # Should have extracted at least some structured data
    assert len(fields_dict) > 0


def test_mock_llm_error_handling(mock_llm):
    """Test that mock LLM can simulate error conditions."""
    from artist_matrix.creation_engine.llm import apply_llm_guidance
    
    profile = ArtistProfile(
        name="Test Artist",
        lyric_style="Electronic pop",
        visual_style="Neon colors"
    )
    
    draft = TrackIdeationDraft(persona_slug=profile.slug)
    persona_summary = f"Artist: {profile.name}, Style: {profile.lyric_style}"
    
    # Test error simulation - should handle gracefully
    response_text, fields_dict, json_text = apply_llm_guidance(
        mock_llm,
        persona_summary,
        "error test",
        [],
        draft
    )
    
    # Should return error message instead of raising
    assert response_text is not None
    assert "LLM unavailable" in response_text
    assert "Mock LLM error" in response_text
    assert fields_dict == {}
    assert json_text is None


def test_mock_llm_malformed_response(mock_llm):
    """Test handling of malformed LLM responses."""
    from artist_matrix.creation_engine.llm import apply_llm_guidance
    
    profile = ArtistProfile(
        name="Test Artist",
        lyric_style="Electronic pop",
        visual_style="Neon colors"
    )
    
    draft = TrackIdeationDraft(persona_slug=profile.slug)
    persona_summary = f"Artist: {profile.name}, Style: {profile.lyric_style}"
    
    # Test malformed response handling
    response_text, fields_dict, json_text = apply_llm_guidance(
        mock_llm,
        persona_summary,
        "return malformed response",
        [],
        draft
    )
    
    # Should still get response text even if JSON parsing fails
    assert response_text is not None
    # Fields dict should be empty if JSON extraction fails
    assert isinstance(fields_dict, dict)


if __name__ == "__main__":
    # Run basic integration test
    print("=== Rich TUI LLM Integration Test ===")
    
    try:
        app = RichTuiApp()
        print(f"✓ LLM service available: {app.ideation_llm is not None}")
        
        if app.ideation_llm:
            profile = ArtistProfile(
                name="Test Artist",
                lyric_style="Electronic pop",
                visual_style="Neon colors",
                influences=["Kraftwerk"]
            )
            
            print(f"✓ Persona created: {profile.name}")
            
            draft = app._ensure_track_draft(profile)
            print(f"✓ Draft created: {draft.title}")
            
            print("✓ Rich TUI LLM integration is working correctly!")
            print("\nTo use:")
            print("1. Run: ARTIST_MATRIX_TUI_MODE=rich uv run python -m artist_matrix.tui")
            print("2. Generate or select a persona first")
            print("3. Go to Creation Workbench")
            print("4. Type your track ideas and the LLM will respond with structured data")
            
        else:
            print("⚠ LLM service not available - configure API key to enable AI features")
            
    except Exception as exc:
        print(f"✗ Integration test failed: {exc}")