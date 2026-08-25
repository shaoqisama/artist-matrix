"""Provider-neutral events emitted by the Artist Matrix agent runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeEventType(str, Enum):
    """Stable event types consumed by terminal, web, or background clients."""

    thread_started = "thread_started"
    turn_started = "turn_started"
    message_delta = "message_delta"
    reasoning_delta = "reasoning_delta"
    plan_updated = "plan_updated"
    tool_started = "tool_started"
    tool_progress = "tool_progress"
    tool_completed = "tool_completed"
    command_output = "command_output"
    usage_updated = "usage_updated"
    turn_completed = "turn_completed"
    warning = "warning"
    error = "error"


class RuntimeEvent(BaseModel):
    """One normalized event from an underlying agent harness."""

    model_config = ConfigDict(frozen=True)

    type: RuntimeEventType
    thread_id: str | None = None
    turn_id: str | None = None
    item_id: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    text: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentTurnResult(BaseModel):
    """Final result of one agent turn."""

    model_config = ConfigDict(frozen=True)

    role: str
    thread_id: str
    turn_id: str
    response: str | None = None
    status: str = "completed"
    started_new_thread: bool = False
    usage: dict[str, Any] | None = None
    error: str | None = None


__all__ = ["AgentTurnResult", "RuntimeEvent", "RuntimeEventType"]
