"""Interfaces between Artist Matrix and an agent harness implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from artist_matrix.agent_runtime.definitions import AgentDefinition
from artist_matrix.agent_runtime.events import RuntimeEvent


EventHandler = Callable[[RuntimeEvent], None]
LoginChallengeHandler = Callable[[str, str | None], None]


@dataclass(frozen=True)
class HarnessTurnRequest:
    """Provider-neutral input for a persistent agent turn."""

    definition: AgentDefinition
    developer_instructions: str
    prompt: str
    cwd: Path
    thread_id: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class HarnessTurnResult:
    """Provider-neutral completion returned by a harness backend."""

    thread_id: str
    turn_id: str
    response: str | None
    status: str
    started_new_thread: bool
    usage: dict[str, object] | None = None
    error: str | None = None


class AgentHarness(Protocol):
    """Runtime contract implemented by Codex and test fakes."""

    def run_turn(
        self,
        request: HarnessTurnRequest,
        *,
        on_event: EventHandler | None = None,
    ) -> HarnessTurnResult: ...

    def healthcheck(self) -> dict[str, object]: ...

    def login(
        self,
        *,
        device_code: bool = False,
        on_challenge: LoginChallengeHandler | None = None,
    ) -> dict[str, object]: ...

    def close(self) -> None: ...


class HarnessUnavailableError(RuntimeError):
    """Raised when the configured harness cannot start or authenticate."""


__all__ = [
    "AgentHarness",
    "EventHandler",
    "HarnessTurnRequest",
    "HarnessTurnResult",
    "HarnessUnavailableError",
    "LoginChallengeHandler",
]
