from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import tomllib

import pytest
from codex_cli_bin import bundled_codex_path

from artist_matrix.agent_runtime.codex import (
    CODEX_PERMISSION_PROFILE,
    DISABLED_CODEX_FEATURES,
    CodexHarness,
    _codex_config_overrides,
)
from artist_matrix.agent_runtime.definitions import (
    MCP_TOOL_ALLOWLIST,
    AgentRole,
    get_agent_definition,
)
from artist_matrix.agent_runtime.events import RuntimeEvent, RuntimeEventType
from artist_matrix.agent_runtime.harness import HarnessTurnRequest, HarnessUnavailableError


class Phase(str, Enum):
    commentary = "commentary"
    final_answer = "final_answer"


class TurnStatus(str, Enum):
    completed = "completed"
    failed = "failed"


@dataclass
class TurnError:
    message: str


@dataclass
class Turn:
    id: str
    status: TurnStatus
    error: TurnError | None = None


@dataclass
class TurnPayload:
    thread_id: str
    turn_id: str
    turn: Turn


@dataclass
class DeltaPayload:
    thread_id: str
    turn_id: str
    item_id: str
    delta: str


@dataclass
class ToolProgressPayload:
    thread_id: str
    turn_id: str
    item_id: str
    message: str


@dataclass
class AgentMessage:
    id: str
    text: str
    phase: Phase | None = None
    type: str = "agentMessage"


@dataclass
class ToolItem:
    id: str
    type: str = "mcpToolCall"


@dataclass
class ItemEnvelope:
    root: AgentMessage | ToolItem


@dataclass
class ItemPayload:
    thread_id: str
    turn_id: str
    item_id: str
    item: ItemEnvelope


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class UsagePayload:
    thread_id: str
    turn_id: str
    token_usage: TokenUsage


@dataclass
class WarningPayload:
    thread_id: str
    message: str


@dataclass
class ErrorPayload:
    thread_id: str
    turn_id: str
    error: TurnError
    will_retry: bool = False


@dataclass
class Notification:
    method: str
    payload: object


class FakeStream:
    def __init__(self, notifications: list[Notification]) -> None:
        self.notifications = notifications
        self.closed = False

    def __iter__(self):  # noqa: ANN204
        return iter(self.notifications)

    def close(self) -> None:
        self.closed = True


class FakeAccount:
    account = SimpleNamespace(type="chatgpt")
    requires_openai_auth = False

    def model_dump(self, **_: object) -> dict[str, object]:
        return {
            "account": {"type": "chatgpt", "accessToken": "must-not-leak"},
            "requiresOpenaiAuth": False,
        }


class FakeLoginCompleted:
    success = True
    error = None

    def model_dump(self, **_: object) -> dict[str, object]:
        return {"success": True, "loginId": "must-not-leak"}


def _request(tmp_path: Path) -> HarnessTurnRequest:
    return HarnessTurnRequest(
        definition=get_agent_definition(AgentRole.director),
        developer_instructions="test instructions",
        prompt="test prompt",
        cwd=tmp_path,
    )


