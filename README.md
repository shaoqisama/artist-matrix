# Artist Matrix

Artist Matrix is a terminal-forward agent framework for crafting AI-first music personas and delivering releases across creative, social, and distribution channels.

## Getting Started
1. Install dependencies with `uv sync --all-extras` (requires Python 3.12+, uv).
2. Activate the environment (`source .venv/bin/activate`) or prefix commands with `uv run`.
3. Run quality checks via `uv run make verify` before opening pull requests.
4. Launch the retro TUI prototype: `uv run python -m artist_matrix.tui`.
5. Optional: set `ARTIST_MATRIX_PERSONA_PROVIDER`, `ARTIST_MATRIX_PERSONA_MODEL`, `ARTIST_MATRIX_PERSONA_API_KEY`, `ARTIST_MATRIX_AVATAR_PROVIDER`, and `ARTIST_MATRIX_AVATAR_MODEL` / `ARTIST_MATRIX_AVATAR_API_KEY` to swap in custom LLM or diffusion connectors (default `stub`).

## Project Layout
- `src/artist_matrix/`: Core packages for each agent node and shared state.
- `docs/agents/`: Operational guides for Soul Forge, Creation Engine, Echo Chamber, and World Stage.
- `docs/workflows.md`: End-to-end pipeline notes, campaign cadences, and release diagrams.
- `data/`: Generated manifests for artists, tracks, and releases (git-tracked placeholders).
- `tests/`: Unit, integration, and snapshot suites.

## Milestones
The repository is organized around the staged roadmap in `docs/project_plan.md`. Each milestone introduces new services, manifests, and tests that build toward a full artist pipeline.

## Contributing
- Follow the guidance in `AGENTS.md` for code style, testing, and PR expectations.
- Extend or add agent docs under `docs/agents/` when modifying behavior.
- Update `docs/workflows.md` and integration tests whenever cross-agent contracts change.

## Status
Current implementation includes:
- Persona creation with manifest persistence (Soul Forge).
- Generate Avatar wizard with back/edit navigation plus visual palette, narrative tone, and safety-note capture.
- Track production with lyric/audio/artwork orchestration (Creation Engine).
- Social amplification planning and analytics stubs (Echo Chamber).
- Distribution pipeline integration and release manifests (World Stage).
- Workflow graph and integration test validating end-to-end hand-offs.
