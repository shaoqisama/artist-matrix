"""Application service for running the native Artist Matrix agents."""

from __future__ import annotations

from pathlib import Path

from artist_matrix.agent_runtime.definitions import (
    AgentDefinition,
    AgentRole,
    get_agent_definition,
)
from artist_matrix.agent_runtime.events import AgentTurnResult
from artist_matrix.agent_runtime.harness import (
    AgentHarness,
    EventHandler,
    HarnessTurnRequest,
    LoginChallengeHandler,
)
from artist_matrix.agent_runtime.threads import ThreadBinding, ThreadStore


class NativeAgentRuntime:
    """Bind product scopes to persistent harness threads and run specialist turns."""

    def __init__(
        self,
        *,
        harness: AgentHarness,
        thread_store: ThreadStore,
        prompts_root: Path,
        workspace: Path,
        model: str | None = None,
    ) -> None:
        self._harness = harness
        self._thread_store = thread_store
        self._prompts_root = prompts_root
        self._workspace = workspace
        self._model = model

    def run(
        self,
        role: AgentRole | str,
        prompt: str,
        *,
        scope: str = "global",
        new_thread: bool = False,
        on_event: EventHandler | None = None,
    ) -> AgentTurnResult:
        definition = get_agent_definition(role)
        normalized_scope = scope.strip() or "global"
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        with self._thread_store.scope_lock(definition.role, normalized_scope):
            if new_thread:
                self._thread_store.forget(definition.role, normalized_scope)
            binding = self._thread_store.get(definition.role, normalized_scope)
            instructions = self._developer_instructions(definition)
            result = self._harness.run_turn(
                HarnessTurnRequest(
                    definition=definition,
                    developer_instructions=instructions,
                    prompt=self._scoped_prompt(prompt, normalized_scope),
                    cwd=self._workspace,
                    thread_id=binding.thread_id if binding else None,
                    model=self._model,
                ),
                on_event=on_event,
            )
            self._thread_store.bind(definition.role, normalized_scope, result.thread_id)
        return AgentTurnResult(
            role=definition.role.value,
            thread_id=result.thread_id,
            turn_id=result.turn_id,
            response=result.response,
            status=result.status,
            started_new_thread=result.started_new_thread,
            usage=result.usage,
            error=result.error,
        )

    def forget(self, role: AgentRole | str, scope: str = "global") -> bool:
        definition = get_agent_definition(role)
        normalized_scope = scope.strip() or "global"
        with self._thread_store.scope_lock(definition.role, normalized_scope):
            return self._thread_store.forget(definition.role, normalized_scope)

    def threads(self) -> tuple[ThreadBinding, ...]:
        return self._thread_store.list()

    def healthcheck(self) -> dict[str, object]:
        return self._harness.healthcheck()

    def login(
        self,
        *,
        device_code: bool = False,
        on_challenge: LoginChallengeHandler | None = None,
    ) -> dict[str, object]:
        return self._harness.login(device_code=device_code, on_challenge=on_challenge)

    def close(self) -> None:
        self._harness.close()

    def _developer_instructions(self, definition: AgentDefinition) -> str:
        instructions = definition.load_instructions(self._prompts_root)
        allowed = ", ".join(definition.allowed_tools)
        return (
            f"{instructions.rstrip()}\n\n"
            "Runtime boundary:\n"
            "- Canonical product data belongs to Artist Matrix, not to this thread.\n"
            "- Use only the artist_matrix MCP tools listed below.\n"
            "- Tool calls may create reviewable proposals but never execute consequential actions.\n"
            "- Never edit project or data files directly. Never call provider APIs directly.\n"
            "- When a proposal is created, show its action ID and ask the user to review it.\n"
            f"Allowed tools for this role: {allowed}.\n"
        )

    def _scoped_prompt(self, prompt: str, scope: str) -> str:
        return f"Artist Matrix scope: {scope}\n\nUser request:\n{prompt.strip()}"


__all__ = ["NativeAgentRuntime"]
