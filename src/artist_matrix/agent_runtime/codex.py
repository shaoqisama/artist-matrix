"""Codex SDK/app-server implementation of the Artist Matrix harness contract."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TypeAlias, cast

from openai_codex import ApprovalMode, Codex, CodexConfig, __version__ as SDK_VERSION

from artist_matrix.agent_runtime.definitions import (
    MCP_TOOL_ALLOWLIST,
    AgentDefinition,
    AgentRole,
    get_agent_definition,
)
from artist_matrix.agent_runtime.events import RuntimeEvent, RuntimeEventType
from artist_matrix.agent_runtime.harness import (
    EventHandler,
    HarnessTurnRequest,
    HarnessTurnResult,
    HarnessUnavailableError,
    LoginChallengeHandler,
)

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

CODEX_PERMISSION_PROFILE = "artist_matrix_readonly"

# Pin every non-product capability that could add tools, external data, filesystem
# access, delegation, or interactive permission flows to the model's inventory.
# Internal transport/model features (for example request compression and remote
# compaction) are deliberately not part of this list.
DISABLED_CODEX_FEATURES = (
    "apps",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode",
    "code_mode_host",
    "computer_use",
    "goals",
    "hooks",
    "image_generation",
    "memories",
    "multi_agent",
    "multi_agent_v2",
    "plugins",
    "remote_plugin",
    "request_permissions_tool",
    "shell_tool",
    "skill_mcp_dependency_install",
    "skill_search",
    "tool_call_mcp_elicitation",
    "tool_suggest",
    "unified_exec",
    "view_image",
    "workspace_dependencies",
)


class CodexHarness:
    """Run persistent, streamed product agents on the local Codex app-server."""

    def __init__(
        self,
        *,
        codex_bin: str | None = None,
        codex_home: Path | str | None = None,
        workspace: Path | str | None = None,
        data_root: Path | str | None = None,
        action_root: Path | str | None = None,
    ) -> None:
        self._codex_bin = codex_bin
        default_home = Path.cwd() / ".cache" / "artist-matrix" / "codex-home"
        self._codex_home = Path(codex_home or default_home).resolve()
        default_workspace = self._codex_home / "workspace"
        workspace_path = Path(workspace or default_workspace).resolve()
        if not workspace_path.is_relative_to(self._codex_home):
            raise ValueError("Codex workspace must be inside the application-owned Codex home")
        self._default_workspace = str(workspace_path)
        self._data_root = str(Path(data_root).resolve()) if data_root is not None else None
        self._action_root = str(Path(action_root).resolve()) if action_root is not None else None
        self._codex: Codex | None = None
        self._workspace: str | None = None
        self._mcp_ready = False

    def run_turn(
        self,
        request: HarnessTurnRequest,
        *,
        on_event: EventHandler | None = None,
    ) -> HarnessTurnResult:
        try:
            codex = self._client(request)
            thread, started_new = self._open_thread(codex, request)
            if started_new:
                thread.set_name(request.definition.title)
                self._emit(
                    on_event,
                    RuntimeEvent(
                        type=RuntimeEventType.thread_started,
                        thread_id=thread.id,
                        data={"role": request.definition.role.value},
                    ),
                )

            handle = thread.turn(
                request.prompt,
                approval_mode=ApprovalMode.deny_all,
            )
            return self._collect_turn(
                request=request,
                thread_id=thread.id,
                turn_id=handle.id,
                stream=handle.stream(),
                started_new=started_new,
                on_event=on_event,
            )
        except HarnessUnavailableError:
            self.close()
            raise
        except Exception as exc:  # noqa: BLE001 - normalize SDK/process/auth failures
            self.close()
            self._emit(
                on_event,
                RuntimeEvent(type=RuntimeEventType.error, text=str(exc)),
            )
            raise HarnessUnavailableError(f"Codex app-server turn failed: {exc}") from exc

    def healthcheck(self) -> dict[str, object]:
        """Verify app-server version, authentication, and the required MCP boundary."""

        try:
            codex = self._client(None)
            account = codex.account(refresh_token=True)
            account_payload = self._redact(account.model_dump(mode="json", by_alias=True))
            authenticated = account.account is not None or not account.requires_openai_auth
            server_info = codex.metadata.serverInfo
            server_payload = (
                server_info.model_dump(mode="json") if server_info is not None else None
            )
            server_version = getattr(server_info, "version", None)
            version_matches = server_version in {None, SDK_VERSION}
            if authenticated and version_matches and not self._mcp_ready:
                definition = get_agent_definition(AgentRole.director)
                codex.thread_start(
                    approval_mode=ApprovalMode.deny_all,
                    config=self._thread_config(definition),
                    cwd=self._default_workspace,
                    developer_instructions="Artist Matrix runtime readiness probe.",
                    ephemeral=True,
                    service_name="artist_matrix_doctor",
                )
                self._mcp_ready = True

            ok = authenticated and version_matches and self._mcp_ready
            error: str | None = None
            if not authenticated:
                error = "Codex authentication is required; run `artist-matrix login`."
            elif not version_matches:
                error = f"Codex server {server_version!r} does not match SDK {SDK_VERSION!r}."
            result: dict[str, object] = {
                "ok": ok,
                "authenticated": authenticated,
                "mcp_ready": self._mcp_ready,
                "sdk_version": SDK_VERSION,
                "project_cwd": self._workspace,
                "codex_home": str(self._codex_home),
                "server": server_payload,
                "account": account_payload,
                **({"error": error} if error is not None else {}),
            }
            return result
        except Exception as exc:  # noqa: BLE001 - doctor reports rather than raises
            self.close()
            return {"ok": False, "error": str(exc)}

    def login(
        self,
        *,
        device_code: bool = False,
        on_challenge: LoginChallengeHandler | None = None,
    ) -> dict[str, object]:
        """Authenticate the SDK-pinned Codex runtime without a separate CLI install."""

        try:
            codex = self._client(None)
            if device_code:
                device_handle = codex.login_chatgpt_device_code()
                url = device_handle.verification_url
                user_code: str | None = device_handle.user_code
                if on_challenge is not None:
                    on_challenge(url, user_code)
                completed = device_handle.wait()
            else:
                browser_handle = codex.login_chatgpt()
                url = browser_handle.auth_url
                user_code = None
                if on_challenge is not None:
                    on_challenge(url, user_code)
                completed = browser_handle.wait()
            payload = completed.model_dump(mode="json", by_alias=True)
            payload.pop("loginId", None)
            if not completed.success:
                raise HarnessUnavailableError(completed.error or "Codex sign-in did not complete")
            return payload
        except HarnessUnavailableError:
            self.close()
            raise
        except Exception as exc:  # noqa: BLE001 - normalize app-server/login failures
            self.close()
            raise HarnessUnavailableError(f"Codex sign-in failed: {exc}") from exc

    def close(self) -> None:
        if self._codex is not None:
            self._codex.close()
            self._codex = None
            self._workspace = None
            self._mcp_ready = False

    def _client(self, request: HarnessTurnRequest | None) -> Codex:
        workspace = str(request.cwd) if request is not None else self._default_workspace
        if self._codex is not None:
            if workspace is not None and workspace != self._workspace:
                raise HarnessUnavailableError("A Codex harness cannot span multiple workspaces")
            return self._codex
        self._prepare_runtime_directories(workspace)
        config = CodexConfig(
            codex_bin=self._codex_bin,
            config_overrides=_codex_config_overrides(),
            cwd=workspace,
            env=self._runtime_environment(),
            client_name="artist_matrix",
            client_title="Artist Matrix",
        )
        self._codex = Codex(config)
        self._workspace = workspace
        return self._codex

    def _open_thread(self, codex: Codex, request: HarnessTurnRequest) -> tuple[Any, bool]:
        thread_config = self._thread_config(request.definition)
        if request.thread_id:
            return (
                codex.thread_resume(
                    request.thread_id,
                    config=thread_config,
                    cwd=str(request.cwd),
                    developer_instructions=request.developer_instructions,
                    model=request.model,
                    approval_mode=ApprovalMode.deny_all,
                ),
                False,
            )

        return (
            codex.thread_start(
                config=thread_config,
                cwd=str(request.cwd),
                developer_instructions=request.developer_instructions,
                model=request.model,
                approval_mode=ApprovalMode.deny_all,
                service_name="artist_matrix",
            ),
            True,
        )

    def _collect_turn(
        self,
        *,
        request: HarnessTurnRequest,
        thread_id: str,
        turn_id: str,
        stream: Any,
        started_new: bool,
        on_event: EventHandler | None,
    ) -> HarnessTurnResult:
        final_response: str | None = None
        streamed_response: list[str] = []
        usage: dict[str, object] | None = None
        status = "inProgress"
        error: str | None = None
        saw_completion = False

        try:
            for notification in stream:
                payload = notification.payload
                event = self._normalize_event(notification.method, payload)
                if event is not None:
                    self._emit(on_event, event)
                    if event.type == RuntimeEventType.message_delta and event.text:
                        streamed_response.append(event.text)

                if notification.method == "item/completed":
                    candidate = self._final_message_from_item(getattr(payload, "item", None))
                    if candidate is not None:
                        final_response = candidate
                elif notification.method == "thread/tokenUsage/updated":
                    usage_payload = getattr(payload, "token_usage", None)
                    usage = self._dump(usage_payload)
                elif notification.method == "turn/completed":
                    saw_completion = True
                    turn = getattr(payload, "turn", None)
                    turn_status = getattr(turn, "status", None)
                    status = getattr(turn_status, "value", str(turn_status or "completed"))
                    turn_error = getattr(turn, "error", None)
                    error = getattr(turn_error, "message", None)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

        if final_response is None and streamed_response:
            final_response = "".join(streamed_response)
        if not saw_completion:
            raise HarnessUnavailableError("Codex event stream ended before turn/completed")
        if status == "failed":
            raise HarnessUnavailableError(error or "Codex turn failed without an error message")

        return HarnessTurnResult(
            thread_id=thread_id,
            turn_id=turn_id,
            response=final_response,
            status=status,
            started_new_thread=started_new,
            usage=usage,
            error=error,
        )

    def _normalize_event(self, method: str, payload: object) -> RuntimeEvent | None:
        thread_id = getattr(payload, "thread_id", None)
        turn_id = getattr(payload, "turn_id", None)
        item_id = getattr(payload, "item_id", None)
        data = self._dump(payload)

        if method == "turn/started":
            turn = getattr(payload, "turn", None)
            return RuntimeEvent(
                type=RuntimeEventType.turn_started,
                thread_id=thread_id,
                turn_id=getattr(turn, "id", turn_id),
                data=data,
            )
        if method == "turn/completed":
            turn = getattr(payload, "turn", None)
            return RuntimeEvent(
                type=RuntimeEventType.turn_completed,
                thread_id=thread_id,
                turn_id=getattr(turn, "id", turn_id),
                data=data,
            )
        if method == "item/agentMessage/delta":
            return RuntimeEvent(
                type=RuntimeEventType.message_delta,
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                text=getattr(payload, "delta", None),
            )
        if "reasoning" in method.lower() and method.endswith("Delta"):
            return RuntimeEvent(
                type=RuntimeEventType.reasoning_delta,
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                text=getattr(payload, "delta", None),
            )
        if method == "item/commandExecution/outputDelta":
            return RuntimeEvent(
                type=RuntimeEventType.command_output,
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                text=getattr(payload, "delta", None),
            )
        if method in {"turn/plan/updated", "item/plan/delta"}:
            return RuntimeEvent(
                type=RuntimeEventType.plan_updated,
                thread_id=thread_id,
                turn_id=turn_id,
                text=getattr(payload, "delta", None),
                data=data,
            )
        if method == "item/mcpToolCall/progress":
            return RuntimeEvent(
                type=RuntimeEventType.tool_progress,
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                text=getattr(payload, "message", None),
            )
        if method in {"item/started", "item/completed"}:
            item = getattr(payload, "item", None)
            root = getattr(item, "root", item)
            item_type = getattr(root, "type", root.__class__.__name__ if root else "unknown")
            tool_types = {
                "commandExecution",
                "dynamicToolCall",
                "fileChange",
                "imageGeneration",
                "mcpToolCall",
                "webSearch",
            }
            if item_type not in tool_types:
                return None
            return RuntimeEvent(
                type=(
                    RuntimeEventType.tool_started
                    if method == "item/started"
                    else RuntimeEventType.tool_completed
                ),
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=getattr(root, "id", item_id),
                data={"item_type": str(item_type), "item": self._dump(root)},
            )
        if method == "thread/tokenUsage/updated":
            return RuntimeEvent(
                type=RuntimeEventType.usage_updated,
                thread_id=thread_id,
                turn_id=turn_id,
                data=data,
            )
        if method == "error":
            turn_error = getattr(payload, "error", None)
            will_retry = bool(getattr(payload, "will_retry", False))
            return RuntimeEvent(
                type=(RuntimeEventType.warning if will_retry else RuntimeEventType.error),
                thread_id=thread_id,
                turn_id=turn_id,
                text=getattr(turn_error, "message", str(turn_error)),
                data={**data, "will_retry": will_retry},
            )
        if "warning" in method.lower() or "deprecation" in method.lower():
            return RuntimeEvent(
                type=RuntimeEventType.warning,
                thread_id=thread_id,
                turn_id=turn_id,
                data=data,
            )
        return None

    def _final_message_from_item(self, item: object) -> str | None:
        root = getattr(item, "root", item)
        if getattr(root, "type", None) != "agentMessage":
            return None
        phase = getattr(root, "phase", None)
        phase_value = getattr(phase, "value", phase)
        if phase_value not in {None, "final_answer"}:
            return None
        text = getattr(root, "text", None)
        return text if isinstance(text, str) else None

    def _dump(self, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(mode="json", by_alias=True)
            return dumped if isinstance(dumped, dict) else {"value": dumped}
        if is_dataclass(value) and not isinstance(value, type):
            dumped = asdict(cast(Any, value))
            return dumped if isinstance(dumped, dict) else {"value": dumped}
        if isinstance(value, dict):
            return value
        return {"value": str(value)}

    def _emit(self, handler: EventHandler | None, event: RuntimeEvent) -> None:
        if handler is not None:
            handler(event)

    def _thread_config(self, definition: AgentDefinition) -> JsonObject:
        """Narrow the host MCP inventory to the active specialist's exact tools."""

        return {"mcp_servers": {"artist_matrix": {"enabled_tools": list(definition.allowed_tools)}}}

    def _prepare_runtime_directories(self, workspace: str | None) -> None:
        for path in (self._codex_home, Path(workspace) if workspace else None):
            if path is None:
                continue
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            if os.name != "nt":
                path.chmod(0o700)

    def _runtime_environment(self) -> dict[str, str]:
        environment = {"CODEX_HOME": str(self._codex_home)}
        if self._data_root is not None:
            environment["ARTIST_MATRIX_DATA_ROOT"] = self._data_root
        if self._action_root is not None:
            environment["ARTIST_MATRIX_ACTION_ROOT"] = self._action_root
        return environment

    def _redact(self, value: Any) -> Any:
        secret_keys = {
            "access_token",
            "accesstoken",
            "api_key",
            "apikey",
            "refresh_token",
            "refreshtoken",
        }
        if isinstance(value, dict):
            return {
                key: self._redact(item)
                for key, item in value.items()
                if key.lower() not in secret_keys
            }
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return value