def test_healthcheck_uses_project_workspace_and_redacts_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    launched_cwds: list[str | None] = []
    launched_envs: list[dict[str, str] | None] = []
    thread_configs: list[dict[str, object] | None] = []

    class FakeCodex:
        metadata = SimpleNamespace(serverInfo=None)

        def __init__(self, config: object) -> None:
            launched_cwds.append(getattr(config, "cwd", None))
            launched_envs.append(getattr(config, "env", None))

        def account(self, *, refresh_token: bool) -> FakeAccount:
            assert refresh_token is True
            return FakeAccount()

        def thread_start(self, **kwargs: object) -> object:
            thread_configs.append(kwargs.get("config"))
            assert kwargs["ephemeral"] is True
            assert "sandbox" not in kwargs
            return SimpleNamespace(id="doctor-thread")

        def close(self) -> None:
            return None

    monkeypatch.setattr("artist_matrix.agent_runtime.codex.Codex", FakeCodex)
    harness = CodexHarness(
        codex_home=tmp_path / "codex-home",
        workspace=tmp_path / "codex-home" / "workspace",
        data_root=tmp_path / "data",
        action_root=tmp_path / "actions",
    )

    result = harness.healthcheck()
    repeated = harness.healthcheck()
    harness.close()

    assert result["ok"] is True
    assert repeated == result
    assert result["authenticated"] is True
    assert result["mcp_ready"] is True
    assert result["project_cwd"] == str((tmp_path / "codex-home" / "workspace").resolve())
    assert result["account"] == {
        "account": {"type": "chatgpt"},
        "requiresOpenaiAuth": False,
    }
    assert launched_cwds == [str((tmp_path / "codex-home" / "workspace").resolve())]
    assert launched_envs == [
        {
            "CODEX_HOME": str((tmp_path / "codex-home").resolve()),
            "ARTIST_MATRIX_DATA_ROOT": str((tmp_path / "data").resolve()),
            "ARTIST_MATRIX_ACTION_ROOT": str((tmp_path / "actions").resolve()),
        }
    ]
    assert thread_configs == [harness._thread_config(get_agent_definition(AgentRole.director))]
    assert (tmp_path / "codex-home").stat().st_mode & 0o777 == 0o700


