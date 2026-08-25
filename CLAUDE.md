# CLAUDE.md

This file gives coding agents a compact project guide. `AGENTS.md` and
`docs/architecture_codex_native.md` are the authoritative architecture and contribution references.

## Development commands

```bash
uv sync --all-extras --frozen
uv run make verify
uv run pytest tests/agent_runtime
```

Use `ruff` for lint/format, `mypy` for source type checks, and pytest for all tests. Tests must not
require live provider keys or Codex authentication.

## Product commands

```bash
uv run artist-matrix login
uv run artist-matrix doctor
uv run artist-matrix
uv run artist-matrix run --agent soul_forge --scope demo "Create an artist concept"
uv run artist-matrix-legacy
```

The native host injects required MCP settings directly. `.codex/config.toml` mirrors that setup for
other Codex surfaces after project trust.

## Architecture

Artist Matrix is a Codex-native virtual-artist system with five roles:

- Director coordinates the lifecycle.
- Soul Forge develops validated artist identities.
- Creation Engine co-creates track briefs and render proposals.
- Echo Chamber plans reviewable audience campaigns.
- World Stage validates release proposals.

The central boundary is `src/artist_matrix/agent_runtime/`:

- `harness.py` defines the provider-neutral runtime protocol.
- `codex.py` is the only module coupled to the public `openai_codex` SDK.
- `service.py` binds roles/scopes to durable threads and injects product boundaries.
- `threads.py` persists only Codex thread IDs; thread history is not canonical product state.
- `definitions.py` and `src/artist_matrix/prompts/agents/` define specialist roles and tools.
- `mcp_server.py` exposes canonical reads and typed proposal creation.
- `actions.py` implements application-owned approval, rejection, retry, and execution.

The MCP surface must stay read/propose-only. Never expose approval, rejection, execution, provider
credentials, shell, arbitrary paths, or filesystem writes. The app-owned Codex home contains only
the Artist Matrix MCP server; shell, web, apps, hooks, plugins, and subagents are disabled. Codex
also runs with deny-all approvals and a read-only sandbox. Consequential work always follows:

`prepare -> review -> approve -> execute`

The host application owns the last three transitions. A pending proposal or agent message is never
proof that a provider operation occurred.

## Domain services and persistence

Existing packages remain canonical domain adapters:

- `soul_forge/` owns `ArtistProfile` and artist manifest persistence.
- `creation_engine/` owns `TrackIdeationDraft`, production services, and track manifests.
- `echo_chamber/` owns campaign planning and social client protocols.
- `world_stage/` owns release validation, distribution protocols, and receipts.
- `state/` owns settings and shared orchestration schemas.

Generated product records live under `data/`. Native proposals default to `data/actions/`; safe
unconfigured execution envelopes use `data/outbox/` and remain explicitly `queued`; the isolated
Codex home and thread bindings default under `.cache/codex-home/`. All paths must be derived from
`ArtistMatrixSettings`, never accepted from model tool arguments.

## Legacy compatibility

`src/artist_matrix/tui/` is retained for migration and existing regression coverage. Launch it with
`artist-matrix-legacy` or `python -m artist_matrix.tui`. New orchestration belongs in
`NativeAgentRuntime`; do not add another provider-specific chat loop to the TUI.

Legacy environment variables for DeepSeek, avatar generation, Suno, Rich/classic mode, and logging
remain supported by domain adapters. Native agents receive none of those credentials through MCP.

## Change checklist

When adding or changing a native capability:

1. Update the canonical domain schema.
2. Add a typed action payload and application adapter for side effects.
3. Add only read/propose MCP tools and validate all slugs/inputs.
4. Update the role definition and versioned prompt together.
5. Add fake-harness, event, MCP allowlist, action transition, and domain tests.
6. Update `docs/workflows.md` and `docs/architecture_codex_native.md`.

Keep `openai-codex` pinned exactly so the Python SDK and bundled CLI runtime cannot drift. Use only
public imports from the package root.
