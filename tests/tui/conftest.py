"""Test fixtures and mocks for Rich TUI tests."""

from __future__ import annotations

from typing import List

import pytest

from artist_matrix.creation_engine.ideation import ChatTurn


class MockTrackIdeationLLM:
    """Mock LLM service that returns deterministic responses for testing."""

    def __init__(self):
        self.call_count = 0
        self.last_persona_summary = None
        self.last_prompt = None
        self.last_transcript = None

    def chat(self, persona_summary: str, prompt: str, transcript: List[ChatTurn]) -> str:
        """Return deterministic response based on input patterns."""
        self.call_count += 1
        self.last_persona_summary = persona_summary
        self.last_prompt = prompt
        self.last_transcript = transcript

        # Pattern-based responses for testing different scenarios
        prompt_lower = prompt.lower()

        if "electronic" in prompt_lower or "synth" in prompt_lower:
            return self._electronic_response()
        elif "dark" in prompt_lower or "atmospheric" in prompt_lower:
            return self._dark_response()
        elif "error" in prompt_lower:
            # Test error handling
            raise Exception("Mock LLM error for testing")
        elif "malformed" in prompt_lower:
            return "This is not valid JSON response"
        else:
            return self._default_response()

    def _electronic_response(self) -> str:
        return """I suggest creating an electronic track with these elements:

```json
{
  "title": "Neon Pulse",
  "style": "Electronic synthwave",
  "tags": ["electronic", "synthwave", "atmospheric"],
  "lyrics": "Neon lights pulse through the digital night\\nSynthetic dreams in chrome and light",
  "notes": ["Driving bassline", "Retro synths", "Atmospheric pads"],
  "prompt": "Electronic synthwave with neon aesthetic",
  "negative_tags": ["acoustic", "organic"],
  "instrumental": false
}
```

This track captures the electronic vibe with a retro-futuristic feel."""

    def _dark_response(self) -> str:
        return """Here's a dark atmospheric composition:

```json
{
  "title": "Shadow Descent", 
  "style": "Dark ambient electronic",
  "tags": ["dark", "atmospheric", "ambient"],
  "lyrics": "In shadows deep where silence reigns\\nEchoes of forgotten pain",
  "notes": ["Deep bass drones", "Distorted textures", "Minimal percussion"],
  "prompt": "Dark atmospheric soundscape",
  "negative_tags": ["bright", "uplifting"],
  "instrumental": false
}
```

A brooding piece perfect for introspective moments."""

    def _default_response(self) -> str:
        return """Let me suggest a track for you:

```json
{
  "title": "Creative Flow",
  "style": "Experimental electronic",
  "tags": ["experimental", "creative", "flowing"],
  "lyrics": "Ideas flowing like water\\nCreativity knows no order", 
  "notes": ["Organic textures", "Evolving patterns"],
  "prompt": "Experimental creative track",
  "negative_tags": ["formulaic"],
  "instrumental": false
}
```

This captures the essence of creative expression."""


@pytest.fixture
def mock_llm():
    """Provide a mock LLM service for testing."""
    return MockTrackIdeationLLM()


@pytest.fixture
def rich_app_with_mock_llm(rich_app_with_mocks, mock_llm):
    """Rich TUI app with both console mocks and mock LLM."""
    app, mock_console = rich_app_with_mocks
    app.ideation_llm = mock_llm
    return app, mock_console, mock_llm