def test_harness_rejects_workspace_outside_isolated_codex_home(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inside the application-owned Codex home"):
        CodexHarness(
            codex_home=tmp_path / "codex-home",
            workspace=tmp_path / "repository",
        )


def test_healthcheck_fails_when_openai_auth_is_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class UnauthenticatedAccount(FakeAccount):
        account = None
        requires_openai_auth = True

        def model_dump(self, **_: object) -> dict[str, object]:
            return {"account": None, "requiresOpenaiAuth": True}

    class FakeCodex:
        metadata = SimpleNamespace(serverInfo=None)

        def __init__(self, _: object) -> None:
            return None

        def account(self, *, refresh_token: bool) -> UnauthenticatedAccount:
            assert refresh_token is True
            return UnauthenticatedAccount()

        def close(self) -> None:
            return None

    monkeypatch.setattr("artist_matrix.agent_runtime.codex.Codex", FakeCodex)
    result = CodexHarness(codex_home=tmp_path / "home").healthcheck()

    assert result["ok"] is False
    assert result["authenticated"] is False
    assert result["mcp_ready"] is False
    assert "artist-matrix login" in str(result["error"])


def test_login_uses_public_sdk_flow_and_redacts_login_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeLoginHandle:
        auth_url = "https://example.test/login"

        def wait(self) -> FakeLoginCompleted:
            return FakeLoginCompleted()

    class FakeCodex:
        def __init__(self, _: object) -> None:
            return None

        def login_chatgpt(self) -> FakeLoginHandle:
            return FakeLoginHandle()

        def close(self) -> None:
            return None

    monkeypatch.setattr("artist_matrix.agent_runtime.codex.Codex", FakeCodex)
    challenges: list[tuple[str, str | None]] = []
    harness = CodexHarness(
        codex_home=tmp_path / "codex-home",
        workspace=tmp_path / "codex-home" / "workspace",
    )

    result = harness.login(on_challenge=lambda url, code: challenges.append((url, code)))
    harness.close()

    assert result == {"success": True}
    assert challenges == [("https://example.test/login", None)]


def test_native_harness_injects_required_mcp_config_without_project_trust() -> None:
    config = tomllib.loads("\n".join(_codex_config_overrides()))
    server = config["mcp_servers"]["artist_matrix"]
    permissions = config["permissions"][CODEX_PERMISSION_PROFILE]

    assert server["args"] == ["-m", "artist_matrix.agent_runtime.mcp_server"]
    assert tuple(server["enabled_tools"]) == MCP_TOOL_ALLOWLIST
    assert server["required"] is True
    assert server["default_tools_approval_mode"] == "auto"
    assert server["env_vars"] == [
        "ARTIST_MATRIX_DATA_ROOT",
        "ARTIST_MATRIX_ACTION_ROOT",
    ]
    assert config["default_permissions"] == CODEX_PERMISSION_PROFILE
    assert permissions["filesystem"][":minimal"] == "read"
    assert permissions["filesystem"][":workspace_roots"] == {".": "read"}
    assert permissions["network"] == {"enabled": False}
    assert all(config["features"][feature] is False for feature in DISABLED_CODEX_FEATURES)
    assert config["tools"] == {"web_search": False}
    assert config["web_search"] == "disabled"


@pytest.mark.parametrize("source", ["runtime-overrides", "project-config"])
def test_pinned_codex_reports_non_product_features_disabled(
    tmp_path: Path,
    source: str,
) -> None:
    codex_home = tmp_path / source
    codex_home.mkdir()
    command = [str(bundled_codex_path())]
    if source == "runtime-overrides":
        for override in _codex_config_overrides():
            command.extend(("-c", override))
    else:
        project_root = Path(__file__).resolve().parents[2]
        shutil.copy2(project_root / ".codex" / "config.toml", codex_home / "config.toml")
    command.extend(("features", "list"))
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(codex_home)

    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    states = {
        columns[0]: columns[-1] == "true"
        for line in completed.stdout.splitlines()
        if len(columns := line.split()) >= 3 and columns[-1] in {"true", "false"}
    }

    assert set(DISABLED_CODEX_FEATURES) <= states.keys()
    assert not {feature for feature in DISABLED_CODEX_FEATURES if states[feature]}


def test_specialist_thread_config_enforces_exact_role_tool_inventory() -> None:
    harness = CodexHarness(codex_bin="unused-in-unit-test")
    definition = get_agent_definition(AgentRole.soul_forge)

    config = harness._thread_config(definition)

    assert config == {
        "mcp_servers": {"artist_matrix": {"enabled_tools": list(definition.allowed_tools)}}
    }
    assert "propose_artist_profile" in definition.allowed_tools
    assert "propose_release" not in definition.allowed_tools


@pytest.mark.parametrize("resuming", [False, True])
def test_open_thread_applies_role_config_on_start_and_resume(
    tmp_path: Path,
    resuming: bool,
) -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class FakeCodex:
        def thread_start(self, *args: object, **kwargs: object) -> object:
            calls.append(("start", args, kwargs))
            return SimpleNamespace(id="thread-new")

        def thread_resume(self, *args: object, **kwargs: object) -> object:
            calls.append(("resume", args, kwargs))
            return SimpleNamespace(id="thread-existing")

    request = _request(tmp_path)
    if resuming:
        request = replace(request, thread_id="thread-existing")
    harness = CodexHarness(codex_bin="unused-in-unit-test")

    _, started_new = harness._open_thread(FakeCodex(), request)  # type: ignore[arg-type]

    method, args, kwargs = calls[0]
    assert method == ("resume" if resuming else "start")
    assert started_new is not resuming
    assert args == (("thread-existing",) if resuming else ())
    assert kwargs["config"] == harness._thread_config(request.definition)
    assert kwargs["approval_mode"].value == "deny_all"
    assert "sandbox" not in kwargs


def test_public_run_turn_wires_start_resume_and_stream_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def completed_stream() -> FakeStream:
        return FakeStream(
            [
                Notification(
                    "item/completed",
                    ItemPayload(
                        "thread-1",
                        "turn-1",
                        "message-1",
                        ItemEnvelope(
                            AgentMessage(
                                "message-1",
                                "Harness answer",
                                Phase.final_answer,
                            )
                        ),
                    ),
                ),
                Notification(
                    "turn/completed",
                    TurnPayload(
                        "thread-1",
                        "turn-1",
                        Turn("turn-1", TurnStatus.completed),
                    ),
                ),
            ]
        )

    class FakeTurnHandle:
        id = "turn-1"

        def stream(self) -> FakeStream:
            return completed_stream()

    class FakeThread:
        id = "thread-1"

        def set_name(self, name: str) -> None:
            assert name == "Artist Matrix Director"

        def turn(self, prompt: str, **kwargs: object) -> FakeTurnHandle:
            assert prompt == "test prompt"
            assert kwargs["approval_mode"].value == "deny_all"
            assert "sandbox" not in kwargs
            return FakeTurnHandle()

    class FakeCodex:
        def __init__(self, _: object) -> None:
            return None

        def thread_start(self, *args: object, **kwargs: object) -> FakeThread:
            calls.append(("start", args, kwargs))
            return FakeThread()

        def thread_resume(self, *args: object, **kwargs: object) -> FakeThread:
            calls.append(("resume", args, kwargs))
            return FakeThread()

        def close(self) -> None:
            return None

    monkeypatch.setattr("artist_matrix.agent_runtime.codex.Codex", FakeCodex)
    harness = CodexHarness(codex_home=tmp_path, workspace=tmp_path)
    request = _request(tmp_path)

    first = harness.run_turn(request)
    second = harness.run_turn(replace(request, thread_id=first.thread_id))
    harness.close()

    assert first.response == "Harness answer"
    assert first.started_new_thread is True
    assert second.response == "Harness answer"
    assert second.started_new_thread is False
    assert [call[0] for call in calls] == ["start", "resume"]
    assert calls[1][1] == ("thread-1",)


def test_codex_normalizes_streaming_delta_and_progress_notifications() -> None:
    harness = CodexHarness(codex_bin="unused-in-unit-test")
    delta = DeltaPayload("thread-1", "turn-1", "item-1", "hello")

    message = harness._normalize_event("item/agentMessage/delta", delta)
    reasoning = harness._normalize_event("item/reasoning/summaryTextDelta", delta)
    command = harness._normalize_event("item/commandExecution/outputDelta", delta)
    progress = harness._normalize_event(
        "item/mcpToolCall/progress",
        ToolProgressPayload("thread-1", "turn-1", "item-tool", "working"),
    )

    assert message is not None
    assert message.type == RuntimeEventType.message_delta
    assert message.thread_id == "thread-1"
    assert message.turn_id == "turn-1"
    assert message.item_id == "item-1"
    assert message.text == "hello"
    assert message.data == {}
    assert reasoning is not None and reasoning.type == RuntimeEventType.reasoning_delta
    assert reasoning.text == "hello"
    assert command is not None and command.type == RuntimeEventType.command_output
    assert command.text == "hello"
    assert progress is not None and progress.type == RuntimeEventType.tool_progress
    assert progress.text == "working"


def test_codex_normalizes_turn_item_usage_warning_and_error_notifications() -> None:
    harness = CodexHarness(codex_bin="unused-in-unit-test")
    turn_payload = TurnPayload(
        "thread-1",
        "turn-1",
        Turn("turn-1", TurnStatus.completed),
    )
    item_payload = ItemPayload(
        "thread-1",
        "turn-1",
        "item-tool",
        ItemEnvelope(ToolItem("item-tool")),
    )

    started = harness._normalize_event("turn/started", turn_payload)
    completed = harness._normalize_event("turn/completed", turn_payload)
    tool_started = harness._normalize_event("item/started", item_payload)
    tool_completed = harness._normalize_event("item/completed", item_payload)
    usage = harness._normalize_event(
        "thread/tokenUsage/updated",
        UsagePayload("thread-1", "turn-1", TokenUsage(5, 3)),
    )
    warning = harness._normalize_event(
        "warning",
        WarningPayload("thread-1", "configuration fallback"),
    )
    error = harness._normalize_event(
        "error",
        ErrorPayload("thread-1", "turn-1", TurnError("stream failed")),
    )

    assert started is not None and started.type == RuntimeEventType.turn_started
    assert started.turn_id == "turn-1"
    assert completed is not None and completed.type == RuntimeEventType.turn_completed
    assert tool_started is not None and tool_started.type == RuntimeEventType.tool_started
    assert tool_started.data["item_type"] == "mcpToolCall"
    assert tool_completed is not None and tool_completed.type == RuntimeEventType.tool_completed
    assert usage is not None and usage.type == RuntimeEventType.usage_updated
    assert usage.data["token_usage"] == {"input_tokens": 5, "output_tokens": 3}
    assert warning is not None and warning.type == RuntimeEventType.warning
    assert warning.data["message"] == "configuration fallback"
    assert error is not None and error.type == RuntimeEventType.error
    assert error.text == "stream failed"
    retrying = harness._normalize_event(
        "error",
        ErrorPayload("thread-1", "turn-1", TurnError("temporary"), will_retry=True),
    )
    assert retrying is not None and retrying.type == RuntimeEventType.warning
    assert retrying.data["will_retry"] is True
    assert harness._normalize_event("future/notification", turn_payload) is None


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (
            ItemEnvelope(AgentMessage("final", "Canonical answer", Phase.final_answer)),
            "Canonical answer",
        ),
        (ItemEnvelope(AgentMessage("legacy", "Legacy answer", None)), "Legacy answer"),
        (ItemEnvelope(AgentMessage("commentary", "Still working", Phase.commentary)), None),
        (ItemEnvelope(ToolItem("tool-1")), None),
    ],
)
def test_codex_extracts_only_final_agent_messages(
    item: ItemEnvelope,
    expected: str | None,
) -> None:
    assert CodexHarness()._final_message_from_item(item) == expected


