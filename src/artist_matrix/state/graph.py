"""Workflow state machine wiring Artist Matrix agents together."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Callable, cast

from artist_matrix.creation_engine import CreationBrief, CreationEngineService
from artist_matrix.echo_chamber import EchoChamberService, SocialCampaign
from artist_matrix.soul_forge import ArtistProfile, SoulForgeRequest, SoulForgeService
from artist_matrix.state import ArtistManifest, JobContext, ReleaseManifest, TrackManifest
from artist_matrix.world_stage.release import ReleaseRequest, WorldStageService


@dataclass
class WorkflowHooks:
    """Hooks invoked at each stage for logging or metrics."""

    on_profile_created: Callable[[JobContext], None] | None = None
    on_track_produced: Callable[[JobContext], None] | None = None
    on_campaign_published: Callable[[JobContext], None] | None = None
    on_release_dispatched: Callable[[JobContext], None] | None = None
    on_error: Callable[[JobContext, Exception], None] | None = None


class ArtistMatrixGraph:
    """Coordinates all nodes to deliver end-to-end releases."""

    def __init__(
        self,
        *,
        soul_forge: SoulForgeService,
        creation_engine: CreationEngineService,
        echo_chamber: EchoChamberService,
        world_stage: WorldStageService,
        hooks: WorkflowHooks | None = None,
    ) -> None:
        self.soul_forge = soul_forge
        self.creation_engine = creation_engine
        self.echo_chamber = echo_chamber
        self.world_stage = world_stage
        self.hooks = hooks or WorkflowHooks()

    def new_artist_release(
        self,
        soul_request: SoulForgeRequest,
        track_brief: CreationBrief,
        campaign: SocialCampaign,
        release_request: ReleaseRequest,
    ) -> JobContext:
        profile = self._create_artist(soul_request)
        artist_manifest = ArtistManifest.model_validate(profile.manifest())
        context = JobContext(artist=artist_manifest)
        self._emit(self.hooks.on_profile_created, context)

        track_manifest = self._produce_track(profile, track_brief)
        context = context.model_copy(update={"track": track_manifest})
        self._emit(self.hooks.on_track_produced, context)

        release_payload = replace(
            release_request,
            track_manifest=Path(track_manifest.manifest_path),
        )

        self._publish_campaign(profile, campaign)
        self._emit(self.hooks.on_campaign_published, context)

        release_manifest = self._dispatch_release(profile, release_payload)
        context = context.model_copy(update={"release": release_manifest})
        self._emit(self.hooks.on_release_dispatched, context)
        return context

    def _create_artist(self, request: SoulForgeRequest) -> ArtistProfile:
        result = self.soul_forge.generate(request)
        return cast(ArtistProfile, result["profile"])

    def _produce_track(self, profile: ArtistProfile, brief: CreationBrief) -> TrackManifest:
        result = self.creation_engine.produce_track(profile, brief)
        manifest_path = Path(str(result["manifest_path"]))
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        artwork_path = None
        if "artwork" in manifest_data:
            artwork_path = manifest_data["artwork"]["image_path"]
        track_manifest = TrackManifest(
            title=manifest_data["title"],
            mood=manifest_data["track_job"]["mood"],
            tempo_bpm=manifest_data["track_job"]["tempo_bpm"],
            key=manifest_data["track_job"]["key"],
            references=tuple(manifest_data["track_job"]["references"]),
            narrative=manifest_data["track_job"].get("narrative"),
            audio_path=manifest_data["track"]["audio_path"],
            artwork_path=artwork_path,
            created_at=datetime.fromisoformat(manifest_data["created_at"]),
            manifest_path=str(manifest_path),
        )
        return track_manifest

    def _publish_campaign(self, profile: ArtistProfile, campaign: SocialCampaign) -> None:
        platform = getattr(campaign, "platform", None)
        if platform is None:
            raise ValueError("Campaign must define a platform for publishing")
        self.echo_chamber.publish_campaign(profile, campaign, platform=platform)

    def _dispatch_release(self, profile: ArtistProfile, request: ReleaseRequest) -> ReleaseManifest:
        result = self.world_stage.dispatch_release(profile, request)
        manifest_path = Path(str(result["manifest_path"]))
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ReleaseManifest(
            title=manifest_data["title"],
            artist_slug=manifest_data["artist"],
            release_date=date.fromisoformat(manifest_data["release_date"]),
            platforms=tuple(manifest_data["platforms"]),
            track_manifest_path=manifest_data["track_manifest"],
            artwork_path=manifest_data.get("artwork_path"),
            description=manifest_data.get("description"),
            receipts=tuple(manifest_data["receipts"]),
        )

    def _emit(self, hook: Callable[[JobContext], None] | None, context: JobContext) -> None:
        if hook:
            hook(context)


__all__ = ["ArtistMatrixGraph", "WorkflowHooks"]
