"""Read/propose-only MCP server for the native Artist Matrix agents.

The server exposes product context and creates reviewable action records. It
does not register approval, rejection, execution, shell, or filesystem-write
tools. Every product path is derived by the host from
:class:`ArtistMatrixSettings`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from artist_matrix.agent_runtime.actions import (
    ActionKind,
    ActionRecord,
    ActionStatus,
    ActionStore,
)
from artist_matrix.state.settings import ArtistMatrixSettings

_SAFE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _record_json(record: ActionRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")


def _slug(value: str, *, field: str) -> str:
    value = value.strip().lower()
    if not _SAFE_SLUG.fullmatch(value):
        raise ValueError(f"{field} must be a simple lowercase slug")
    return value


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LookupError(f"{label} not found") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read {label}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid {label} record")
    return value


class ActionMCPTools:
    """Public product tools registered with Codex through MCP."""

    def __init__(
        self,
        store: ActionStore,
        settings: ArtistMatrixSettings | None = None,
        *,
        actor: str = "codex",
    ) -> None:
        inferred_settings = getattr(store, "settings", None)
        resolved_settings = settings or (
            inferred_settings if isinstance(inferred_settings, ArtistMatrixSettings) else None
        )
        if resolved_settings is None:
            raise TypeError("ActionMCPTools requires ArtistMatrixSettings")
        self.settings: ArtistMatrixSettings = resolved_settings
        self.store = store
        self.actor = actor

    # Product context -------------------------------------------------

    def list_artists(self) -> list[dict[str, Any]]:
        artists_root = self.settings.data_root / "artists"
        if not artists_root.exists():
            return []
        artists: list[dict[str, Any]] = []
        for path in sorted(artists_root.glob("*.json")):
            try:
                record = _read_json(path, label=f"artist {path.stem}")
            except RuntimeError:
                continue
            artists.append(
                {
                    "name": record.get("name"),
                    "slug": record.get("slug", path.stem),
                    "persona_tags": record.get("persona_tags", []),
                    "lyric_style": record.get("lyric_style"),
                }
            )
        return artists

    def get_artist(self, artist_slug: str) -> dict[str, Any]:
        safe_slug = _slug(artist_slug, field="artist_slug")
        path = self.settings.data_root / "artists" / f"{safe_slug}.json"
        return _read_json(path, label=f"artist {safe_slug}")

    def list_tracks(self, artist_slug: str) -> list[dict[str, Any]]:
        safe_slug = _slug(artist_slug, field="artist_slug")
        tracks_root = self.settings.data_root / "artists" / safe_slug / "tracks"
        if not tracks_root.exists():
            return []
        tracks: list[dict[str, Any]] = []
        for path in sorted(tracks_root.glob("*.json")):
            try:
                record = _read_json(path, label=f"track {path.stem}")
            except RuntimeError:
                continue
            tracks.append(
                {
                    "artist_slug": safe_slug,
                    "track_slug": path.stem,
                    "title": record.get("title"),
                    "created_at": record.get("created_at"),
                }
            )
        return tracks

    def get_track(self, artist_slug: str, track_slug: str) -> dict[str, Any]:
        safe_artist = _slug(artist_slug, field="artist_slug")
        safe_track = _slug(track_slug, field="track_slug")
        path = self.settings.data_root / "artists" / safe_artist / "tracks" / f"{safe_track}.json"
        return _read_json(path, label=f"track {safe_artist}/{safe_track}")

    # Proposals -------------------------------------------------------

    def propose_artist_profile(self, profile: Mapping[str, object]) -> dict[str, Any]:
        record = self.store.propose(
            ActionKind.SAVE_PERSONA,
            {"profile": dict(profile)},
            requested_by=self.actor,
        )
        return _record_json(record)

    def propose_track_render(
        self,
        artist_slug: str,
        draft: Mapping[str, object],
    ) -> dict[str, Any]:
        record = self.store.propose(
            ActionKind.RENDER_TRACK,
            {"artist_slug": artist_slug, "draft": dict(draft)},
            requested_by=self.actor,
        )
        return _record_json(record)

    def propose_social_campaign(
        self,
        artist_slug: str,
        title: str,
        platform: str,
        beats: Sequence[str],
        cadence_minutes: int = 120,
    ) -> dict[str, Any]:
        record = self.store.propose(
            ActionKind.SCHEDULE_CAMPAIGN,
            {
                "artist_slug": artist_slug,
                "title": title,
                "platform": platform,
                "beats": list(beats),
                "cadence_minutes": cadence_minutes,
            },
            requested_by=self.actor,
        )
        return _record_json(record)

    def propose_release(
        self,
        artist_slug: str,
        title: str,
        release_date: str,
        platforms: Sequence[str],
        track_slug: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        record = self.store.propose(
            ActionKind.DISPATCH_RELEASE,
            {
                "artist_slug": artist_slug,
                "title": title,
                "release_date": release_date,
                "platforms": list(platforms),
                "track_slug": track_slug,
                "description": description,
            },
            requested_by=self.actor,
        )
        return _record_json(record)

    # Action inspection -----------------------------------------------

    def get_action(self, action_id: str) -> dict[str, Any]:
        return _record_json(self.store.get(action_id))

    def list_actions(
        self,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        records = self.store.list_actions(
            kind=ActionKind(kind) if kind is not None else None,
            status=ActionStatus(status) if status is not None else None,
        )
        return [_record_json(record) for record in records[:limit]]


MCPToolHandler = Callable[..., object]


def build_mcp_tool_handlers(tools: ActionMCPTools) -> dict[str, MCPToolHandler]:
    """Return the exact read/propose allowlist exposed to Codex."""

    return {
        "list_artists": tools.list_artists,
        "get_artist": tools.get_artist,
        "list_tracks": tools.list_tracks,
        "get_track": tools.get_track,
        "list_actions": tools.list_actions,
        "get_action": tools.get_action,
        "propose_artist_profile": tools.propose_artist_profile,
        "propose_track_render": tools.propose_track_render,
        "propose_social_campaign": tools.propose_social_campaign,
        "propose_release": tools.propose_release,
    }


def build_mcp_server(settings: ArtistMatrixSettings | None = None) -> FastMCP:
    """Build the stdio MCP server configured entirely by the host settings."""

    resolved_settings = settings or ArtistMatrixSettings()
    store = ActionStore(resolved_settings.resolved_action_root)
    tools = ActionMCPTools(store, resolved_settings)
    server = FastMCP(
        "artist-matrix",
        instructions=(
            "Read Artist Matrix product context and create reviewable proposals. "
            "No tool exposed by this server can approve or execute an action."
        ),
    )
    for name, handler in build_mcp_tool_handlers(tools).items():
        server.tool(name=name)(handler)
    return server


def main() -> None:
    """Run the MCP server over stdio for Codex app-server."""

    build_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()


__all__ = [
    "ActionMCPTools",
    "MCPToolHandler",
    "build_mcp_server",
    "build_mcp_tool_handlers",
    "main",
]