def test_codex_collect_turn_prefers_completed_item_and_closes_stream(tmp_path: Path) -> None:
    stream = FakeStream(
        [
            Notification(
                "turn/started",
                TurnPayload("thread-1", "turn-1", Turn("turn-1", TurnStatus.completed)),
            ),
            Notification(
                "item/agentMessage/delta",
                DeltaPayload("thread-1", "turn-1", "message-1", "Partial answer"),
            ),
            Notification(
                "item/completed",
                ItemPayload(
                    "thread-1",
                    "turn-1",
                    "message-1",
                    ItemEnvelope(
                        AgentMessage("message-1", "Canonical final answer", Phase.final_answer)
                    ),
                ),
            ),
            Notification(
                "thread/tokenUsage/updated",
                UsagePayload("thread-1", "turn-1", TokenUsage(11, 7)),
            ),
            Notification(
                "turn/completed",
                TurnPayload("thread-1", "turn-1", Turn("turn-1", TurnStatus.completed)),
            ),
        ]
    )
    events: list[RuntimeEvent] = []

    result = CodexHarness()._collect_turn(
        request=_request(tmp_path),
        thread_id="thread-1",
        turn_id="turn-1",
        stream=stream,
        started_new=True,
        on_event=events.append,
    )

    assert result.response == "Canonical final answer"
    assert result.status == "completed"
    assert result.started_new_thread is True
    assert result.usage == {"input_tokens": 11, "output_tokens": 7}
    assert stream.closed is True
    assert RuntimeEventType.message_delta in [event.type for event in events]
    assert events[-1].type == RuntimeEventType.turn_completed


