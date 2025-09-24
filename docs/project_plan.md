# Implementation Plan

## Milestone 0: Repository Foundations
- [x] Scaffold Python package `artist_matrix` with `src/artist_matrix/__init__.py` and `pyproject.toml` configured for Python 3.11, `uv`, `ruff`, and `pytest`.
- [x] Create `Makefile` with `verify`, `lint`, `type-check`, and `test` targets wired to `uv run` commands.
- [x] Establish `assets/`, `tests/`, and `docs/workflows.md` placeholders plus `state/` and `interfaces/` modules.
- [x] Automate CI stub (e.g., GitHub Actions `uv run make verify`) once core checks pass locally.

## Milestone 1: Unified TUI Shell
- [x] Build `artist_matrix/tui/__main__.py` launching textual or prompt_toolkit-based interface styled in post-apocalyptic 8-bit theme.
- [x] Implement navigation options: "Generate Avatar" (routes to Soul Forge flow) and "Select Avatar" (lists stored profiles).
- [x] Add ASCII art headers, color palette constants, and retro status indicators under `assets/tui/`.
- [x] Write snapshot-based TUI regression tests in `tests/tui/test_shell.py` using textual's testing harness or `pytest` golden files.


## Milestone 2: Soul Forge Agent
- [x] Design `artist_matrix/soul_forge/` module with persona schema (`ArtistProfile`) and creation workflow orchestrator.
- [x] Integrate LLM routing stubs (using dependency injection for DeepSeek/Claude connectors) and SDXL prompt generation placeholders.
- [x] Persist generated profiles to `data/artists/<slug>.json` with manifest metadata.
- [x] Cover schema validation and happy-path flow via `tests/soul_forge/test_creation.py`, mocking external calls.

## Milestone 3: Creation Engine Agent
- [x] Implement `artist_matrix/creation_engine/` handling lyric generation, Suno API hooks, and artwork requests.
- [x] Provide queue-friendly job definitions in `state/jobs.py` and synchronous fallbacks.
- [x] Add orchestrated flow tests plus artifact manifest assertions under `tests/creation_engine/`.

## Milestone 4: Echo Chamber Node
- [x] Create `artist_matrix/echo_chamber/` for social posting templates, scheduling, and fan interaction responses.
- [x] Abstract API clients with protocol interfaces so they can be mocked easily.
- [x] Supply content planning tests validating tone consistency and queueing logic.

## Milestone 5: World Stage Node
- [x] Build `artist_matrix/world_stage/` managing distribution payloads, metadata validation, and analytics ingestion.
- [x] Add storage adapters for streaming and storefront integrations following shared interface contracts.
- [x] Ensure regression coverage for release pipelines in `tests/world_stage/`.

## Milestone 6: Workflow Integration & State Management
- [x] Implement LangGraph state machine in `artist_matrix/state/graph.py` connecting all agents.
- [x] Centralize shared prompts, enums, and settings using Pydantic models in `state/schemas.py` and `state/settings.py`.
- [x] Introduce job orchestration utilities and error recovery patterns documented in `docs/workflows.md`.
- [x] Cover integration paths with end-to-end tests under `tests/integration/` using fixture data.

## Milestone 7: Documentation & Operational Playbook
- [x] Expand `docs/workflows.md` with sequence diagrams, queue lifecycle, and approval gates per milestone.
- [x] Add `docs/agents/` subfolder housing per-agent configuration guides and prompt samples.
- [x] Keep `AGENTS.md` synchronized with this plan, listing expectations and checklists aligned to each milestone.
- [x] Prepare onboarding README updates summarizing setup, verified commands, and release cadence.

## Milestone 8: Generate Avatar Flow Refinement
- [x] **User Flow Audit**: Map each prompt/confirmation required to gather persona traits (name, genre, mood, influences) referencing `docs/project_outline.md`.
- [x] **Input Capture Implementation**: Extend `TuiApp` with a multi-step wizard, validating inputs, saving drafts, and presenting a summary before submission.
- [x] **Soul Forge Integration**: Invoke `SoulForgeService.generate` with captured data, surface progress states, and render success/error feedback inline.
- [x] **Avatar Preview Rendering**: Persist avatar blueprint data, display prompt/seed summaries or ASCII placeholders, and prep for future image embedding.
- [x] **Persistence & Navigation**: Store manifest paths in session state to enable immediate hand-off to creation flows; support cancellation/back navigation gracefully.
- [x] **Testing & Telemetry**: Add flow tests in `tests/tui/test_generate_flow.py` mocking Soul Forge responses and track instrumentation hooks for debugging.

