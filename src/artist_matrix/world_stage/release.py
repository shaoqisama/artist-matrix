"""World Stage service responsible for distribution and release manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from artist_matrix.interfaces.distribution import (
    DistributionClient,
    DistributionReceipt,
    ReleaseAnalytics,
    ReleaseSpec,
)
from artist_matrix.soul_forge import ArtistProfile

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_RELEASE_ROOT = _PROJECT_ROOT / "data" / "releases"


@dataclass(frozen=True)
class ReleaseRequest:
    """Input describing the release metadata and assets."""

    title: str
    release_date: date
    platforms: Sequence[str]
    track_manifest: Path
    artwork_path: Path | None = None
    description: str | None = None

    def to_spec(self) -> ReleaseSpec:
        return ReleaseSpec(
            title=self.title,
            release_date=self.release_date,
            platforms=tuple(self.platforms),
            track_manifest=self.track_manifest,
            artwork_path=self.artwork_path,
            description=self.description,
        )


class ReleaseManifestRepository:
    """Persist release manifests for auditing and analytics."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or _RELEASE_ROOT

    def save(
        self,
        profile: ArtistProfile,
        request: ReleaseRequest,
        receipts: Sequence[DistributionReceipt],
        *,
        dispatched_at: datetime,
    ) -> Path:
        artist_root = self.base_path / profile.slug
        artist_root.mkdir(parents=True, exist_ok=True)
        release_slug = request.title.lower().replace(" ", "-")
        manifest_path = artist_root / f"{release_slug}.json"

        payload = {
            "artist": profile.slug,
            "title": request.title,
            "release_date": request.release_date.isoformat(),
            "platforms": list(request.platforms),
            "track_manifest": str(request.track_manifest),
            "artwork_path": str(request.artwork_path) if request.artwork_path else None,
            "description": request.description,
            "receipts": [
                {
                    "platform": receipt.platform,
                    "external_id": receipt.external_id,
                    "dashboard_url": receipt.dashboard_url,
                }
                for receipt in receipts
            ],
            "dispatched_at": dispatched_at.isoformat(),
        }
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return manifest_path


class WorldStageService:
    """Coordinates distribution of releases across platforms."""

    def __init__(
        self,
        clients: Iterable[DistributionClient],
        *,
        analytics: ReleaseAnalytics | None = None,
        repository: ReleaseManifestRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clients = {client.platform: client for client in clients}
        self._analytics = analytics
        self._repository = repository or ReleaseManifestRepository()
        self._clock = clock or datetime.utcnow

    def dispatch_release(
        self,
        profile: ArtistProfile,
        request: ReleaseRequest,
    ) -> Mapping[str, object]:
        spec = request.to_spec()
        receipts: list[DistributionReceipt] = []

        for platform in spec.platforms:
            if platform not in self._clients:
                raise ValueError(f"No distribution client configured for platform '{platform}'")
            client = self._clients[platform]
            receipt = client.submit_release(profile, spec)
            receipts.append(receipt)
            if self._analytics is not None:
                self._analytics.record(profile, spec, receipt)

        manifest_path = self._repository.save(
            profile=profile,
            request=request,
            receipts=receipts,
            dispatched_at=self._clock(),
        )

        return {
            "spec": spec,
            "receipts": tuple(receipts),
            "manifest_path": manifest_path,
        }


__all__ = ["WorldStageService", "ReleaseRequest", "ReleaseManifestRepository"]