def test_codex_collect_turn_uses_deltas_when_no_final_item_exists(tmp_path: Path) -> None:
    stream = FakeStream(
        [
            Notification(
                "item/agentMessage/delta",
                DeltaPayload("thread-1", "turn-1", "message-1", "Hello "),
            ),
            Notification(
                "item/agentMessage/delta",
                DeltaPayload("thread-1", "turn-1", "message-1", "world"),
            ),
            Notification(
                "turn/completed",
                TurnPayload("thread-1", "turn-1", Turn("turn-1", TurnStatus.completed)),
            ),
        ]
    )

    result = CodexHarness()._collect_turn(
        request=_request(tmp_path),
        thread_id="thread-1",
        turn_id="turn-1",
        stream=stream,
        started_new=False,
        on_event=None,
    )

    assert result.response == "Hello world"
    assert stream.closed is True


def test_codex_collect_turn_raises_normalized_failure_and_closes_stream(
    tmp_path: Path,
) -> None:
    stream = FakeStream(
        [
            Notification(
                "error",
                ErrorPayload("thread-1", "turn-1", TurnError("authentication expired")),
            ),
            Notification(
                "turn/completed",
                TurnPayload(
                    "thread-1",
                    "turn-1",
                    Turn("turn-1", TurnStatus.failed, TurnError("authentication expired")),
                ),
            ),
        ]
    )

    with pytest.raises(HarnessUnavailableError, match="authentication expired"):
        CodexHarness()._collect_turn(
            request=_request(tmp_path),
            thread_id="thread-1",
            turn_id="turn-1",
            stream=stream,
            started_new=False,
            on_event=None,
        )

    assert stream.closed is True
