"""Creation Engine agent for composing lyrics, audio, and artwork."""

from .connectors import (
    HeuristicLyricGenerator,
    StubAudioGenerator,
    SunoAudioGenerator,
    build_audio_generator,
    build_lyric_generator,
)
from .ideation import ChatTurn, TrackIdeationDraft, TrackIdeationStore
from .llm import TrackIdeationLLM, apply_llm_guidance
from .service import CreationBrief, CreationEngineService, TrackManifestRepository

__all__ = [
    "CreationBrief",
    "CreationEngineService",
    "TrackManifestRepository",
    "HeuristicLyricGenerator",
    "StubAudioGenerator",
    "SunoAudioGenerator",
    "build_audio_generator",
    "build_lyric_generator",
    "ChatTurn",
    "TrackIdeationDraft",
    "TrackIdeationStore",
    "TrackIdeationLLM",
    "apply_llm_guidance",
]
