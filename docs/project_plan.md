# Implementation Plan

## Milestone 0: Repository Foundations
- Scaffold Python package `artist_matrix` with `src/artist_matrix/__init__.py` and `pyproject.toml` configured for Python 3.11, `uv`, `ruff`, and `pytest`.
- Create `Makefile` with `verify`, `lint`, `type-check`, and `test` targets wired to `uv run` commands.
- Establish `assets/`, `tests/`, and `docs/workflows.md` placeholders plus `state/` and `interfaces/` modules.
- Automate CI stub (e.g., GitHub Actions `uv run make verify`) once core checks pass locally.

## Milestone 1: Unified TUI Shell
- Build `artist_matrix/tui/__main__.py` launching textual or prompt_toolkit-based interface styled in post-apocalyptic 8-bit theme.
- Implement navigation options: "Generate Avatar" (routes to Soul Forge flow) and "Select Avatar" (lists stored profiles).
- Add ASCII art headers, color palette constants, and retro status indicators under `assets/tui/`.
- Write snapshot-based TUI regression tests in `tests/tui/test_shell.py` using textual's testing harness or `pytest` golden files.


## Milestone 2: Soul Forge Agent
- Design `artist_matrix/soul_forge/` module with persona schema (`ArtistProfile`) and creation workflow orchestrator.
- Integrate LLM routing stubs (using dependency injection for DeepSeek/Claude connectors) and SDXL prompt generation placeholders.
- Persist generated profiles to `data/artists/<slug>.json` with manifest metadata.
- Cover schema validation and happy-path flow via `tests/soul_forge/test_creation.py`, mocking external calls.

## Milestone 3: Creation Engine Agent
- Implement `artist_matrix/creation_engine/` handling lyric generation, Suno API hooks, and artwork requests.
- Provide queue-friendly job definitions in `state/jobs.py` and synchronous fallbacks.
- Add orchestrated flow tests plus artifact manifest assertions under `tests/creation_engine/`.

## Milestone 4: Echo Chamber Node
- Create `artist_matrix/echo_chamber/` for social posting templates, scheduling, and fan interaction responses.
- Abstract API clients with protocol interfaces so they can be mocked easily.
- Supply content planning tests validating tone consistency and queueing logic.

## Milestone 5: World Stage Node
- Build `artist_matrix/world_stage/` managing distribution payloads, metadata validation, and analytics ingestion.
- Add storage adapters for streaming and storefront integrations following shared interface contracts.
- Ensure regression coverage for release pipelines in `tests/world_stage/`.

## Milestone 6: Workflow Integration & State Management
- Implement LangGraph state machine in `artist_matrix/state/graph.py` connecting all agents.
- Centralize shared prompts, enums, and settings using Pydantic models in `state/schemas.py` and `state/settings.py`.
- Introduce job orchestration utilities and error recovery patterns documented in `docs/workflows.md`.
- Cover integration paths with end-to-end tests under `tests/integration/` using fixture data.

## Milestone 7: Documentation & Operational Playbook
- Expand `docs/workflows.md` with sequence diagrams, queue lifecycle, and approval gates per milestone.
- Add `docs/agents/` subfolder housing per-agent configuration guides and prompt samples.
- Keep `AGENTS.md` synchronized with this plan, listing expectations and checklists aligned to each milestone.
- Prepare onboarding README updates summarizing setup, verified commands, and release cadence.

## Milestone 8: Generate Avatar Flow Refinement
- **User Flow Audit**: Map each prompt/confirmation required to gather persona traits (name, genre, mood, influences) referencing `docs/project_outline.md`.
- **Input Capture Implementation**: Extend `TuiApp` with a multi-step wizard, validating inputs, saving drafts, and presenting a summary before submission.
- **Soul Forge Integration**: Invoke `SoulForgeService.generate` with captured data, surface progress states, and render success/error feedback inline.
- **Avatar Preview Rendering**: Persist avatar blueprint data, display prompt/seed summaries or ASCII placeholders, and prep for future image embedding.
- **Persistence & Navigation**: Store manifest paths in session state to enable immediate hand-off to creation flows; support cancellation/back navigation gracefully.
- **Testing & Telemetry**: Author flow tests in `tests/tui/test_generate_flow.py` mocking Soul Forge responses and track instrumentation hooks for debugging.
