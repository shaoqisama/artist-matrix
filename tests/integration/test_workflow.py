from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from artist_matrix.creation_engine import (
    CreationBrief,
    CreationEngineService,
    TrackManifestRepository,
)
from artist_matrix.echo_chamber import EchoChamberService, SocialCampaign
from artist_matrix.interfaces.distribution import DistributionReceipt, ReleaseSpec
from artist_matrix.interfaces.production import ArtworkArtifact, LyricDraft, TrackArtifact
from artist_matrix.interfaces.social import SocialPost
from artist_matrix.soul_forge import ArtistProfileRepository, SoulForgeRequest, SoulForgeService
from artist_matrix.soul_forge.connectors import (
    DiffusionAvatarGenerator,
    LLMTemplatePersonaGenerator,
)
from artist_matrix.state import JobContext
from artist_matrix.state.graph import ArtistMatrixGraph
from artist_matrix.state.jobs import ArtworkJobSpec, TrackJobSpec
from artist_matrix.world_stage.release import (
    ReleaseManifestRepository,
    ReleaseRequest,
    WorldStageService,
)


pytestmark = pytest.mark.integration


class StubLyricGenerator:
    def generate_lyrics(self, profile, spec: TrackJobSpec) -> LyricDraft:
        return LyricDraft(title=spec.title, body="lyrics", references=spec.references)


class StubAudioGenerator:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path

    def render_track(self, profile, spec: TrackJobSpec, lyrics: LyricDraft) -> TrackArtifact:
        path = self.tmp_path / f"{spec.title.lower().replace(' ', '_')}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return TrackArtifact(title=spec.title, audio_path=path)


class StubArtworkGenerator:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path

    def render_artwork(
        self, profile, spec: ArtworkJobSpec, track: TrackArtifact
    ) -> ArtworkArtifact:
        path = self.tmp_path / f"{track.title.lower().replace(' ', '_')}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"art")
        return ArtworkArtifact(title=track.title, image_path=path, prompt="cover", seed=spec.seed)


class StubSocialClient:
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.posts: list[SocialPost] = []

    def publish(self, post: SocialPost) -> None:
        self.posts.append(post)


class StubDistributionClient:
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.receipts: list[DistributionReceipt] = []

    def submit_release(self, profile, spec: ReleaseSpec) -> DistributionReceipt:
        receipt = DistributionReceipt(platform=self.platform, external_id=f"{self.platform}-001")
        self.receipts.append(receipt)
        return receipt


class RecordingAnalytics:
    def __init__(self) -> None:
        self.records: list[str] = []

    def record(self, profile, spec, receipt: DistributionReceipt) -> None:
        self.records.append(receipt.external_id)


def test_full_workflow(tmp_path: Path) -> None:
    artists_dir = tmp_path / "artists"
    tracks_dir = tmp_path / "tracks"
    releases_dir = tmp_path / "releases"
    avatars_dir = tmp_path / "avatars"

    soul_service = SoulForgeService(
        persona_generator=LLMTemplatePersonaGenerator(
            provider="deepseek",
            model="deepseek-music",
            api_key="sk-deepseek-test",
        ),
        avatar_generator=DiffusionAvatarGenerator(
            provider="sdxl",
            model="sdxl-music",
            asset_root=avatars_dir,
            api_key="sk-sdxl-test",
        ),
        repository=ArtistProfileRepository(base_path=artists_dir),
        clock=lambda: datetime(2100, 1, 1, 0, 0, 0),
    )

    creation_service = CreationEngineService(
        lyric_generator=StubLyricGenerator(),
        audio_generator=StubAudioGenerator(tracks_dir),
        artwork_generator=StubArtworkGenerator(tracks_dir),
        repository=TrackManifestRepository(base_path=tracks_dir),
        clock=lambda: datetime(2100, 1, 2, 0, 0, 0),
    )

    social_client = StubSocialClient("twitter")
    echo_service = EchoChamberService([social_client])

    distribution_client = StubDistributionClient("spotify")
    world_service = WorldStageService(
        [distribution_client],
        analytics=RecordingAnalytics(),
        repository=ReleaseManifestRepository(base_path=releases_dir),
        clock=lambda: datetime(2100, 1, 3, 0, 0, 0),
    )

    graph = ArtistMatrixGraph(
        soul_forge=soul_service,
        creation_engine=creation_service,
        echo_chamber=echo_service,
        world_stage=world_service,
    )

    context = graph.new_artist_release(
        soul_request=SoulForgeRequest(
            name="Neon Wasteland",
            genre="synthwave",
            mood="fierce",
            influences=("Kavinsky",),
            descriptors=("retro",),
        ),
        track_brief=CreationBrief(
            track=TrackJobSpec(title="Signal Burn", mood="fierce"),
            artwork=ArtworkJobSpec(title="Signal Burn", style="poster"),
        ),
        campaign=SocialCampaign(
            title="Signal Burn Launch", platform="twitter", beats=("Teaser", "Drop")
        ),
        release_request=ReleaseRequest(
            title="Signal Burn",
            release_date=date(2100, 1, 4),
            platforms=("spotify",),
            track_manifest=tracks_dir / "placeholder.json",
        ),
    )

    assert isinstance(context, JobContext)
    assert context.artist.slug == "neon-wasteland"
    assert context.track is not None
    assert context.track.title == "Signal Burn"
    assert context.release is not None
    assert context.release.platforms == ("spotify",)
    assert social_client.posts

    avatar_asset = avatars_dir / "neon-wasteland-sdxl.json"
    assert avatar_asset.exists()