## Milestone 9: External Persona & Avatar Connectors
- [x] Replace fallback persona generator with routed LLM clients (DeepSeek/Claude) conforming to `interfaces/creative.PersonaGenerator`.
- [x] Swap `_SimpleAvatarGenerator` for SDXL or similar diffusion adapters returning asset paths and metadata.
- [x] Load API credentials via `ArtistMatrixSettings`; document required env vars in `docs/agents/soul_forge.md` and `README.md`.
- [x] Update integration tests to mock external services while verifying prompt payloads and manifest enrichment.

## Milestone 10: Wizard UX Enhancements
- [x] Add step navigation (back/edit) and confirmation screens so users can revise inputs before forging.
- [x] Capture additional persona attributes (visual palettes, narrative tone, safety guidelines) aligned with `docs/project_outline.md`.
- [x] Persist draft state in `SessionState` to resume cancelled sessions without re-entry.
- [x] Expand TUI regression tests to cover alternate flows, validation errors, and cancellation recovery.

- [x] Implement `DeepSeekPersonaConnector` supporting synchronous “one-shot” refinement plus iterative chat responses, with retry/backoff and safety checks (profane content, guardrails).

## Milestone 12: TUI Avatar Selection UX
- [x] Enumerate stored personas from `data/artists/` (respecting the configured data root) and display them in a friendly list with key metadata.
- [x] Allow users to preview selected manifest details (lyric/visual styles, avatar assets) before confirming the selection.
- [x] Persist the chosen persona in session state for downstream flows (Creation Engine, Echo Chamber, World Stage).
- [x] Handle missing/invalid manifests gracefully with retry prompts and logging.
- [x] Expand TUI tests covering selection flow, empty archive handling, and manifest preview output.

## Milestone 13: Post-Forge Hand-off Automation
- [x] Extend the main TUI menu with dedicated entries for Creation Engine (track briefs) and Echo Chamber (campaigns), using the currently selected persona.
- [x] Offer immediate follow-up prompts after forging a persona to jump into the chosen workflow without returning to the main menu.
- [x] Pre-populate brief/campaign templates with persona metadata (genre, mood, tags, safety notes) and persist breadcrumbs for automation.
- [x] Expand integration tests to cover hand-offs and document the workflow in README/agents/workflows guides.

## Milestone 14: Suno-Powered Track Production
- [x] Implement `SunoAudioGenerator` adhering to `AudioGenerator`, handling job submission, polling, error retries, and asset downloads to `data/artists/<slug>/tracks/`.
- [x] Extend settings/env support (`ArtistMatrixSettings`, `.env.example`) with `ARTIST_MATRIX_CREATION_AUDIO_PROVIDER=suno`, API key, and endpoint configuration.
- [x] Wire the Creation Engine and TUI "Launch Creation" action to invoke Suno when provider is set, displaying progress/state changes in the shell.
- [x] Backfill tests with Suno fixtures (recorded responses) and update `docs/agents/creation_engine.md` plus `README.md` quick-start notes for real audio generation.

## Milestone 15: Creation Engine Telemetry & Logging
- [x] Add structured logging to the Creation Engine, capturing request/response metadata (submission payload, polling snapshots, completion summary) without leaking secrets.
- [x] Introduce `ARTIST_MATRIX_CREATION_AUDIO_LOG_DIR` (settings + `.env.example`) and persist Suno transcripts to rotating JSON/text files when configured.
- [x] Surface log file hints in the TUI after track generation to guide debugging workflows.
- [x] Extend connector/unit tests to assert log artefacts, and document the logging workflow in `docs/agents/creation_engine.md` / `README.md`.
