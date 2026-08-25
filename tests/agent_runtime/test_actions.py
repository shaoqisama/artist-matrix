from __future__ import annotations

import time
from datetime import timedelta
from multiprocessing import get_context
from pathlib import Path

import pytest
from pydantic import ValidationError

from artist_matrix.agent_runtime.actions import (
    ActionConflictError,
    ActionExecutor,
    ActionKind,
    ActionLedger,
    ActionStatus,
    ActionStore,
    InvalidActionTransition,
    StaleRunningPolicy,
)
from artist_matrix.state import ArtistMatrixSettings


def _profile_payload(name: str = "Neon Wasteland") -> dict[str, object]:
    return {
        "name": name,
        "persona_tags": ["retro"],
        "lyric_style": "synthwave stories",
        "visual_style": "neon glitch",
        "influences": ["Kavinsky"],
    }


def _approve_render_in_process(
    data_root: str,
    action_root: str,
    action_id: str,
    start_event,  # noqa: ANN001 - multiprocessing proxy types are platform-specific
    ready_queue,  # noqa: ANN001
    result_queue,  # noqa: ANN001
) -> None:
    """Compete for one action from an independent process and store instance."""

    settings = ArtistMatrixSettings(data_root=Path(data_root))
    store = ActionStore(Path(action_root))

    def provider_handler(action, handler_settings, context):  # noqa: ANN001
        call_log = handler_settings.data_root / "provider-calls.log"
        with call_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{context.idempotency_key}\n")
            handle.flush()
        time.sleep(0.1)
        return {"provider_job_id": f"job-{action.action_id}"}

    ready_queue.put("ready")
    if not start_event.wait(timeout=10):
        result_queue.put(("error", "start timeout"))
        return
    try:
        result = ActionExecutor(
            settings,
            handlers={ActionKind.RENDER_TRACK: provider_handler},
        ).approve(store, action_id)
        result_queue.put(("ok", result.status.value))
    except Exception as exc:  # noqa: BLE001 - serialize worker failure for the parent test
        result_queue.put(("error", repr(exc)))


def test_action_ledger_persists_one_atomic_json_record(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path)
    ledger = ActionLedger(settings)

    record = ledger.propose(
        ActionKind.SAVE_PERSONA,
        {"profile": _profile_payload()},
    )

    expected = tmp_path / "actions" / f"{record.action_id}.json"
    assert expected.exists()
    assert ledger.get(record.action_id) == record
    assert not list(expected.parent.glob("*.tmp"))


def test_save_persona_requires_approval_and_reapproval_is_idempotent(
    tmp_path: Path,
) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))
    record = ledger.propose(
        ActionKind.SAVE_PERSONA,
        {"profile": _profile_payload()},
    )
    manifest = tmp_path / "artists" / "neon-wasteland.json"
    assert not manifest.exists()

    executor = ActionExecutor(ledger)
    completed = executor.approve_and_execute(record.action_id)
    repeated = executor.approve_and_execute(record.action_id)

    assert manifest.exists()
    assert completed.status == ActionStatus.COMPLETED
    assert completed.attempts == 1
    assert repeated == completed
    assert repeated.result is not None
    assert repeated.result["manifest_path"] == str(manifest)


def test_unconfigured_external_action_is_queued_in_settings_derived_outbox(
    tmp_path: Path,
) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))
    record = ledger.propose(
        ActionKind.DISPATCH_RELEASE,
        {
            "artist_slug": "neon-wasteland",
            "title": "Signal Burn",
            "release_date": "2100-01-04",
            "platforms": ["spotify"],
            "track_slug": "signal-burn",
        },
    )

    queued = ActionExecutor(ledger).approve_and_execute(record.action_id)

    expected = tmp_path / "outbox" / "dispatch_release" / f"{record.action_id}.json"
    assert queued.status == ActionStatus.QUEUED
    assert expected.exists()
    assert queued.result == {
        "mode": "outbox",
        "external_effect": "not_executed",
        "outbox_path": str(expected),
        "idempotency_key": str(record.action_id),
    }
    assert ActionExecutor(ledger).approve_and_execute(record.action_id) == queued
    assert "neon-wasteland" in expected.read_text(encoding="utf-8")


