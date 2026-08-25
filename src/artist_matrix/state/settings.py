"""Configuration settings for Artist Matrix agents."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _working_path(name: str) -> Path:
    """Resolve mutable defaults from the process working directory at startup."""

    return Path.cwd() / name


class ArtistMatrixSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARTIST_MATRIX_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    data_root: Path = Field(default_factory=lambda: _working_path("data"))
    cache_root: Path = Field(default_factory=lambda: _working_path(".cache"))
    log_level: str = Field(default="INFO")
    agent_runtime: str = Field(default="codex")
    codex_model: str | None = Field(default=None)
    codex_bin: str | None = Field(default=None)
    codex_home: Path | None = Field(default=None)
    codex_workspace: Path | None = Field(default=None)
    codex_thread_store: Path | None = Field(default=None)
    action_root: Path | None = Field(default=None)
    persona_provider: str = Field(default="stub")
    persona_model: str = Field(default="persona-stub")
    persona_api_key: str | None = Field(default=None)
    persona_endpoint: str | None = Field(default="https://api.deepseek.com/v1/chat/completions")
    persona_log_dir: Path | None = Field(default=None)
    avatar_provider: str = Field(default="stub")
    avatar_model: str = Field(default="sdxl-stub")
    avatar_api_key: str | None = Field(default=None)
    prompts_root: Path = Field(default=_PACKAGE_ROOT / "prompts")
    agent_prompts_root: Path | None = Field(default=None)
    creation_audio_provider: str = Field(default="stub")
    creation_audio_model: str = Field(default="V3_5")
    creation_audio_api_key: str | None = Field(default=None)
    creation_audio_base_url: str | None = Field(default="https://api.sunoapi.org")
    creation_audio_callback_url: str | None = Field(default=None)
    creation_audio_poll_interval: float = Field(default=5.0)
    creation_audio_timeout_seconds: float = Field(default=300.0)
    creation_audio_log_dir: Path | None = Field(default=None)
    tui_log_dir: Path | None = Field(default_factory=lambda: _working_path("logs") / "tui")
    tui_mode: str = Field(default="classic")

    @property
    def resolved_codex_home(self) -> Path:
        """Return the application-owned Codex home isolated from user configuration."""

        return self.codex_home or self.cache_root / "codex-home"

    @property
    def resolved_codex_workspace(self) -> Path:
        """Return a data-free workspace for native product-agent threads."""

        return self.codex_workspace or self.resolved_codex_home / "workspace"

    @property
    def resolved_agent_prompts_root(self) -> Path:
        """Return package-owned native prompts that survive wheel installation."""

        return self.agent_prompts_root or _PACKAGE_ROOT / "prompts"

    @property
    def resolved_thread_store(self) -> Path:
        return self.codex_thread_store or self.resolved_codex_home / "agent_threads.json"

    @property
    def resolved_action_root(self) -> Path:
        return self.action_root or self.data_root / "actions"


__all__ = ["ArtistMatrixSettings"]
