"""Schema definitions for virtual artist profiles."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Sequence

from pydantic import BaseModel, ConfigDict, Field


_slug_pattern = re.compile(r"[^a-z0-9]+")


if TYPE_CHECKING:
    from artist_matrix.interfaces.creative import PersonaDraft


class ArtistProfile(BaseModel):
    """Canonical representation of an Artist Matrix persona."""

    model_config = ConfigDict(frozen=True)

    name: str
    persona_tags: Sequence[str] = Field(default_factory=tuple)
    lyric_style: str
    visual_style: str
    influences: Sequence[str] = Field(default_factory=tuple)
    safety_notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0"

    @property
    def slug(self) -> str:
        """Stable slug used for manifests and storage paths."""

        lowered = self.name.lower().strip()
        sanitized = _slug_pattern.sub("-", lowered)
        slug = sanitized.strip("-")
        return slug or "artist"

    def manifest(self) -> Dict[str, Any]:
        """Return a serialisable manifest for persistence."""

        payload = self.model_dump()
        payload["slug"] = self.slug
        payload["created_at"] = self.created_at.isoformat()
        payload["persona_tags"] = list(self.persona_tags)
        payload["influences"] = list(self.influences)
        return payload

    @classmethod
    def from_draft(
        cls,
        draft: "PersonaDraft",
        *,
        created_at: datetime | None = None,
        version: str = "1.0",
    ) -> "ArtistProfile":
        from artist_matrix.interfaces.creative import PersonaDraft as PersonaDraftType

        if not isinstance(draft, PersonaDraftType):
            raise TypeError("draft must be an instance of PersonaDraft")

        return cls(
            name=draft.name,
            persona_tags=tuple(draft.persona_tags),
            lyric_style=draft.lyric_style,
            visual_style=draft.visual_style,
            influences=tuple(draft.influences),
            safety_notes=draft.safety_notes,
            created_at=created_at or datetime.utcnow(),
            version=version,
        )


__all__ = ["ArtistProfile"]