def test_failed_handler_is_persisted_and_can_be_retried(tmp_path: Path) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))
    record = ledger.propose(
        ActionKind.RENDER_TRACK,
        {
            "artist_slug": "neon-wasteland",
            "draft": {
                "persona_slug": "neon-wasteland",
                "title": "Signal Burn",
                "tags": ["neon"],
                "lyrics": "Verse line",
            },
        },
    )
    calls = 0

    idempotency_keys: list[str] = []

    def flaky_handler(action, settings, context):  # noqa: ANN001
        nonlocal calls
        calls += 1
        idempotency_keys.append(context.idempotency_key)
        assert context.action_id == action.action_id
        assert context.attempt == calls
        if calls == 1:
            raise RuntimeError("provider unavailable")
        return {"provider_job_id": "job-001"}

    executor = ActionExecutor(
        ledger,
        handlers={ActionKind.RENDER_TRACK: flaky_handler},
    )

    failed = executor.approve_and_execute(record.action_id)
    completed = executor.approve_and_execute(record.action_id)

    assert failed.status == ActionStatus.FAILED
    assert failed.error == "provider unavailable"
    assert completed.status == ActionStatus.COMPLETED
    assert completed.attempts == 2
    assert completed.result == {
        "provider_job_id": "job-001",
        "idempotency_key": str(record.action_id),
    }
    assert idempotency_keys == [str(record.action_id), str(record.action_id)]


def test_rejected_action_cannot_execute(tmp_path: Path) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))
    record = ledger.propose(
        ActionKind.SCHEDULE_CAMPAIGN,
        {
            "artist_slug": "neon-wasteland",
            "title": "Launch",
            "platform": "echo",
            "beats": ["Teaser"],
        },
    )
    executor = ActionExecutor(ledger)

    rejected = executor.reject(record.action_id, reason="User declined")

    assert rejected.status == ActionStatus.REJECTED
    with pytest.raises(InvalidActionTransition, match="rejected"):
        executor.approve_and_execute(record.action_id)


def test_stable_store_and_executor_api(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path)
    store = ActionStore(settings.resolved_action_root)
    record = store.propose(
        ActionKind.SCHEDULE_CAMPAIGN,
        {
            "artist_slug": "neon-wasteland",
            "title": "Launch",
            "platform": "echo",
            "beats": ["Teaser"],
        },
    )

    queued = ActionExecutor(settings).approve(store, record.action_id)

    assert store.get(record.action_id) == queued
    assert store.list(ActionStatus.QUEUED) == (queued,)


def test_revision_compare_and_swap_rejects_stale_transition(tmp_path: Path) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))
    record = ledger.propose(
        ActionKind.SAVE_PERSONA,
        {"profile": _profile_payload()},
    )

    running = ledger.mark_running(record.action_id, expected_revision=record.revision)

    with pytest.raises(ActionConflictError, match="revision changed"):
        ledger.mark_failed(
            record.action_id,
            "late failure",
            expected_revision=record.revision,
        )
    assert ledger.get(record.action_id) == running


def test_stale_running_is_failed_for_reconciliation_before_explicit_retry(
    tmp_path: Path,
) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))
    record = ledger.propose(
        ActionKind.RENDER_TRACK,
        {
            "artist_slug": "neon-wasteland",
            "draft": {
                "persona_slug": "neon-wasteland",
                "title": "Signal Burn",
                "tags": ["neon"],
                "lyrics": "Verse line",
            },
        },
    )
    ledger.mark_running(record.action_id)
    calls = 0

    def provider_handler(action, settings, context):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return {"provider_job_id": context.idempotency_key}

    executor = ActionExecutor(
        ledger,
        handlers={ActionKind.RENDER_TRACK: provider_handler},
        stale_running_after=timedelta(0),
    )

    recovered = executor.approve_and_execute(record.action_id)
    completed = executor.approve_and_execute(record.action_id)

    assert recovered.status == ActionStatus.FAILED
    assert "external outcome is unknown" in (recovered.error or "")
    assert str(record.action_id) in (recovered.error or "")
    assert completed.status == ActionStatus.COMPLETED
    assert completed.attempts == 2
    assert calls == 1


