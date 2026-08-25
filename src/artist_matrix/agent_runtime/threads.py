"""Durable mapping between product scopes and Codex thread identifiers."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from artist_matrix.agent_runtime.definitions import AgentRole
from artist_matrix.agent_runtime.locking import exclusive_file_lock


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ThreadBinding(BaseModel):
    """A resumable harness thread bound to a product scope."""

    model_config = ConfigDict(frozen=True)

    role: AgentRole
    scope: str
    thread_id: str
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @property
    def key(self) -> str:
        return f"{self.role.value}:{self.scope}"


class ThreadStore:
    """Persist thread bindings atomically without treating thread history as canonical state."""

    schema_version = 1

    def __init__(self, path: Path, *, namespace: str = "") -> None:
        self.path = path
        self.namespace = namespace.strip()
        self._lock = RLock()

    def get(self, role: AgentRole, scope: str) -> ThreadBinding | None:
        with self._registry_lock():
            raw = self._load().get(self._key(role, scope))
        return ThreadBinding.model_validate(raw) if raw is not None else None

    def bind(self, role: AgentRole, scope: str, thread_id: str) -> ThreadBinding:
        with self._registry_lock():
            records = self._load()
            key = self._key(role, scope)
            previous = records.get(key)
            created_at = previous.get("created_at") if isinstance(previous, dict) else _now()
            binding = ThreadBinding.model_validate(
                {
                    "role": role,
                    "scope": scope,
                    "thread_id": thread_id,
                    "created_at": created_at,
                    "updated_at": _now(),
                }
            )
            records[key] = binding.model_dump(mode="json")
            self._save(records)
        return binding

    def forget(self, role: AgentRole, scope: str) -> bool:
        with self._registry_lock():
            records = self._load()
            removed = records.pop(self._key(role, scope), None) is not None
            if removed:
                self._save(records)
        return removed

    def list(self) -> tuple[ThreadBinding, ...]:
        with self._registry_lock():
            records = self._load()
        bindings = [
            ThreadBinding.model_validate(value)
            for key, value in records.items()
            if self._in_namespace(key)
        ]
        return tuple(sorted(bindings, key=lambda item: item.updated_at, reverse=True))

    @contextmanager
    def scope_lock(self, role: AgentRole, scope: str) -> Iterator[None]:
        """Serialize one role/scope turn across threads and processes."""

        digest = sha256(self._key(role, scope).encode("utf-8")).hexdigest()
        lock_path = self.path.parent / ".thread-scope-locks" / f"{digest}.lock"
        with exclusive_file_lock(lock_path):
            yield

    def _key(self, role: AgentRole, scope: str) -> str:
        key = f"{role.value}:{scope.strip() or 'global'}"
        return f"{self.namespace}|{key}" if self.namespace else key

    def _in_namespace(self, key: str) -> bool:
        if not self.namespace:
            return "|" not in key
        return key.startswith(f"{self.namespace}|")

    @contextmanager
    def _registry_lock(self) -> Iterator[None]:
        lock_path = self.path.parent / f".{self.path.name}.lock"
        with self._lock, exclusive_file_lock(lock_path):
            yield

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Cannot read thread registry: {self.path}") from exc
        if payload.get("schema_version") != self.schema_version:
            raise RuntimeError(f"Unsupported thread registry version in {self.path}")
        bindings = payload.get("bindings", {})
        if not isinstance(bindings, dict):
            raise RuntimeError(f"Invalid thread registry in {self.path}")
        return {str(key): value for key, value in bindings.items() if isinstance(value, dict)}

    def _save(self, records: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = {"schema_version": self.schema_version, "bindings": records}
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)


__all__ = ["ThreadBinding", "ThreadStore"]
