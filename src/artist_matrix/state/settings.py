"""Configuration settings for Artist Matrix agents."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ArtistMatrixSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARTIST_MATRIX_")

    data_root: Path = Field(default=_PROJECT_ROOT / "data")
    cache_root: Path = Field(default=_PROJECT_ROOT / ".cache")
    log_level: str = Field(default="INFO")


__all__ = ["ArtistMatrixSettings"]
