"""Approval-gated action records for Codex-driven Artist Matrix workflows.

The agent may propose actions and inspect their state.  Only application code
holding an :class:`ActionExecutor` can approve and execute an action.  This
keeps charged or externally visible operations out of the model tool surface.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Iterator, Literal, TypeAlias, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from artist_matrix.agent_runtime.locking import exclusive_file_lock
from artist_matrix.creation_engine.ideation import TrackIdeationDraft
from artist_matrix.soul_forge.profiles import ArtistProfile
from artist_matrix.soul_forge.service import ArtistProfileRepository
from artist_matrix.state.settings import ArtistMatrixSettings

logger = logging.getLogger(__name__)

_SAFE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ActionKind(str, Enum):
    """Consequential operations an agent can propose."""

    SAVE_PERSONA = "save_persona"
    RENDER_TRACK = "render_track"
    SCHEDULE_CAMPAIGN = "schedule_campaign"
    DISPATCH_RELEASE = "dispatch_release"


class ActionStatus(str, Enum):
    """Lifecycle states persisted in the action ledger."""

    PENDING = "pending"
    RUNNING = "running"
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class StaleRunningPolicy(str, Enum):
    """How approval handles an action abandoned in ``running`` state."""

    FAIL = "fail"
    RETRY = "retry"


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ArtistScopedPayload(_StrictPayload):
    artist_slug: str

    @field_validator("artist_slug")
    @classmethod
    def validate_artist_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SAFE_SLUG.fullmatch(value):
            raise ValueError("artist_slug must be a simple lowercase slug")
        return value


class SavePersonaPayload(_StrictPayload):
    """A validated profile to persist after application approval."""

    profile: ArtistProfile


class RenderTrackPayload(_ArtistScopedPayload):
    """The accepted draft to submit to the production boundary."""

    draft: TrackIdeationDraft

    @model_validator(mode="after")
    def validate_persona_matches(self) -> RenderTrackPayload:
        if self.draft.persona_slug != self.artist_slug:
            raise ValueError("draft persona_slug must match artist_slug")
        if not (self.draft.title and self.draft.title.strip()):
            raise ValueError("render draft requires a title")
        if not any(str(tag).strip() for tag in self.draft.tags):
            raise ValueError("render draft requires at least one tag")
        has_lyrics = bool(self.draft.lyrics and self.draft.lyrics.strip())
        if not self.draft.allow_instrumental and not has_lyrics:
            raise ValueError("non-instrumental render draft requires lyrics")
        has_style_and_notes = bool(
            self.draft.style
            and self.draft.style.strip()
            and any(str(note).strip() for note in self.draft.notes)
        )
        if not has_lyrics and not has_style_and_notes:
            raise ValueError("render draft requires lyrics or a style with production notes")
        return self


class ScheduleCampaignPayload(_ArtistScopedPayload):
    """A campaign plan that may be scheduled after approval."""

    title: str
    platform: str
    beats: tuple[str, ...]
    cadence_minutes: int = Field(default=120, gt=0)

    @field_validator("title", "platform")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("beats")
    @classmethod
    def validate_beats(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(beat.strip() for beat in value if beat.strip())
        if not cleaned:
            raise ValueError("beats must include at least one entry")
        return cleaned


class DispatchReleasePayload(_ArtistScopedPayload):
    """Release metadata using slugs rather than model-provided file paths."""

    title: str
    release_date: date
    platforms: tuple[str, ...]
    track_slug: str
    description: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(platform.strip() for platform in value if platform.strip())
        if not cleaned:
            raise ValueError("platforms must include at least one entry")
        return cleaned

    @field_validator("track_slug")
    @classmethod
    def validate_track_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SAFE_SLUG.fullmatch(value):
            raise ValueError("track_slug must be a simple lowercase slug")
        return value


ActionPayload: TypeAlias = (
    SavePersonaPayload | RenderTrackPayload | ScheduleCampaignPayload | DispatchReleasePayload
)

_PAYLOAD_TYPES: dict[ActionKind, type[ActionPayload]] = {
    ActionKind.SAVE_PERSONA: SavePersonaPayload,
    ActionKind.RENDER_TRACK: RenderTrackPayload,
    ActionKind.SCHEDULE_CAMPAIGN: ScheduleCampaignPayload,
    ActionKind.DISPATCH_RELEASE: DispatchReleasePayload,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reject_model_paths(value: object) -> None:
    """Reject path-like fields in a model proposal, including nested fields."""

    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            if key == "path" or key.endswith(("_path", "_dir", "_root")):
                raise ValueError(f"model-supplied paths are not allowed: {raw_key}")
            _reject_model_paths(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _reject_model_paths(child)


def _parse_payload(kind: ActionKind, value: object) -> ActionPayload:
    if isinstance(value, BaseModel):
        raw_value: object = value.model_dump(mode="python")
    else:
        raw_value = value
    _reject_model_paths(raw_value)
    return _PAYLOAD_TYPES[kind].model_validate(raw_value)


class ActionRecord(BaseModel):
    """Durable record for a proposed and possibly executed action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    action_id: UUID = Field(default_factory=uuid4)
    kind: ActionKind
    status: ActionStatus = ActionStatus.PENDING
    revision: int = Field(default=0, ge=0)
    payload: ActionPayload
    requested_by: str = "codex"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    approved_at: datetime | None = None
    queued_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int = Field(default=0, ge=0)
    result: dict[str, Any] | None = None
    error: str | None = None
    rejection_reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def parse_kind_specific_payload(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        raw = dict(value)
        if "kind" not in raw or "payload" not in raw:
            return raw
        kind = ActionKind(raw["kind"])
        raw["payload"] = _parse_payload(kind, raw["payload"])
        return raw

    @model_validator(mode="after")
    def validate_payload_kind(self) -> ActionRecord:
        expected = _PAYLOAD_TYPES[self.kind]
        if not isinstance(self.payload, expected):
            raise ValueError(f"payload does not match action kind {self.kind.value}")
        return self


class ActionNotFoundError(LookupError):
    """Raised when an action ID is absent from the ledger."""


class InvalidActionTransition(RuntimeError):
    """Raised when application code attempts an invalid lifecycle transition."""


class ActionConflictError(InvalidActionTransition):
    """Raised when a compare-and-swap transition observes a stale revision."""


def _action_uuid(action_id: UUID | str) -> UUID:
    try:
        return action_id if isinstance(action_id, UUID) else UUID(str(action_id))
    except ValueError as exc:
        raise ActionNotFoundError(f"Invalid action ID: {action_id}") from exc


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


class ActionStore:
    """Atomic JSON action store rooted at an application-selected directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = RLock()
        self._action_locks: dict[UUID, RLock] = {}

    def _path(self, action_id: UUID | str) -> Path:
        safe_id = _action_uuid(action_id)
        return self.root / f"{safe_id}.json"

    def propose(
        self,
        kind: ActionKind | str,
        payload: ActionPayload | Mapping[str, object],
        *,
        requested_by: str = "codex",
    ) -> ActionRecord:
        parsed_kind = ActionKind(kind)
        parsed_payload = _parse_payload(parsed_kind, payload)
        record = ActionRecord(
            kind=parsed_kind,
            payload=parsed_payload,
            requested_by=requested_by.strip() or "codex",
        )
        with self._lock:
            self._write(record)
            # Return the persisted representation so callers observe the same
            # canonical list/tuple and datetime forms as subsequent reads.
            return self.get(record.action_id)

    def get(self, action_id: UUID | str) -> ActionRecord:
        path = self._path(action_id)
        with self._lock:
            try:
                raw = path.read_text(encoding="utf-8")
            except FileNotFoundError as exc:
                raise ActionNotFoundError(f"Action not found: {action_id}") from exc
        return ActionRecord.model_validate_json(raw)

    def list_actions(
        self,
        *,
        kind: ActionKind | str | None = None,
        status: ActionStatus | str | None = None,
    ) -> tuple[ActionRecord, ...]:
        parsed_kind = ActionKind(kind) if kind is not None else None
        parsed_status = ActionStatus(status) if status is not None else None
        records: list[ActionRecord] = []
        with self._lock:
            paths = tuple(self.root.glob("*.json")) if self.root.exists() else ()
            for path in paths:
                try:
                    record = ActionRecord.model_validate_json(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    logger.warning(
                        "Skipping invalid action record",
                        extra={"path": str(path), "error": str(exc)},
                    )
                    continue
                if parsed_kind is not None and record.kind != parsed_kind:
                    continue
                if parsed_status is not None and record.status != parsed_status:
                    continue
                records.append(record)
        records.sort(key=lambda record: (record.created_at, str(record.action_id)), reverse=True)
        return tuple(records)

    def list(
        self,
        status: ActionStatus | str | None = None,
        *,
        kind: ActionKind | str | None = None,
    ) -> tuple[ActionRecord, ...]:
        """Stable CLI-facing alias for listing ledger records."""

        return self.list_actions(kind=kind, status=status)

    def reject(
        self,
        action_id: UUID | str,
        reason: str = "Rejected by application",
    ) -> ActionRecord:
        """Reject a proposed action without exposing execution to the model."""

        return self.mark_rejected(action_id, reason)

    def mark_running(
        self,
        action_id: UUID | str,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        with self._action_lock(action_id):
            return self._mark_running_locked(action_id, expected_revision=expected_revision)

    def mark_completed(
        self,
        action_id: UUID | str,
        result: Mapping[str, object] | None = None,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        with self._action_lock(action_id):
            return self._mark_completed_locked(
                action_id,
                result,
                expected_revision=expected_revision,
            )

    def mark_queued(
        self,
        action_id: UUID | str,
        result: Mapping[str, object],
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        """Record that the host queued work without claiming an external effect."""

        with self._action_lock(action_id):
            return self._mark_queued_locked(
                action_id,
                result,
                expected_revision=expected_revision,
            )

    def mark_failed(
        self,
        action_id: UUID | str,
        error: str,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        with self._action_lock(action_id):
            return self._mark_failed_locked(
                action_id,
                error,
                expected_revision=expected_revision,
            )

    def mark_rejected(
        self,
        action_id: UUID | str,
        reason: str,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        with self._action_lock(action_id):
            return self._mark_rejected_locked(
                action_id,
                reason,
                expected_revision=expected_revision,
            )

    @contextmanager
    def _action_lock(self, action_id: UUID | str) -> Iterator[UUID]:
        """Serialize one action across store instances and operating-system processes.

        Lock files are intentionally retained. Removing a lock file while another process
        is waiting on its inode would create a second lock domain and break mutual exclusion.
        """

        safe_id = _action_uuid(action_id)
        with self._lock:
            thread_lock = self._action_locks.setdefault(safe_id, RLock())
        with thread_lock:
            lock_path = self.root / ".locks" / f"{safe_id}.lock"
            with exclusive_file_lock(lock_path):
                yield safe_id

    def _mark_running_locked(
        self,
        action_id: UUID | str,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        current = self.get(action_id)
        self._check_revision(current, expected_revision)
        if current.status not in {
            ActionStatus.PENDING,
            ActionStatus.FAILED,
            ActionStatus.QUEUED,
        }:
            raise InvalidActionTransition(
                f"Cannot run {current.action_id} from {current.status.value}"
            )
        now = _now()
        updated = current.model_copy(
            update={
                "status": ActionStatus.RUNNING,
                "revision": current.revision + 1,
                "updated_at": now,
                "approved_at": current.approved_at or now,
                "queued_at": None,
                "completed_at": None,
                "attempts": current.attempts + 1,
                "result": None,
                "error": None,
            }
        )
        self._write(updated)
        return updated

    def _mark_completed_locked(
        self,
        action_id: UUID | str,
        result: Mapping[str, object] | None = None,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        current = self.get(action_id)
        self._check_revision(current, expected_revision)
        if current.status != ActionStatus.RUNNING:
            raise InvalidActionTransition(
                f"Cannot complete {current.action_id} from {current.status.value}"
            )
        now = _now()
        updated = current.model_copy(
            update={
                "status": ActionStatus.COMPLETED,
                "revision": current.revision + 1,
                "updated_at": now,
                "queued_at": None,
                "completed_at": now,
                "result": dict(result or {}),
                "error": None,
            }
        )
        self._write(updated)
        return updated

    def _mark_queued_locked(
        self,
        action_id: UUID | str,
        result: Mapping[str, object],
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        current = self.get(action_id)
        self._check_revision(current, expected_revision)
        if current.status != ActionStatus.RUNNING:
            raise InvalidActionTransition(
                f"Cannot queue {current.action_id} from {current.status.value}"
            )
        now = _now()
        updated = current.model_copy(
            update={
                "status": ActionStatus.QUEUED,
                "revision": current.revision + 1,
                "updated_at": now,
                "queued_at": now,
                "completed_at": None,
                "result": dict(result),
                "error": None,
            }
        )
        self._write(updated)
        return updated

    def _mark_failed_locked(
        self,
        action_id: UUID | str,
        error: str,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        current = self.get(action_id)
        self._check_revision(current, expected_revision)
        if current.status != ActionStatus.RUNNING:
            raise InvalidActionTransition(
                f"Cannot fail {current.action_id} from {current.status.value}"
            )
        now = _now()
        updated = current.model_copy(
            update={
                "status": ActionStatus.FAILED,
                "revision": current.revision + 1,
                "updated_at": now,
                "queued_at": None,
                "completed_at": now,
                "error": error.strip() or "Action execution failed",
                "result": None,
            }
        )
        self._write(updated)
        return updated

    def _mark_rejected_locked(
        self,
        action_id: UUID | str,
        reason: str,
        *,
        expected_revision: int | None = None,
    ) -> ActionRecord:
        current = self.get(action_id)
        self._check_revision(current, expected_revision)
        if current.status == ActionStatus.REJECTED:
            return current
        if current.status not in {ActionStatus.PENDING, ActionStatus.FAILED}:
            raise InvalidActionTransition(
                f"Cannot reject {current.action_id} from {current.status.value}"
            )
        now = _now()
        updated = current.model_copy(
            update={
                "status": ActionStatus.REJECTED,
                "revision": current.revision + 1,
                "updated_at": now,
                "completed_at": now,
                "rejection_reason": reason.strip() or "Rejected by application",
            }
        )
        self._write(updated)
        return updated

    def _check_revision(self, current: ActionRecord, expected_revision: int | None) -> None:
        if expected_revision is not None and current.revision != expected_revision:
            raise ActionConflictError(
                f"Action {current.action_id} revision changed from "
                f"{expected_revision} to {current.revision}"
            )

    def _write(self, record: ActionRecord) -> None:
        _atomic_write_json(self._path(record.action_id), record.model_dump(mode="json"))


class ActionLedger(ActionStore):
    """Settings-backed compatibility wrapper around :class:`ActionStore`."""

    def __init__(self, settings: ArtistMatrixSettings) -> None:
        self.settings = settings
        super().__init__(settings.resolved_action_root)


class ActionExecutionContext(BaseModel):
    """Host-owned execution metadata passed to every consequential adapter.

    Provider handlers must send ``idempotency_key`` as the provider request's
    idempotency key. It is stable across retries because it is the action UUID.
    """

    model_config = ConfigDict(frozen=True)

    action_id: UUID
    idempotency_key: str
    attempt: int = Field(ge=1)


class OutboxReceipt(BaseModel):
    """Receipt proving local enqueue only, never an external side effect."""

    model_config = ConfigDict(frozen=True)

    mode: Literal["outbox"] = "outbox"
    external_effect: Literal["not_executed"] = "not_executed"
    outbox_path: str
    idempotency_key: str


ActionHandler: TypeAlias = Callable[
    [ActionRecord, ArtistMatrixSettings, ActionExecutionContext], object
]


def _json_safe(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class LocalOutboxAdapter:
    """Safe default for actions whose external service is not configured."""

    def __init__(self, settings: ArtistMatrixSettings) -> None:
        self.settings = settings
        self.root = settings.data_root / "outbox"

    def execute(self, action: ActionRecord) -> OutboxReceipt:
        target = self.root / action.kind.value / f"{action.action_id}.json"
        envelope: dict[str, object] = {
            "action": action.model_dump(mode="json"),
            "idempotency_key": str(action.action_id),
            "queued_at": _now().isoformat(),
        }
        if action.kind == ActionKind.DISPATCH_RELEASE:
            payload = cast(DispatchReleasePayload, action.payload)
            track_manifest = (
                self.settings.data_root
                / "artists"
                / payload.artist_slug
                / "tracks"
                / f"{payload.track_slug}.json"
            )
            envelope["derived_track_manifest"] = str(track_manifest)
        _atomic_write_json(target, envelope)
        return OutboxReceipt(
            outbox_path=str(target),
            idempotency_key=str(action.action_id),
        )


_DEFAULT_STALE_RUNNING_AFTER = timedelta(minutes=15)


class ActionExecutor:
    """Application-only approval and execution boundary.

    The executor is deliberately not registered by the MCP surface.  Handlers
    can call deterministic domain services; unconfigured actions are written
    to a local outbox rooted under ``ArtistMatrixSettings.data_root``.
    """

    def __init__(
        self,
        settings_or_store: ArtistMatrixSettings | ActionStore,
        *,
        handlers: Mapping[ActionKind, ActionHandler] | None = None,
        outbox: LocalOutboxAdapter | None = None,
        stale_running_after: timedelta | None = _DEFAULT_STALE_RUNNING_AFTER,
        stale_running_policy: StaleRunningPolicy | str = StaleRunningPolicy.FAIL,
    ) -> None:
        if isinstance(settings_or_store, ArtistMatrixSettings):
            self.settings = settings_or_store
            self.store: ActionStore | None = None
        else:
            self.store = settings_or_store
            settings = getattr(settings_or_store, "settings", None)
            if not isinstance(settings, ArtistMatrixSettings):
                raise TypeError(
                    "ActionExecutor(ActionStore) requires a settings-backed ActionLedger; "
                    "use ActionExecutor(settings).approve(store, action_id) instead"
                )
            self.settings = settings
        self.handlers = dict(handlers or {})
        self.outbox = outbox or LocalOutboxAdapter(self.settings)
        if stale_running_after is not None and stale_running_after.total_seconds() < 0:
            raise ValueError("stale_running_after must not be negative")
        self.stale_running_after = stale_running_after
        self.stale_running_policy = StaleRunningPolicy(stale_running_policy)
        self._lock = RLock()

    def approve_and_execute(self, action_id: UUID | str) -> ActionRecord:
        if self.store is None:
            raise TypeError("No default ActionStore; call approve(store, action_id)")
        return self.approve(self.store, action_id)

    def approve(self, store: ActionStore, action_id: UUID | str) -> ActionRecord:
        """Approve and execute one record from ``store``.

        Re-approving a completed action returns the persisted completion
        unchanged, making UI retries idempotent.
        """

        with self._lock, store._action_lock(action_id):
            current = store.get(action_id)
            if current.status in {ActionStatus.COMPLETED, ActionStatus.QUEUED}:
                return current
            if current.status == ActionStatus.REJECTED:
                raise InvalidActionTransition(f"Action {current.action_id} was rejected")
            if current.status == ActionStatus.RUNNING:
                current = self._recover_stale_running(store, current)
                if self.stale_running_policy == StaleRunningPolicy.FAIL:
                    return current

            running = store._mark_running_locked(
                current.action_id,
                expected_revision=current.revision,
            )
            context = ActionExecutionContext(
                action_id=running.action_id,
                idempotency_key=str(running.action_id),
                attempt=running.attempts,
            )
            try:
                raw_result = self._execute(running, context)
                is_outbox = isinstance(raw_result, OutboxReceipt)
                safe_result = _json_safe(raw_result)
                if not isinstance(safe_result, Mapping):
                    safe_result = {"value": safe_result}
                result = dict(safe_result)
                result.setdefault("idempotency_key", context.idempotency_key)
            except Exception as exc:  # noqa: BLE001 - persist the failed action for inspection
                logger.exception(
                    "Approved action execution failed",
                    extra={"action_id": str(running.action_id), "kind": running.kind.value},
                )
                return store._mark_failed_locked(
                    running.action_id,
                    str(exc),
                    expected_revision=running.revision,
                )

            if is_outbox:
                return store._mark_queued_locked(
                    running.action_id,
                    result,
                    expected_revision=running.revision,
                )
            return store._mark_completed_locked(
                running.action_id,
                result,
                expected_revision=running.revision,
            )

    def reject(self, action_id: UUID | str, *, reason: str) -> ActionRecord:
        if self.store is None:
            raise TypeError("No default ActionStore; call store.reject(action_id, reason)")
        return self.store.reject(action_id, reason)

    def _recover_stale_running(
        self,
        store: ActionStore,
        current: ActionRecord,
    ) -> ActionRecord:
        stale_after = self.stale_running_after
        updated_at = current.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        is_stale = stale_after is not None and _now() - updated_at >= stale_after
        if not is_stale:
            raise InvalidActionTransition(f"Action {current.action_id} is already running")

        message = (
            "Recovered stale running action; external outcome is unknown. "
            f"Reconcile provider state with idempotency key {current.action_id} before retrying."
        )
        return store._mark_failed_locked(
            current.action_id,
            message,
            expected_revision=current.revision,
        )

    def _execute(
        self,
        action: ActionRecord,
        context: ActionExecutionContext,
    ) -> object:
        handler = self.handlers.get(action.kind)
        if handler is not None:
            return handler(action, self.settings, context)
        if action.kind == ActionKind.SAVE_PERSONA:
            payload = cast(SavePersonaPayload, action.payload)
            repository = ArtistProfileRepository(base_path=self.settings.data_root / "artists")
            manifest_path = repository.save(payload.profile)
            return {
                "artist_slug": payload.profile.slug,
                "manifest_path": str(manifest_path),
            }
        return self.outbox.execute(action)


__all__ = [
    "ActionConflictError",
    "ActionExecutionContext",
    "ActionExecutor",
    "ActionHandler",
    "ActionKind",
    "ActionLedger",
    "ActionNotFoundError",
    "ActionPayload",
    "ActionRecord",
    "ActionStatus",
    "ActionStore",
    "DispatchReleasePayload",
    "InvalidActionTransition",
    "LocalOutboxAdapter",
    "OutboxReceipt",
    "RenderTrackPayload",
    "SavePersonaPayload",
    "ScheduleCampaignPayload",
    "StaleRunningPolicy",
]
