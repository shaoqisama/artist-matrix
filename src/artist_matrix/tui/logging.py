"""TUI session logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionLogger:
    """Writes user/AI interaction entries to JSONL with basic redaction."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = self.log_dir / f"session_{timestamp}.jsonl"
        self._handle = self.path.open("a", encoding="utf-8")

    def write_event(self, *, role: str, message: str) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "role": role,
            "message": self._redact(message),
        }
        self._handle.write(json.dumps(payload))
        self._handle.write("\n")
        self._handle.flush()

    def _redact(self, text: str) -> str:
        if "api key" in text.lower():
            return "<redacted>"
        return text

    def close(self) -> None:
        try:
            self._handle.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to close session log", extra={"error": str(exc)})


__all__ = ["SessionLogger"]
