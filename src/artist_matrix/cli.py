"""Command-line product surface for the Codex-native Artist Matrix runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

from artist_matrix.agent_runtime.actions import (
    ActionExecutor,
    ActionLedger,
    ActionRecord,
    ActionStatus,
)
from artist_matrix.agent_runtime.codex import CodexHarness
from artist_matrix.agent_runtime.definitions import AgentRole
from artist_matrix.agent_runtime.domain_handlers import build_action_handlers
from artist_matrix.agent_runtime.events import RuntimeEvent, RuntimeEventType
from artist_matrix.agent_runtime.harness import HarnessUnavailableError
from artist_matrix.agent_runtime.service import NativeAgentRuntime
from artist_matrix.agent_runtime.threads import ThreadStore
from artist_matrix.state import ArtistMatrixSettings

_RUNTIME_NAMESPACE_VERSION = "codex-native-permissions-v2"


def build_runtime(
    settings: ArtistMatrixSettings | None = None,
    *,
    workspace: Path | None = None,
) -> NativeAgentRuntime:
    """Compose the product runtime in one place for CLI and future UI adapters."""

    resolved = settings or ArtistMatrixSettings()
    resolved_workspace = (workspace or resolved.resolved_codex_workspace).resolve()
    return NativeAgentRuntime(
        harness=CodexHarness(
            codex_bin=resolved.codex_bin,
            codex_home=resolved.resolved_codex_home,
            workspace=resolved_workspace,
            data_root=resolved.data_root,
            action_root=resolved.resolved_action_root,
        ),
        thread_store=ThreadStore(
            resolved.resolved_thread_store,
            namespace=_runtime_namespace(
                resolved.resolved_codex_home,
                resolved_workspace,
                resolved.codex_model,
            ),
        ),
        prompts_root=resolved.resolved_agent_prompts_root,
        workspace=resolved_workspace,
        model=resolved.codex_model,
    )


def _runtime_namespace(home: Path, workspace: Path, model: str | None) -> str:
    context = (
        f"{_RUNTIME_NAMESPACE_VERSION}\0{home.resolve()}\0{workspace.resolve()}\0"
        f"{model or 'account-default'}"
    )
    return hashlib.sha256(context.encode("utf-8")).hexdigest()[:16]


class _StreamPrinter:
    def __init__(self) -> None:
        self.saw_message = False
        self._line_open = False

    def __call__(self, event: RuntimeEvent) -> None:
        if event.type == RuntimeEventType.message_delta and event.text:
            print(event.text, end="", flush=True)
            self.saw_message = True
            self._line_open = True
            return
        if event.type == RuntimeEventType.tool_started:
            self._newline()
            print(f"[tool] {event.data.get('item_type', 'operation')} started")
            return
        if event.type == RuntimeEventType.tool_progress and event.text:
            self._newline()
            print(f"[tool] {event.text}")
            return
        if event.type == RuntimeEventType.warning:
            self._newline()
            print("[warning] Codex reported a runtime warning", file=sys.stderr)
            return
        if event.type == RuntimeEventType.error and event.text:
            self._newline()
            print(f"[error] {event.text}", file=sys.stderr)

    def finish(self) -> None:
        self._newline()

    def _newline(self) -> None:
        if self._line_open:
            print()
            self._line_open = False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="artist-matrix",
        description="Run Artist Matrix on the Codex open agent harness.",
    )
    subparsers = parser.add_subparsers(dest="command")

    chat = subparsers.add_parser("chat", help="Open a persistent interactive agent thread")
    _add_agent_scope_arguments(chat)

    run = subparsers.add_parser("run", help="Run one streamed agent turn")
    _add_agent_scope_arguments(run)
    run.add_argument("prompt", help="Task for the selected agent")
    run.add_argument("--new", action="store_true", help="Start a fresh thread for this scope")
    run.add_argument("--json", action="store_true", help="Emit only the final result as JSON")

    actions = subparsers.add_parser("actions", help="List reviewable application actions")
    actions.add_argument("--status", choices=[status.value for status in ActionStatus])

    approve = subparsers.add_parser("approve", help="Review and execute one proposed action")
    approve.add_argument("action_id")
    approve.add_argument("--yes", action="store_true", help="Skip the interactive confirmation")

    reject = subparsers.add_parser("reject", help="Reject one proposed action")
    reject.add_argument("action_id")
    reject.add_argument("--reason", default="Rejected by user")

    subparsers.add_parser("threads", help="List persistent agent-thread bindings")
    login = subparsers.add_parser("login", help="Sign in the SDK-pinned Codex runtime")
    login.add_argument(
        "--device-code",
        action="store_true",
        help="Use a device code instead of the local browser callback",
    )
    subparsers.add_parser("doctor", help="Check the pinned Codex runtime and authentication")
    subparsers.add_parser("legacy", help="Launch the previous deterministic TUI")
    return parser


def _add_agent_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent",
        choices=[role.value for role in AgentRole],
        default=AgentRole.director.value,
    )
    parser.add_argument("--scope", default="global", help="Artist slug or workflow scope")


def _run_once(args: argparse.Namespace, settings: ArtistMatrixSettings) -> int:
    runtime = build_runtime(settings)
    printer = _StreamPrinter()
    try:
        result = runtime.run(
            args.agent,
            args.prompt,
            scope=args.scope,
            new_thread=args.new,
            on_event=None if args.json else printer,
        )
        if args.json:
            print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
        else:
            printer.finish()
            if not printer.saw_message and result.response:
                print(result.response)
            print(f"\nthread: {result.thread_id}")
        return 0 if result.status == "completed" else 1
    except HarnessUnavailableError as exc:
        printer.finish()
        print(f"Artist Matrix could not run Codex: {exc}", file=sys.stderr)
        print("Run `artist-matrix login`, then `artist-matrix doctor`.", file=sys.stderr)
        return 2
    finally:
        runtime.close()


def _chat(args: argparse.Namespace, settings: ArtistMatrixSettings) -> int:
    runtime = build_runtime(settings)
    ledger = ActionLedger(settings)
    role = AgentRole(args.agent)
    scope = args.scope
    print("Artist Matrix // Codex-native agent runtime")
    print(f"agent={role.value} scope={scope}")
    print("Type /help for commands. Consequential actions require /approve <id>.")
    try:
        while True:
            try:
                raw = input(f"\n{role.value}:{scope}> ").strip()
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                print("\nUse /quit to exit.")
                continue
            if not raw:
                continue
            if raw.startswith("/"):
                outcome = _handle_chat_command(raw, runtime, ledger, role, scope)
                if outcome[0] == "quit":
                    return 0
                role, scope = outcome[1], outcome[2]
                continue

            printer = _StreamPrinter()
            try:
                result = runtime.run(role, raw, scope=scope, on_event=printer)
            except HarnessUnavailableError as exc:
                printer.finish()
                print(f"Codex turn failed: {exc}", file=sys.stderr)
                print(
                    "Use /new to replace a stale thread, /doctor for diagnostics, "
                    "or run `artist-matrix login` outside chat."
                )
                continue
            printer.finish()
            if not printer.saw_message and result.response:
                print(result.response)
    finally:
        runtime.close()


def _handle_chat_command(
    raw: str,
    runtime: NativeAgentRuntime,
    ledger: ActionLedger,
    role: AgentRole,
    scope: str,
) -> tuple[str, AgentRole, str]:
    command, _, argument = raw.partition(" ")
    argument = argument.strip()
    if command in {"/quit", "/q", "/exit"}:
        return "quit", role, scope
    if command == "/help":
        print(
            "/agent <role>  /scope <name>  /new  /threads  /actions\n"
            "/approve <id>  /reject <id>  /doctor  /quit"
        )
    elif command == "/agent":
        try:
            role = AgentRole(argument)
            print(f"agent={role.value}")
        except ValueError:
            print("roles: " + ", ".join(item.value for item in AgentRole))
    elif command == "/scope":
        if argument:
            scope = argument
            print(f"scope={scope}")
        else:
            print("Usage: /scope <artist-slug-or-workflow>")
    elif command == "/new":
        removed = runtime.forget(role, scope)
        print("Thread binding cleared." if removed else "No saved thread binding existed.")
    elif command == "/threads":
        _print_threads(runtime)
    elif command == "/actions":
        _print_actions(ledger)
    elif command == "/approve":
        if argument:
            _approve_action(ledger, argument, assume_yes=False)
        else:
            print("Usage: /approve <action-id>")
    elif command == "/reject":
        if argument:
            _reject_action(ledger, argument, reason="Rejected in chat")
        else:
            print("Usage: /reject <action-id>")
    elif command == "/doctor":
        print(json.dumps(runtime.healthcheck(), indent=2, sort_keys=True))
    else:
        print("Unknown command. Type /help.")
    return "continue", role, scope


def _print_threads(runtime: NativeAgentRuntime) -> None:
    bindings = runtime.threads()
    if not bindings:
        print("No persistent thread bindings.")
        return
    for binding in bindings:
        print(
            f"{binding.role.value:<17} {binding.scope:<24} "
            f"{binding.thread_id}  {binding.updated_at.isoformat()}"
        )


def _print_actions(ledger: ActionLedger, status: str | None = None) -> None:
    records = ledger.list_actions(status=status)
    if not records:
        print("No matching actions.")
        return
    for record in records:
        print(
            f"{record.action_id}  {record.status.value:<9} "
            f"{record.kind.value:<20} {record.created_at.isoformat()}"
        )


def _print_action_review(record: ActionRecord) -> None:
    print(json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True))


def _approve_action(ledger: ActionLedger, action_id: str, *, assume_yes: bool) -> int:
    try:
        record = ledger.get(action_id)
        _print_action_review(record)
        if not assume_yes:
            choice = input("Approve this host action? [y/N]: ").strip().lower()
            if choice not in {"y", "yes"}:
                print("Action left pending.")
                return 1
        completed = ActionExecutor(
            ledger,
            handlers=build_action_handlers(ledger.settings),
        ).approve_and_execute(action_id)
        _print_action_review(completed)
        return 0 if completed.status in {ActionStatus.COMPLETED, ActionStatus.QUEUED} else 1
    except Exception as exc:  # noqa: BLE001 - CLI reports validation and transition errors
        print(f"Action approval failed: {exc}", file=sys.stderr)
        return 2


def _reject_action(ledger: ActionLedger, action_id: str, *, reason: str) -> int:
    try:
        rejected = ActionExecutor(ledger).reject(action_id, reason=reason)
        _print_action_review(rejected)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI reports validation and transition errors
        print(f"Action rejection failed: {exc}", file=sys.stderr)
        return 2


def _legacy() -> int:
    from artist_matrix.tui.__main__ import legacy_main

    legacy_main()
    return 0


def _login(settings: ArtistMatrixSettings, *, device_code: bool) -> int:
    runtime = build_runtime(settings)

    def show_challenge(url: str, user_code: str | None) -> None:
        print(f"Open this URL to sign in:\n{url}")
        if user_code is not None:
            print(f"Device code: {user_code}")
        print("Waiting for Codex sign-in to complete...")

    try:
        runtime.login(device_code=device_code, on_challenge=show_challenge)
        print("Codex sign-in completed.")
        return 0
    except HarnessUnavailableError as exc:
        print(f"Codex sign-in failed: {exc}", file=sys.stderr)
        return 2
    finally:
        runtime.close()


def main(argv: Sequence[str] | None = None) -> None:
    settings = ArtistMatrixSettings()
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    command = args.command
    if command is None:
        if settings.agent_runtime.lower() == "legacy":
            raise SystemExit(_legacy())
        args = parser.parse_args(["chat"])
        command = "chat"

    if command == "run":
        code = _run_once(args, settings)
    elif command == "chat":
        code = _chat(args, settings)
    elif command == "actions":
        _print_actions(ActionLedger(settings), args.status)
        code = 0
    elif command == "approve":
        code = _approve_action(ActionLedger(settings), args.action_id, assume_yes=args.yes)
    elif command == "reject":
        code = _reject_action(ActionLedger(settings), args.action_id, reason=args.reason)
    elif command == "threads":
        runtime = build_runtime(settings)
        try:
            _print_threads(runtime)
            code = 0
        finally:
            runtime.close()
    elif command == "login":
        code = _login(settings, device_code=args.device_code)
    elif command == "doctor":
        runtime = build_runtime(settings)
        try:
            result = runtime.healthcheck()
            print(json.dumps(result, indent=2, sort_keys=True))
            code = 0 if result.get("ok") else 2
        finally:
            runtime.close()
    elif command == "legacy":
        code = _legacy()
    else:
        parser.error(f"Unknown command: {command}")
        return
    raise SystemExit(code)


__all__ = ["build_runtime", "main"]
