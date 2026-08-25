from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from artist_matrix.agent_runtime.definitions import AgentRole
from artist_matrix.agent_runtime.threads import ThreadStore


def test_thread_store_binds_rebinds_and_reloads_a_scope(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "threads.json"
    store = ThreadStore(path)

    first = store.bind(AgentRole.soul_forge, "neon-wasteland", "thread-001")
    rebound = store.bind(AgentRole.soul_forge, "neon-wasteland", "thread-002")

    assert rebound.thread_id == "thread-002"
    assert rebound.created_at == first.created_at
    assert rebound.updated_at >= first.updated_at
    assert ThreadStore(path).get(AgentRole.soul_forge, "neon-wasteland") == rebound
    assert ThreadStore(path).list() == (rebound,)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == ThreadStore.schema_version
    assert set(payload["bindings"]) == {"soul_forge:neon-wasteland"}
    assert not path.with_suffix(".json.tmp").exists()


def test_thread_store_keeps_roles_and_scopes_isolated(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    store.bind(AgentRole.soul_forge, "neon-wasteland", "thread-soul")
    store.bind(AgentRole.creation_engine, "neon-wasteland", "thread-creation")
    store.bind(AgentRole.soul_forge, "void-signal", "thread-void")

    assert store.get(AgentRole.soul_forge, "neon-wasteland").thread_id == "thread-soul"  # type: ignore[union-attr]
    assert (
        store.get(AgentRole.creation_engine, "neon-wasteland").thread_id  # type: ignore[union-attr]
        == "thread-creation"
    )
    assert store.get(AgentRole.soul_forge, "void-signal").thread_id == "thread-void"  # type: ignore[union-attr]


def test_thread_store_keeps_runtime_namespaces_isolated(tmp_path: Path) -> None:
    path = tmp_path / "threads.json"
    first = ThreadStore(path, namespace="runtime-a")
    second = ThreadStore(path, namespace="runtime-b")

    first.bind(AgentRole.director, "global", "thread-a")
    second.bind(AgentRole.director, "global", "thread-b")

    assert first.get(AgentRole.director, "global").thread_id == "thread-a"  # type: ignore[union-attr]
    assert second.get(AgentRole.director, "global").thread_id == "thread-b"  # type: ignore[union-attr]
    assert [item.thread_id for item in first.list()] == ["thread-a"]
    assert [item.thread_id for item in second.list()] == ["thread-b"]


def test_thread_store_cross_instance_updates_do_not_overwrite_each_other(
    tmp_path: Path,
) -> None:
    path = tmp_path / "threads.json"

    def bind_many(prefix: str, role: AgentRole) -> None:
        store = ThreadStore(path)
        for index in range(20):
            scope = f"{prefix}-{index}"
            store.bind(role, scope, f"thread-{scope}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bind_many, "soul", AgentRole.soul_forge)
        second = pool.submit(bind_many, "track", AgentRole.creation_engine)
        first.result()
        second.result()

    assert len(ThreadStore(path).list()) == 40


def test_thread_store_forget_is_idempotent(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path / "threads.json")
    store.bind(AgentRole.world_stage, "signal-burn", "thread-release")

    assert store.forget(AgentRole.world_stage, "signal-burn") is True
    assert store.forget(AgentRole.world_stage, "signal-burn") is False
    assert store.get(AgentRole.world_stage, "signal-burn") is None
    assert store.list() == ()


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        json.dumps({"schema_version": 999, "bindings": {}}),
        json.dumps({"schema_version": 1, "bindings": []}),
    ],
)
def test_thread_store_fails_closed_for_corrupt_or_unsupported_data(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "threads.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(RuntimeError, match="thread registry"):
        ThreadStore(path).list()
