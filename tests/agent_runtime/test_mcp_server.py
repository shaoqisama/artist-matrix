from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path

import pytest

from artist_matrix.agent_runtime.actions import ActionLedger, ActionStatus
from artist_matrix.agent_runtime.codex import CODEX_PERMISSION_PROFILE, DISABLED_CODEX_FEATURES
from artist_matrix.agent_runtime.definitions import MCP_TOOL_ALLOWLIST
from artist_matrix.agent_runtime.mcp_server import (
    ActionMCPTools,
    build_mcp_server,
    build_mcp_tool_handlers,
)
from artist_matrix.state import ArtistMatrixSettings


def _profile_payload() -> dict[str, object]:
    return {
        "name": "Neon Wasteland",
        "persona_tags": ["retro"],
        "lyric_style": "synthwave stories",
        "visual_style": "neon glitch",
        "influences": ["Kavinsky"],
    }


def test_mcp_surface_exposes_only_propose_and_read_tools(tmp_path: Path) -> None:
    tools = ActionMCPTools(ActionLedger(ArtistMatrixSettings(data_root=tmp_path)))
    handlers = build_mcp_tool_handlers(tools)

    assert set(handlers) == {
        "list_artists",
        "get_artist",
        "list_tracks",
        "get_track",
        "list_actions",
        "get_action",
        "propose_artist_profile",
        "propose_track_render",
        "propose_social_campaign",
        "propose_release",
    }
    assert not any("approve" in name or "execute" in name or "reject" in name for name in handlers)


def test_mcp_proposals_remain_pending_and_are_readable(tmp_path: Path) -> None:
    tools = ActionMCPTools(
        ActionLedger(ArtistMatrixSettings(data_root=tmp_path)),
        actor="creation-agent",
    )

    persona = tools.propose_artist_profile(_profile_payload())
    render = tools.propose_track_render(
        "neon-wasteland",
        {
            "persona_slug": "neon-wasteland",
            "title": "Signal Burn",
            "style": "synthwave",
            "tags": ["neon"],
            "lyrics": "Verse line",
        },
    )
    campaign = tools.propose_social_campaign(
        "neon-wasteland",
        "Signal Burn Launch",
        "echo",
        ["Teaser", "Drop"],
        90,
    )
    release = tools.propose_release(
        "neon-wasteland",
        "Signal Burn",
        "2100-01-04",
        ["spotify"],
        "signal-burn",
    )

    for proposed in (persona, render, campaign, release):
        assert proposed["status"] == ActionStatus.PENDING.value
        assert proposed["requested_by"] == "creation-agent"
        assert tools.get_action(proposed["action_id"]) == proposed

    assert len(tools.list_actions()) == 4
    assert len(tools.list_actions(kind="render_track")) == 1
    assert len(tools.list_actions(status="pending")) == 4


def test_mcp_rejects_model_supplied_path(tmp_path: Path) -> None:
    tools = ActionMCPTools(ActionLedger(ArtistMatrixSettings(data_root=tmp_path)))

    with pytest.raises(ValueError, match="model-supplied paths"):
        tools.propose_track_render(
            "neon-wasteland",
            {
                "persona_slug": "neon-wasteland",
                "title": "Signal Burn",
                "audio_path": "/tmp/escape.mp3",
            },
        )


def test_mcp_list_limit_is_bounded(tmp_path: Path) -> None:
    tools = ActionMCPTools(ActionLedger(ArtistMatrixSettings(data_root=tmp_path)))

    with pytest.raises(ValueError, match="between 1 and 500"):
        tools.list_actions(limit=0)


def test_product_reads_are_settings_derived(tmp_path: Path) -> None:
    settings = ArtistMatrixSettings(data_root=tmp_path)
    artists = tmp_path / "artists"
    tracks = artists / "neon-wasteland" / "tracks"
    artists.mkdir(parents=True)
    tracks.mkdir(parents=True)
    (artists / "neon-wasteland.json").write_text(
        json.dumps({"name": "Neon Wasteland", "slug": "neon-wasteland"}),
        encoding="utf-8",
    )
    (tracks / "signal-burn.json").write_text(
        json.dumps({"title": "Signal Burn"}),
        encoding="utf-8",
    )
    tools = ActionMCPTools(ActionLedger(settings))

    assert tools.list_artists()[0]["slug"] == "neon-wasteland"
    assert tools.get_artist("neon-wasteland")["name"] == "Neon Wasteland"
    assert tools.list_tracks("neon-wasteland")[0]["track_slug"] == "signal-burn"
    assert tools.get_track("neon-wasteland", "signal-burn")["title"] == "Signal Burn"
    with pytest.raises(ValueError, match="simple lowercase slug"):
        tools.get_artist("../escape")


def test_fastmcp_registration_matches_public_allowlist(tmp_path: Path) -> None:
    server = build_mcp_server(ArtistMatrixSettings(data_root=tmp_path))

    registered = {tool.name for tool in asyncio.run(server.list_tools())}

    expected = set(
        build_mcp_tool_handlers(
            ActionMCPTools(ActionLedger(ArtistMatrixSettings(data_root=tmp_path)))
        )
    )
    assert registered == expected
    assert not any(
        forbidden in name for name in registered for forbidden in ("approve", "execute", "reject")
    )


def test_project_codex_config_pins_the_same_tool_allowlist() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((project_root / ".codex" / "config.toml").read_text(encoding="utf-8"))
    server = config["mcp_servers"]["artist_matrix"]

    assert tuple(server["enabled_tools"]) == MCP_TOOL_ALLOWLIST
    assert server["required"] is True
    assert server["default_tools_approval_mode"] == "auto"
    assert config["default_permissions"] == CODEX_PERMISSION_PROFILE
    permissions = config["permissions"][CODEX_PERMISSION_PROFILE]
    assert permissions["filesystem"][":minimal"] == "read"
    assert permissions["filesystem"][":workspace_roots"] == {".": "read"}
    assert permissions["network"] == {"enabled": False}
    assert all(config["features"][feature] is False for feature in DISABLED_CODEX_FEATURES)
    assert config["agents"]["enabled"] is False
    assert config["tools"]["web_search"] is False
    assert config["web_search"] == "disabled"
