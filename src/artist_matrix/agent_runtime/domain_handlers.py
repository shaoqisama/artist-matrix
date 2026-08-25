"""Host-owned adapters from approved native actions to existing domain services."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from artist_matrix.agent_runtime.actions import (
    ActionExecutionContext,
    ActionHandler,
    ActionKind,
    ActionRecord,
    RenderTrackPayload,
    SavePersonaPayload,
)
from artist_matrix.creation_engine.connectors import (
    build_audio_generator,
)
from artist_matrix.creation_engine.service import (
    CreationBrief,
    CreationEngineService,
    TrackManifestRepository,
)
from artist_matrix.interfaces.production import LyricDraft, TrackArtifact
from artist_matrix.soul_forge.connectors import build_avatar_generator
from artist_matrix.soul_forge.profiles import ArtistProfile
from artist_matrix.soul_forge.service import ArtistProfileRepository
from artist_matrix.state.jobs import TrackJobSpec
from artist_matrix.state.settings import ArtistMatrixSettings


class _AcceptedDraftLyricGenerator:
    """Keep the user-approved lyric/instrumental choice unchanged at execution."""

    def __init__(self, *, body: str, references: tuple[str, ...]) -> None:
        self._body = body
        self._references = references

    def generate_lyrics(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
    ) -> LyricDraft:
        del profile
        return LyricDraft(title=spec.title, body=self._body, references=self._references)


def build_action_handlers(
    settings: ArtistMatrixSettings,
) -> Mapping[ActionKind, ActionHandler]:
    """Build adapters that are safe and complete for the active configuration.

    Local/stub audio is deterministic and can execute immediately after review.
    Remote providers stay in the explicit outbox until their adapter propagates
    ``ActionExecutionContext.idempotency_key`` to the provider.
    """

    handlers: dict[ActionKind, ActionHandler] = {}
    if settings.avatar_provider.lower() in {
        "diffusion",
        "local",
        "runway",
        "sdxl",
        "stub",
    }:
        handlers[ActionKind.SAVE_PERSONA] = _save_persona
    if settings.creation_audio_provider.lower() in {"local", "stub"}:
        handlers[ActionKind.RENDER_TRACK] = _render_track
    return handlers


def _save_persona(
    action: ActionRecord,
    settings: ArtistMatrixSettings,
    context: ActionExecutionContext,
) -> Mapping[str, object]:
    del context  # Current avatar implementations are local and deterministic.
    payload = cast(SavePersonaPayload, action.payload)
    avatar = build_avatar_generator(settings).generate_avatar(payload.profile)
    manifest_path = ArtistProfileRepository(base_path=settings.data_root / "artists").save(
        payload.profile, avatar=avatar
    )
    return {
        "artist_slug": payload.profile.slug,
        "manifest_path": str(manifest_path),
        "avatar_asset_path": str(avatar.asset_path) if avatar.asset_path else None,
        "avatar_provider": settings.avatar_provider.lower(),
    }


def _render_track(
    action: ActionRecord,
    settings: ArtistMatrixSettings,
    context: ActionExecutionContext,
) -> Mapping[str, object]:
    del context  # Local filesystem execution is serialized by the action lock.
    payload = cast(RenderTrackPayload, action.payload)
    profile = _load_profile(settings, payload.artist_slug)
    draft = payload.draft
    title = cast(str, draft.title)
    narrative = draft.summary or "\n".join(str(note) for note in draft.notes) or None
    brief = CreationBrief(
        track=TrackJobSpec(
            title=title,
            mood=draft.style or ", ".join(str(tag) for tag in draft.tags),
            references=tuple(str(tag) for tag in draft.tags),
            narrative=narrative,
        ),
        narrative=narrative,
    )
    service = CreationEngineService(
        lyric_generator=_AcceptedDraftLyricGenerator(
            body=draft.lyrics or "",
            references=tuple(str(tag) for tag in draft.tags),
        ),
        audio_generator=build_audio_generator(settings),
        repository=TrackManifestRepository(base_path=settings.data_root / "artists"),
    )
    result = service.produce_track(profile, brief)
    track = cast(TrackArtifact, result["track"])
    return {
        "artist_slug": payload.artist_slug,
        "title": title,
        "manifest_path": str(result["manifest_path"]),
        "audio_path": str(track.audio_path),
        "provider": settings.creation_audio_provider.lower(),
    }


def _load_profile(settings: ArtistMatrixSettings, artist_slug: str) -> ArtistProfile:
    path = settings.data_root / "artists" / f"{artist_slug}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LookupError(f"Artist profile not found: {artist_slug}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read artist profile: {artist_slug}") from exc
    profile = ArtistProfile.model_validate(payload)
    if profile.slug != artist_slug:
        raise RuntimeError(f"Artist profile slug mismatch in {path.name}")
    return profile


__all__ = ["build_action_handlers"]
