"""Echo Chamber service handling social scheduling and posting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from artist_matrix.interfaces.social import AnalyticsClient, SocialClient, SocialPost
from artist_matrix.soul_forge import ArtistProfile

from .planner import CampaignPlanner, SocialCampaign


@dataclass(frozen=True)
class SocialPlanResult:
    """Represents the outcome of scheduling and publishing a campaign."""

    scheduled: Sequence[SocialPost]
    failed: Sequence[SocialPost]


class EchoChamberService:
    """Coordinates planning and posting content for virtual artists."""

    def __init__(
        self,
        clients: Iterable[SocialClient],
        *,
        analytics_client: AnalyticsClient | None = None,
        planner: CampaignPlanner | None = None,
    ) -> None:
        self._clients = {client.platform: client for client in clients}
        self._analytics = analytics_client
        self._planner = planner or CampaignPlanner()

    def _build_posts(
        self,
        profile: ArtistProfile,
        campaign: SocialCampaign,
        *,
        start_at: datetime | None = None,
        platform: str,
    ) -> Sequence[SocialPost]:
        beats = list(self._planner.plan(profile, campaign, start_at=start_at))
        return [
            SocialPost(platform=platform, content=beat, scheduled_for=scheduled)
            for beat, scheduled in beats
        ]

    def publish_campaign(
        self,
        profile: ArtistProfile,
        campaign: SocialCampaign,
        *,
        platform: str,
        start_at: datetime | None = None,
    ) -> SocialPlanResult:
        if platform not in self._clients:
            raise ValueError(f"No client configured for platform '{platform}'")

        client = self._clients[platform]
        posts = self._build_posts(profile, campaign, start_at=start_at, platform=platform)
        successes: list[SocialPost] = []
        failures: list[SocialPost] = []

        for post in posts:
            try:
                client.publish(post)
            except Exception:  # noqa: BLE001 - capture and report, continue posting
                failures.append(post)
                self._record(profile, post, status="failed")
            else:
                successes.append(post)
                self._record(profile, post, status="published")

        return SocialPlanResult(scheduled=tuple(successes), failed=tuple(failures))

    def _record(self, profile: ArtistProfile, post: SocialPost, *, status: str) -> None:
        if self._analytics is None:
            return
        self._analytics.record(profile, post, status=status)


__all__ = ["EchoChamberService", "SocialPlanResult"]
