from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.world_stage.release import (
    ReleaseManifestRepository,
    ReleaseRequest,
    WorldStageService,
)
from artist_matrix.interfaces.distribution import DistributionReceipt, ReleaseSpec


@pytest.fixture()
def profile() -> ArtistProfile:
    return ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("cyberpunk", "cinematic"),
        lyric_style="narrative synth",
        visual_style="glitch neon",
        influences=("Perturbator",),
    )


class StubDistributionClient:
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.calls: list[ReleaseSpec] = []

    def submit_release(self, profile: ArtistProfile, spec: ReleaseSpec) -> DistributionReceipt:
        self.calls.append(spec)
        return DistributionReceipt(platform=self.platform, external_id=f"{self.platform}-123")


class RecordingAnalytics:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def record(self, profile: ArtistProfile, spec, receipt: DistributionReceipt) -> None:
        self.records.append((receipt.platform, receipt.external_id))


@pytest.fixture()
def track_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "signal_burn.json"
    manifest.write_text(json.dumps({"title": "Signal Burn"}), encoding="utf-8")
    return manifest


def test_dispatch_release_generates_manifest(
    profile: ArtistProfile, track_manifest: Path, tmp_path: Path
) -> None:
    client = StubDistributionClient("spotify")
    analytics = RecordingAnalytics()
    repository = ReleaseManifestRepository(base_path=tmp_path / "releases")
    fixed_time = datetime(2100, 1, 1, 0, 0, 0)
    service = WorldStageService(
        [client], analytics=analytics, repository=repository, clock=lambda: fixed_time
    )

    request = ReleaseRequest(
        title="Signal Burn",
        release_date=date(2100, 1, 2),
        platforms=("spotify",),
        track_manifest=track_manifest,
        artwork_path=None,
        description="Lead single from the Neon Wasteland EP.",
    )

    result = service.dispatch_release(profile, request)
    manifest_path = result["manifest_path"]

    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["artist"] == profile.slug
    assert data["title"] == "Signal Burn"
    assert data["release_date"] == "2100-01-02"
    assert data["receipts"][0]["platform"] == "spotify"
    assert data["dispatched_at"] == fixed_time.isoformat()
    assert analytics.records == [("spotify", "spotify-123")]


def test_dispatch_release_missing_client(
    profile: ArtistProfile, track_manifest: Path, tmp_path: Path
) -> None:
    service = WorldStageService([], repository=ReleaseManifestRepository(base_path=tmp_path))
    request = ReleaseRequest(
        title="Signal Burn",
        release_date=date(2100, 1, 2),
        platforms=("apple",),
        track_manifest=track_manifest,
    )

    with pytest.raises(ValueError):
        service.dispatch_release(profile, request)
