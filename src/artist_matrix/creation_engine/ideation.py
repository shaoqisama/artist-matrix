"""Track ideation data models and persistence helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Sequence

from pydantic import BaseModel, Field

from artist_matrix.state import ArtistMatrixSettings

_logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    """Represents a single turn in the ideation conversation."""

    role: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrackIdeationDraft(BaseModel):
    """Minimal draft built only from user-confirmed fields."""

    persona_slug: str
    title: str | None = None
    style: str | None = None
    tags: Sequence[str] = Field(default_factory=tuple)
    lyrics: str | None = None
    notes: Sequence[str] = Field(default_factory=tuple)
    duration_sec: int | None = None
    allow_instrumental: bool = True
    ref_url: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str | None = None

    model_config = {
        "extra": "ignore",
        "json_schema_extra": {
            "examples": [
                {
                    "persona_slug": "neon-falcon",
                    "title": "Signal Burn",
                    "style": "glitch-pop anthem",
                    "tags": ["glitch", "synth", "midnight"],
                    "lyrics": "Verse...",
                    "notes": ["keep vocals airy"],
                    "duration_sec": 180,
                    "allow_instrumental": True,
                    "ref_url": "https://reference.example/signal-burn",
                }
            ]
        }
    }

    def update_timestamp(self) -> None:
        object.__setattr__(self, "updated_at", datetime.now(timezone.utc))


@dataclass(slots=True)
class TrackIdeationStore:
    """Persists drafts and transcripts per persona for reuse."""

    settings: ArtistMatrixSettings

    def _persona_root(self, persona_slug: str) -> Path:
        base = self.settings.data_root / "artists" / persona_slug / "drafts"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def draft_path(self, persona_slug: str) -> Path:
        return self._persona_root(persona_slug) / "latest_draft.json"

    def transcript_path(self, persona_slug: str) -> Path:
        return self._persona_root(persona_slug) / "latest_transcript.jsonl"

    def final_path(self, persona_slug: str) -> Path:
        return self._persona_root(persona_slug) / "final_brief.json"

    def save_draft(self, draft: TrackIdeationDraft) -> Path:
        path = self.draft_path(draft.persona_slug)
        _logger.debug("Persisting track draft", extra={"persona": draft.persona_slug, "path": str(path)})
        serialisable = json.loads(draft.model_dump_json())
        path.write_text(json.dumps(serialisable, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_draft(self, persona_slug: str) -> TrackIdeationDraft | None:
        path = self.draft_path(persona_slug)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TrackIdeationDraft.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "Failed to load track draft",
                extra={"persona": persona_slug, "path": str(path), "error": str(exc)},
            )
            return None

    def append_transcript(self, persona_slug: str, turns: Iterable[ChatTurn]) -> Path:
        path = self.transcript_path(persona_slug)
        _logger.debug(
            "Appending transcript",
            extra={"persona": persona_slug, "path": str(path)},
        )
        with path.open("a", encoding="utf-8") as handle:
            for turn in turns:
                handle.write(turn.model_dump_json())
                handle.write("\n")
        return path

    def save_final(self, draft: TrackIdeationDraft) -> Path:
        path = self.final_path(draft.persona_slug)
        _logger.debug(
            "Persisting final track draft",
            extra={"persona": draft.persona_slug, "path": str(path)},
        )
        serialisable = json.loads(draft.model_dump_json())
        path.write_text(json.dumps(serialisable, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_final(self, persona_slug: str) -> TrackIdeationDraft | None:
        path = self.final_path(persona_slug)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TrackIdeationDraft.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "Failed to load final draft",
                extra={"persona": persona_slug, "path": str(path), "error": str(exc)},
            )
            return None

    def load_transcript(self, persona_slug: str) -> List[ChatTurn]:
        path = self.transcript_path(persona_slug)
        if not path.exists():
            return []
        turns: list[ChatTurn] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        turns.append(ChatTurn.model_validate_json(line))
                    except Exception as exc:  # noqa: BLE001
                        _logger.debug(
                            "Skipping transcript line",
                            extra={"persona": persona_slug, "error": str(exc)},
                        )
        except OSError as exc:  # noqa: BLE001
            _logger.warning(
                "Failed to load transcript",
                extra={"persona": persona_slug, "error": str(exc)},
            )
        return turns


__all__ = [
    "ChatTurn",
    "TrackIdeationDraft",
    "TrackIdeationStore",
]
