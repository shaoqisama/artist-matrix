"""Configuration settings for Artist Matrix agents."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ArtistMatrixSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARTIST_MATRIX_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    data_root: Path = Field(default=_PROJECT_ROOT / "data")
    cache_root: Path = Field(default=_PROJECT_ROOT / ".cache")
    log_level: str = Field(default="INFO")
    persona_provider: str = Field(default="stub")
    persona_model: str = Field(default="persona-stub")
    persona_api_key: str | None = Field(default=None)
    persona_endpoint: str | None = Field(default="https://api.deepseek.com/v1/chat/completions")
    persona_log_dir: Path | None = Field(default=None)
    avatar_provider: str = Field(default="stub")
    avatar_model: str = Field(default="sdxl-stub")
    avatar_api_key: str | None = Field(default=None)
    prompts_root: Path = Field(default=_PROJECT_ROOT / "prompts")
    creation_audio_provider: str = Field(default="stub")
    creation_audio_model: str = Field(default="V3_5")
    creation_audio_api_key: str | None = Field(default=None)
    creation_audio_base_url: str | None = Field(default="https://api.sunoapi.org")
    creation_audio_callback_url: str | None = Field(default=None)
    creation_audio_poll_interval: float = Field(default=5.0)
    creation_audio_timeout_seconds: float = Field(default=300.0)
    creation_audio_log_dir: Path | None = Field(default=None)
    tui_log_dir: Path | None = Field(default=None)


__all__ = ["ArtistMatrixSettings"]