def test_stale_running_retry_policy_reuses_provider_idempotency_key(tmp_path: Path) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))
    record = ledger.propose(
        ActionKind.RENDER_TRACK,
        {
            "artist_slug": "neon-wasteland",
            "draft": {
                "persona_slug": "neon-wasteland",
                "title": "Signal Burn",
                "tags": ["neon"],
                "lyrics": "Verse line",
            },
        },
    )
    ledger.mark_running(record.action_id)
    observed_keys: list[str] = []

    def provider_handler(action, settings, context):  # noqa: ANN001
        observed_keys.append(context.idempotency_key)
        return {"provider_job_id": "reconciled-job"}

    completed = ActionExecutor(
        ledger,
        handlers={ActionKind.RENDER_TRACK: provider_handler},
        stale_running_after=timedelta(0),
        stale_running_policy=StaleRunningPolicy.RETRY,
    ).approve_and_execute(record.action_id)

    assert completed.status == ActionStatus.COMPLETED
    assert completed.attempts == 2
    assert observed_keys == [str(record.action_id)]


def test_independent_processes_execute_one_provider_call(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path)
    ledger = ActionLedger(settings)
    record = ledger.propose(
        ActionKind.RENDER_TRACK,
        {
            "artist_slug": "neon-wasteland",
            "draft": {
                "persona_slug": "neon-wasteland",
                "title": "Signal Burn",
                "tags": ["neon"],
                "lyrics": "Verse line",
            },
        },
    )
    context = get_context("spawn")
    start_event = context.Event()
    ready_queue = context.Queue()
    result_queue = context.Queue()
    args = (
        str(tmp_path),
        str(settings.resolved_action_root),
        str(record.action_id),
        start_event,
        ready_queue,
        result_queue,
    )
    processes = [context.Process(target=_approve_render_in_process, args=args) for _ in range(2)]
    for process in processes:
        process.start()
    try:
        assert [ready_queue.get(timeout=15) for _ in processes] == ["ready", "ready"]
        start_event.set()
        for process in processes:
            process.join(timeout=15)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)

    assert [process.exitcode for process in processes] == [0, 0]
    assert sorted(result_queue.get(timeout=5) for _ in processes) == [
        ("ok", ActionStatus.COMPLETED.value),
        ("ok", ActionStatus.COMPLETED.value),
    ]
    assert (tmp_path / "provider-calls.log").read_text(encoding="utf-8").splitlines() == [
        str(record.action_id)
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"artist_slug": "../escape", "draft": {"persona_slug": "../escape"}},
        {
            "artist_slug": "neon-wasteland",
            "draft": {
                "persona_slug": "neon-wasteland",
                "manifest_path": "/tmp/injected.json",
            },
        },
    ],
)
def test_model_cannot_supply_paths_or_unsafe_slugs(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))

    with pytest.raises((ValidationError, ValueError)):
        ledger.propose(ActionKind.RENDER_TRACK, payload)


def test_render_proposal_requires_a_finalization_ready_draft(tmp_path: Path) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))

    with pytest.raises(ValidationError, match="lyrics or a style with production notes"):
        ledger.propose(
            ActionKind.RENDER_TRACK,
            {
                "artist_slug": "neon-wasteland",
                "draft": {
                    "persona_slug": "neon-wasteland",
                    "title": "Signal Burn",
                    "tags": ["neon"],
                },
            },
        )


def test_non_instrumental_render_requires_lyrics(tmp_path: Path) -> None:
    ledger = ActionLedger(ArtistMatrixSettings(data_root=tmp_path))

    with pytest.raises(ValidationError, match="non-instrumental render draft requires lyrics"):
        ledger.propose(
            ActionKind.RENDER_TRACK,
            {
                "artist_slug": "neon-wasteland",
                "draft": {
                    "persona_slug": "neon-wasteland",
                    "title": "Signal Burn",
                    "style": "synthwave",
                    "tags": ["neon"],
                    "notes": ["keep vocals airy"],
                    "allow_instrumental": False,
                },
            },
        )
