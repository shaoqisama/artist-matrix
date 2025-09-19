# Repository Guidelines

Consult `docs/project_plan.md` before starting any task; each milestone below mirrors the plan and adds execution tips.

## Milestone 0 – Repository Foundations
- Scaffold `src/artist_matrix/`, `assets/`, `tests/`, and shared `interfaces/` + `state/` packages exactly as the plan specifies.
- Use `uv venv --python 3.11 .venv` and `uv sync --all-extras`; run linting and tests with `uv run make verify` before every commit.
- Adopt `ruff format` + `ruff check`, 4-space indentation, snake_case modules, PascalCase classes, and UPPER_CASE constants from day one.

## Milestone 1 – Unified TUI Shell
- Build the retro terminal UI under `artist_matrix/tui/`, pulling palette constants and ASCII art from `assets/tui/`.
- Maintain golden snapshots for navigation and theming in `tests/tui/`, updating them only when UX changes are intentional.

## Milestone 2 – Soul Forge Agent
- Implement profile schemas and generation flows in `artist_matrix/soul_forge/`; persist JSON manifests to `data/artists/` per profile slug.
- Mock LLM and SDXL calls in `tests/soul_forge/` to keep runs deterministic; attach prompt fixtures in `tests/fixtures/`.

## Milestone 3 – Creation Engine Agent
- Route lyric, audio, and artwork jobs through `artist_matrix/creation_engine/` while recording artifact metadata in manifests.
- Verify queue hooks and artifact outputs via regression tests in `tests/creation_engine/`, snapshotting representative payloads.

## Milestone 4 – Echo Chamber Node
- House social templates and scheduling logic in `artist_matrix/echo_chamber/`, exposing protocol-based clients for APIs.
- Cover copy tone and scheduling cadence with fixture-backed tests; ensure fallbacks when outbound posts fail.

## Milestone 5 – World Stage Node
- Implement distribution and analytics adapters in `artist_matrix/world_stage/`, sharing interfaces with other nodes.
- Guard release orchestration with tests that validate metadata, storefront payloads, and retry strategies.

## Milestone 6 – Workflow Integration
- Assemble the LangGraph state machine plus shared Pydantic schemas under `artist_matrix/state/`; document flows in `docs/workflows.md`.
- Build integration tests in `tests/integration/` using fixture manifests to exercise cross-node hand-offs and error recovery.

## Milestone 7 – Documentation & Delivery
- Expand and maintain `docs/agents/` when behavior changes; mirror updates in `docs/workflows.md` and sequence diagrams.
- Keep commit summaries short and imperative (`"add tui navigation"`), reference issues, and attach `uv run make verify` output or TUI screenshots in PRs.
- Refresh `README.md` and `docs/project_plan.md` after major milestones so onboarding stays accurate.