def _codex_config_overrides() -> tuple[str, ...]:
    """Expose only the host-owned MCP boundary to product-agent threads."""

    module_args = ["-m", "artist_matrix.agent_runtime.mcp_server"]
    return (
        f'default_permissions="{CODEX_PERMISSION_PROFILE}"',
        (
            f"permissions.{CODEX_PERMISSION_PROFILE}="
            '{description="Read only the empty Artist Matrix workspace", '
            'filesystem={":minimal"="read", ":workspace_roots"={"."="read"}}, '
            "network={enabled=false}}"
        ),
        "allow_login_shell=false",
        'web_search="disabled"',
        "tools.web_search=false",
        *(f"features.{feature}=false" for feature in DISABLED_CODEX_FEATURES),
        "apps._default.enabled=false",
        "agents.enabled=false",
        f"mcp_servers.artist_matrix.command={json.dumps(sys.executable)}",
        f"mcp_servers.artist_matrix.args={json.dumps(module_args)}",
        (
            "mcp_servers.artist_matrix.env_vars="
            f"{json.dumps(['ARTIST_MATRIX_DATA_ROOT', 'ARTIST_MATRIX_ACTION_ROOT'])}"
        ),
        "mcp_servers.artist_matrix.enabled=true",
        "mcp_servers.artist_matrix.required=true",
        "mcp_servers.artist_matrix.startup_timeout_sec=20",
        "mcp_servers.artist_matrix.tool_timeout_sec=60",
        (f"mcp_servers.artist_matrix.enabled_tools={json.dumps(list(MCP_TOOL_ALLOWLIST))}"),
        'mcp_servers.artist_matrix.default_tools_approval_mode="auto"',
    )


__all__ = [
    "CODEX_PERMISSION_PROFILE",
    "DISABLED_CODEX_FEATURES",
    "CodexHarness",
]
