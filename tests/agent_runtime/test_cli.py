from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from artist_matrix.agent_runtime.actions import ActionKind, ActionLedger, ActionStatus
from artist_matrix.agent_runtime.events import AgentTurnResult, RuntimeEvent, RuntimeEventType
from artist_matrix.cli import _runtime_namespace, main
from artist_matrix.state import ArtistMatrixSettings


def _profile_payload() -> dict[str, object]:
    return {
        "name": "Neon Wasteland",
        "persona_tags": ["retro"],
        "lyric_style": "synthwave stories",
        "visual_style": "neon glitch",
        "influences": ["Kavinsky"],
    }


def _configure_data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ArtistMatrixSettings:
    monkeypatch.setenv("ARTIST_MATRIX_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ARTIST_MATRIX_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("ARTIST_MATRIX_ACTION_ROOT", str(tmp_path / "actions"))
    return ArtistMatrixSettings()


def test_runtime_namespace_invalidates_pre_permission_profile_threads(tmp_path: Path) -> None:
    home = tmp_path / "codex-home"
    workspace = home / "workspace"
    model = "account-default"
    legacy_context = f"{home.resolve()}\0{workspace.resolve()}\0{model}"
    legacy_namespace = hashlib.sha256(legacy_context.encode("utf-8")).hexdigest()[:16]

    assert _runtime_namespace(home, workspace, None) != legacy_namespace


def test_run_command_streams_native_result_and_closes_runtime(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeRuntime:
        closed = False
        calls: list[tuple[object, ...]] = []

        def run(self, role, prompt, **kwargs):  # noqa: ANN001, ANN201
            self.calls.append((role, prompt, kwargs["scope"], kwargs["new_thread"]))
            kwargs["on_event"](
                RuntimeEvent(type=RuntimeEventType.message_delta, text="Streamed answer")
            )
            return AgentTurnResult(
                role=str(role),
                thread_id="thread-001",
                turn_id="turn-001",
                response="Streamed answer",
                status="completed",
                started_new_thread=True,
            )

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    monkeypatch.setattr("artist_matrix.cli.build_runtime", lambda settings: runtime)

    with pytest.raises(SystemExit, match="0"):
        main(
            [
                "run",
                "--agent",
                "soul_forge",
                "--scope",
                "neon-wasteland",
                "--new",
                "Create the identity",
            ]
        )

    output = capsys.readouterr().out
    assert "Streamed answer" in output
    assert "thread: thread-001" in output
    assert runtime.calls == [("soul_forge", "Create the identity", "neon-wasteland", True)]
    assert runtime.closed is True


def test_doctor_command_uses_runtime_health_exit_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeRuntime:
        def healthcheck(self) -> dict[str, object]:
            return {"ok": False, "error": "login required"}

        def close(self) -> None:
            return None

    monkeypatch.setattr("artist_matrix.cli.build_runtime", lambda settings: FakeRuntime())

    with pytest.raises(SystemExit, match="2"):
        main(["doctor"])

    assert "login required" in capsys.readouterr().out


def test_actions_command_lists_pending_proposals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _configure_data_root(monkeypatch, tmp_path)
    record = ActionLedger(settings).propose(
        ActionKind.SAVE_PERSONA,
        {"profile": _profile_payload()},
    )

    with pytest.raises(SystemExit, match="0"):
        main(["actions", "--status", "pending"])

    output = capsys.readouterr().out
    assert str(record.action_id) in output
    assert "save_persona" in output
    assert "pending" in output


def test_approve_requires_confirmation_then_executes_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _configure_data_root(monkeypatch, tmp_path)
    ledger = ActionLedger(settings)
    record = ledger.propose(
        ActionKind.SAVE_PERSONA,
        {"profile": _profile_payload()},
    )
    monkeypatch.setattr("builtins.input", lambda _: "no")

    with pytest.raises(SystemExit, match="1"):
        main(["approve", str(record.action_id)])

    assert ledger.get(record.action_id).status == ActionStatus.PENDING
    assert not (tmp_path / "artists" / "neon-wasteland.json").exists()

    with pytest.raises(SystemExit, match="0"):
        main(["approve", str(record.action_id), "--yes"])
    with pytest.raises(SystemExit, match="0"):
        main(["approve", str(record.action_id), "--yes"])

    completed = ledger.get(record.action_id)
    assert completed.status == ActionStatus.COMPLETED
    assert completed.attempts == 1
    assert (tmp_path / "artists" / "neon-wasteland.json").exists()


def test_reject_command_prevents_later_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _configure_data_root(monkeypatch, tmp_path)
    ledger = ActionLedger(settings)
    record = ledger.propose(
        ActionKind.SAVE_PERSONA,
        {"profile": _profile_payload()},
    )

    with pytest.raises(SystemExit, match="0"):
        main(["reject", str(record.action_id), "--reason", "Needs another pass"])
    with pytest.raises(SystemExit, match="2"):
        main(["approve", str(record.action_id), "--yes"])

    rejected = ledger.get(record.action_id)
    assert rejected.status == ActionStatus.REJECTED
    assert rejected.rejection_reason == "Needs another pass"


def test_approve_reports_local_outbox_queue_as_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _configure_data_root(monkeypatch, tmp_path)
    ledger = ActionLedger(settings)
    record = ledger.propose(
        ActionKind.SCHEDULE_CAMPAIGN,
        {
            "artist_slug": "neon-wasteland",
            "title": "Launch",
            "platform": "echo",
            "beats": ["Teaser"],
        },
    )

    with pytest.raises(SystemExit, match="0"):
        main(["approve", str(record.action_id), "--yes"])

    queued = ledger.get(record.action_id)
    assert queued.status == ActionStatus.QUEUED
    assert queued.result is not None
    assert queued.result["external_effect"] == "not_executed"
