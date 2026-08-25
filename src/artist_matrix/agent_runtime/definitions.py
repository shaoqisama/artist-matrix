"""Definitions for the specialist agents in Artist Matrix."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class AgentRole(str, Enum):
    """The native agent roles exposed by Artist Matrix."""

    director = "director"
    soul_forge = "soul_forge"
    creation_engine = "creation_engine"
    echo_chamber = "echo_chamber"
    world_stage = "world_stage"


class AgentDefinition(BaseModel):
    """Configuration and product boundary for one specialist agent."""

    model_config = ConfigDict(frozen=True)

    role: AgentRole
    title: str
    description: str
    instruction_file: str
    allowed_tools: tuple[str, ...]

    def load_instructions(self, prompts_root: Path) -> str:
        path = prompts_root / self.instruction_file
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise RuntimeError(f"Agent instructions are missing: {path}") from exc


PRODUCT_READ_TOOLS = (
    "list_artists",
    "get_artist",
    "list_tracks",
    "get_track",
    "list_actions",
    "get_action",
)

PROPOSAL_TOOLS = (
    "propose_artist_profile",
    "propose_track_render",
    "propose_social_campaign",
    "propose_release",
)

MCP_TOOL_ALLOWLIST = PRODUCT_READ_TOOLS + PROPOSAL_TOOLS


AGENT_DEFINITIONS: dict[AgentRole, AgentDefinition] = {
    AgentRole.director: AgentDefinition(
        role=AgentRole.director,
        title="Artist Matrix Director",
        description="Coordinates the complete virtual-artist lifecycle.",
        instruction_file="agents/director.md",
        allowed_tools=MCP_TOOL_ALLOWLIST,
    ),
    AgentRole.soul_forge: AgentDefinition(
        role=AgentRole.soul_forge,
        title="Soul Forge",
        description="Develops coherent virtual-artist identities.",
        instruction_file="agents/soul_forge.md",
        allowed_tools=PRODUCT_READ_TOOLS + ("propose_artist_profile",),
    ),
    AgentRole.creation_engine: AgentDefinition(
        role=AgentRole.creation_engine,
        title="Creation Engine",
        description="Co-creates track concepts and production proposals.",
        instruction_file="agents/creation_engine.md",
        allowed_tools=PRODUCT_READ_TOOLS + ("propose_track_render",),
    ),
    AgentRole.echo_chamber: AgentDefinition(
        role=AgentRole.echo_chamber,
        title="Echo Chamber",
        description="Plans audience campaigns in the artist's voice.",
        instruction_file="agents/echo_chamber.md",
        allowed_tools=PRODUCT_READ_TOOLS + ("propose_social_campaign",),
    ),
    AgentRole.world_stage: AgentDefinition(
        role=AgentRole.world_stage,
        title="World Stage",
        description="Validates and prepares release distribution.",
        instruction_file="agents/world_stage.md",
        allowed_tools=PRODUCT_READ_TOOLS + ("propose_release",),
    ),
}


def get_agent_definition(role: AgentRole | str) -> AgentDefinition:
    """Return the immutable definition for ``role``."""

    normalized = role if isinstance(role, AgentRole) else AgentRole(role)
    return AGENT_DEFINITIONS[normalized]


__all__ = [
    "AGENT_DEFINITIONS",
    "MCP_TOOL_ALLOWLIST",
    "PRODUCT_READ_TOOLS",
    "PROPOSAL_TOOLS",
    "AgentDefinition",
    "AgentRole",
    "get_agent_definition",
]
