# Artist Matrix

[![CI](https://github.com/shaoqisama/artist-matrix/workflows/CI/badge.svg)](https://github.com/shaoqisama/artist-matrix/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Artist Matrix is a terminal-forward agent framework for crafting AI-first music personas and delivering releases across creative, social, and distribution channels.

## Getting Started
1. Install dependencies with `uv sync --all-extras` (requires Python 3.12+, uv).
2. Activate the environment (`source .venv/bin/activate`) or prefix commands with `uv run`.
3. Run quality checks via `uv run make verify` before opening pull requests.
4. Launch the retro TUI prototype: `uv run python -m artist_matrix.tui`.
5. Optional: set `ARTIST_MATRIX_PERSONA_PROVIDER`, `ARTIST_MATRIX_PERSONA_MODEL`, `ARTIST_MATRIX_PERSONA_API_KEY`, `ARTIST_MATRIX_AVATAR_PROVIDER`, `ARTIST_MATRIX_AVATAR_MODEL` / `ARTIST_MATRIX_AVATAR_API_KEY`, and the audio knobs (`ARTIST_MATRIX_CREATION_AUDIO_PROVIDER`, `ARTIST_MATRIX_CREATION_AUDIO_MODEL`, `ARTIST_MATRIX_CREATION_AUDIO_API_KEY`, `ARTIST_MATRIX_CREATION_AUDIO_BASE_URL`, `ARTIST_MATRIX_CREATION_AUDIO_CALLBACK_URL`, `ARTIST_MATRIX_CREATION_AUDIO_LOG_DIR`) to swap in custom LLM, diffusion, or audio connectors (default `stub`).

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
- Generate Avatar wizard with back/edit navigation plus optional DeepSeek refinement chat for visual palette, narrative tone, and safety-note capture.
- DeepSeek integration reads prompt templates from `prompts/persona/` and calls the configured API endpoint when the provider and key are set.
- Optional logging: set `ARTIST_MATRIX_PERSONA_LOG_DIR` to capture DeepSeek request/response JSON artifacts for debugging.
- New TUI options let you jump straight into Creation Engine or Echo Chamber with pre-filled briefs and campaign beats after forging/selecting a persona.
- Creation Engine now invokes provider-backed audio (`stub` or `suno`) directly from the TUI, persisting track manifests and surfacing artifact paths on completion.
- Suno integration downloads every returned take, saving alternates alongside the primary track and noting them in the manifest/log summary.
- "Creation Workbench" adds a persona-aware chat loop and editable draft so you can shape Suno prompts (with revisions saved to `data/artists/<slug>/drafts/`). Configure DeepSeek keys to get AI suggestions; otherwise a local heuristic responds. Use "Finalize draft" to preview the Suno payload before rendering. Adjust the LLM system prompt under `prompts/creation/ideation_system.md` if you want different JSON fields.
- Set `ARTIST_MATRIX_TUI_LOG_DIR=./logs/tui` (or another path) to capture each console session as JSONL for debugging/replay.
- Track production with lyric/audio/artwork orchestration (Creation Engine).
- Social amplification planning and analytics stubs (Echo Chamber).
- Distribution pipeline integration and release manifests (World Stage).
- Workflow graph and integration test validating end-to-end hand-offs.
