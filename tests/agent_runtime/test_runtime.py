from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from artist_matrix.agent_runtime.definitions import AgentRole, get_agent_definition
from artist_matrix.agent_runtime.events import RuntimeEvent, RuntimeEventType
from artist_matrix.agent_runtime.harness import (
    EventHandler,
    HarnessTurnRequest,
    HarnessTurnResult,
)
from artist_matrix.agent_runtime.service import NativeAgentRuntime
from artist_matrix.agent_runtime.threads import ThreadStore


class FakeAgentHarness:
    def __init__(self, results: Iterable[HarnessTurnResult]) -> None:
        self.results = list(results)
        self.requests: list[HarnessTurnRequest] = []
        self.handlers: list[EventHandler | None] = []
        self.closed = False

    def run_turn(
        self,
        request: HarnessTurnRequest,
        *,
        on_event: EventHandler | None = None,
    ) -> HarnessTurnResult:
        self.requests.append(request)
        self.handlers.append(on_event)
        if on_event is not None:
            on_event(
                RuntimeEvent(
                    type=RuntimeEventType.turn_started,
                    thread_id=request.thread_id,
                    data={"fake": True},
                )
            )
        if not self.results:
            raise AssertionError("Fake harness has no result for this turn")
        return self.results.pop(0)

    def healthcheck(self) -> dict[str, object]:
        return {"ok": True, "provider": "fake"}

    def login(self, *, device_code=False, on_challenge=None):  # noqa: ANN001, ANN201
        if on_challenge is not None:
            on_challenge("https://example.test/login", "CODE" if device_code else None)
        return {"success": True}

    def close(self) -> None:
        self.closed = True


def _result(
    thread_id: str,
    turn_id: str,
    *,
    started_new_thread: bool,
) -> HarnessTurnResult:
    return HarnessTurnResult(
        thread_id=thread_id,
        turn_id=turn_id,
        response=f"response for {turn_id}",
        status="completed",
        started_new_thread=started_new_thread,
        usage={"input_tokens": 10},
    )


def _runtime(
    tmp_path: Path,
    harness: FakeAgentHarness,
    *,
    role: AgentRole = AgentRole.soul_forge,
) -> tuple[NativeAgentRuntime, ThreadStore, Path]:
    prompts_root = tmp_path / "prompts"
    definition = get_agent_definition(role)
    instruction_path = prompts_root / definition.instruction_file
    instruction_path.parent.mkdir(parents=True, exist_ok=True)
    instruction_path.write_text(
        f"# {definition.title}\n\nRole-specific instructions.\n", encoding="utf-8"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ThreadStore(tmp_path / "state" / "threads.json")
    return (
        NativeAgentRuntime(
            harness=harness,
            thread_store=store,
            prompts_root=prompts_root,
            workspace=workspace,
            model="codex-test-model",
        ),
        store,
        workspace,
    )


def test_runtime_binds_first_turn_and_resumes_the_same_scope(tmp_path: Path) -> None:
    harness = FakeAgentHarness(
        [
            _result("thread-001", "turn-001", started_new_thread=True),
            _result("thread-001", "turn-002", started_new_thread=False),
        ]
    )
    runtime, store, workspace = _runtime(tmp_path, harness)
    events: list[RuntimeEvent] = []

    first = runtime.run(
        AgentRole.soul_forge,
        "  Create an original synthwave artist.  ",
        scope="  neon-wasteland  ",
        on_event=events.append,
    )
    second = runtime.run(
        AgentRole.soul_forge,
        "Refine the visual identity.",
        scope="neon-wasteland",
    )

    assert first.started_new_thread is True
    assert second.started_new_thread is False
    assert [request.thread_id for request in harness.requests] == [None, "thread-001"]
    assert harness.requests[0].cwd == workspace
    assert harness.requests[0].model == "codex-test-model"
    assert harness.requests[0].prompt == (
        "Artist Matrix scope: neon-wasteland\n\nUser request:\nCreate an original synthwave artist."
    )
    assert store.get(AgentRole.soul_forge, "neon-wasteland").thread_id == "thread-001"  # type: ignore[union-attr]
    assert events and events[0].data == {"fake": True}


def test_runtime_new_thread_forgets_the_previous_binding(tmp_path: Path) -> None:
    harness = FakeAgentHarness([_result("thread-new", "turn-new", started_new_thread=True)])
    runtime, store, _ = _runtime(tmp_path, harness)
    store.bind(AgentRole.soul_forge, "neon-wasteland", "thread-old")

    result = runtime.run(
        AgentRole.soul_forge,
        "Start over from canonical artist data.",
        scope="neon-wasteland",
        new_thread=True,
    )

    assert harness.requests[0].thread_id is None
    assert result.thread_id == "thread-new"
    assert store.get(AgentRole.soul_forge, "neon-wasteland").thread_id == "thread-new"  # type: ignore[union-attr]


def test_runtime_forget_and_healthcheck_delegate_to_dependencies(tmp_path: Path) -> None:
    harness = FakeAgentHarness([])
    runtime, store, _ = _runtime(tmp_path, harness)
    store.bind(AgentRole.soul_forge, "global", "thread-001")

    assert runtime.healthcheck() == {"ok": True, "provider": "fake"}
    assert runtime.forget(AgentRole.soul_forge, "  ") is True
    assert runtime.forget(AgentRole.soul_forge, "global") is False


def test_runtime_login_and_close_delegate_to_harness(tmp_path: Path) -> None:
    harness = FakeAgentHarness([])
    runtime, _, _ = _runtime(tmp_path, harness)
    challenges: list[tuple[str, str | None]] = []

    result = runtime.login(
        device_code=True, on_challenge=lambda url, code: challenges.append((url, code))
    )
    runtime.close()

    assert result == {"success": True}
    assert challenges == [("https://example.test/login", "CODE")]
    assert harness.closed is True


@pytest.mark.parametrize("role", list(AgentRole))
def test_runtime_prompt_enforces_canonical_data_and_proposal_boundaries(
    tmp_path: Path,
    role: AgentRole,
) -> None:
    harness = FakeAgentHarness(
        [_result(f"thread-{role.value}", "turn-001", started_new_thread=True)]
    )
    runtime, _, _ = _runtime(tmp_path, harness, role=role)

    runtime.run(role, "  Complete this task safely.  ", scope="  ")

    request = harness.requests[0]
    instructions = request.developer_instructions
    definition = get_agent_definition(role)
    assert instructions.startswith(f"# {definition.title}\n\nRole-specific instructions.")
    assert "Canonical product data belongs to Artist Matrix, not to this thread." in instructions
    assert "Tool calls may create reviewable proposals" in instructions
    assert "never execute consequential actions" in instructions
    assert "Never edit project or data files directly." in instructions
    assert "Never call provider APIs directly." in instructions
    assert "show its action ID and ask the user to review it" in instructions
    assert f"Allowed tools for this role: {', '.join(definition.allowed_tools)}." in instructions
    assert (
        request.prompt == "Artist Matrix scope: global\n\nUser request:\nComplete this task safely."
    )


def test_runtime_rejects_empty_prompt_before_calling_harness(tmp_path: Path) -> None:
    harness = FakeAgentHarness([])
    runtime, _, _ = _runtime(tmp_path, harness)

    with pytest.raises(ValueError, match="prompt must not be empty"):
        runtime.run(AgentRole.soul_forge, " \n\t ")

    assert harness.requests == []
