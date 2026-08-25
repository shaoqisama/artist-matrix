from __future__ import annotations

from datetime import datetime
from typing import List

import pytest

from artist_matrix.echo_chamber import CampaignPlanner, EchoChamberService, SocialCampaign
from artist_matrix.interfaces.social import SocialPost
from artist_matrix.soul_forge import ArtistProfile


@pytest.fixture()
def profile() -> ArtistProfile:
    return ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("cyberpunk", "cinematic"),
        lyric_style="narrative synth",
        visual_style="glitch neon",
        influences=("Perturbator",),
    )


class RecordingClient:
    def __init__(self, platform: str, *, fail_on: int | None = None) -> None:
        self.platform = platform
        self.fail_on = fail_on
        self.published: List[SocialPost] = []
        self.failures: List[SocialPost] = []
        self._counter = 0

    def publish(self, post: SocialPost) -> None:
        self._counter += 1
        if self.fail_on is not None and self._counter == self.fail_on:
            self.failures.append(post)
            raise RuntimeError("Publishing failed")
        self.published.append(post)


class RecordingAnalytics:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def record(self, profile: ArtistProfile, post: SocialPost, *, status: str) -> None:
        self.records.append((post.content, status))


def test_campaign_planner_spacing(profile: ArtistProfile) -> None:
    planner = CampaignPlanner(clock=lambda: datetime(2100, 1, 1, 0, 0, 0))
    campaign = SocialCampaign(
        title="Release Week",
        platform="twitter",
        beats=("Teaser", "Drop", "Recap"),
        cadence_minutes=60,
    )
    slots = list(planner.plan(profile, campaign))

    assert len(slots) == 3
    assert slots[0][1] == datetime(2100, 1, 1, 0, 0, 0)
    assert slots[2][1] == datetime(2100, 1, 1, 2, 0, 0)


def test_publish_campaign_records_success_and_failure(profile: ArtistProfile) -> None:
    client = RecordingClient("twitter", fail_on=2)
    analytics = RecordingAnalytics()
    service = EchoChamberService([client], analytics_client=analytics)

    campaign = SocialCampaign(
        title="Signal Boost",
        platform="twitter",
        beats=("Hello", "Drop", "Recap"),
        cadence_minutes=30,
    )

    result = service.publish_campaign(
        profile, campaign, platform="twitter", start_at=datetime(2100, 1, 1, 0, 0, 0)
    )

    assert len(result.scheduled) == 2
    assert len(result.failed) == 1
    assert analytics.records[1] == ("Drop", "failed")


def test_publish_campaign_missing_client(profile: ArtistProfile) -> None:
    service = EchoChamberService([])
    campaign = SocialCampaign(title="Ghost Post", platform="discord", beats=("Ping",))

    with pytest.raises(ValueError):
        service.publish_campaign(profile, campaign, platform="discord")
