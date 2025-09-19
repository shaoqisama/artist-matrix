"""Content planning utilities for Echo Chamber."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Iterator, Sequence

from artist_matrix.soul_forge import ArtistProfile


@dataclass(frozen=True)
class SocialCampaign:
    """Defines a sequence of social posts for a persona."""

    title: str
    beats: Sequence[str]
    cadence_minutes: int = 120


class CampaignPlanner:
    """Generates scheduled content plans for campaigns."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or datetime.utcnow

    def plan(
        self,
        profile: ArtistProfile,
        campaign: SocialCampaign,
        *,
        start_at: datetime | None = None,
    ) -> Iterator[tuple[str, datetime]]:
        base = start_at or self._clock()
        offset = timedelta(minutes=campaign.cadence_minutes)
        for index, beat in enumerate(campaign.beats):
            yield beat, base + offset * index


__all__ = ["SocialCampaign", "CampaignPlanner"]
