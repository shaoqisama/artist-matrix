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

## Milestone 16: Persona-Aware Track Ideation
- [x] Add a `TrackIdeationDraft` schema and persist iterative briefs to `SessionState` plus disk for reuse.
- [x] Extend the TUI Creation menu with a chat-driven “Discuss track concept” flow that collaborates with an LLM (DeepSeek) seeded by the selected persona.
- [x] Convert the approved draft into Suno-ready payload fields (title/style/instrumental/custom mode, tags, lyrics) before submission and allow manual edits.
- [x] Persist transcripts + final briefs, update documentation (`docs/agents/creation_engine.md`, `README.md`) and add tests covering chat, draft save/load, and Suno hand-off using the curated prompt.

## Milestone 17: Ideation-to-Render Handoff Enhancements
- [x] Capture structured fields (prompt/style/tags/instrumental/lyrics) automatically from LLM replies and surface them in the draft summary for confirmation.
- [x] Add a “Finalize draft” step that locks the curated brief, shows a Suno payload preview, and lets users tweak before rendering.
- [x] Persist finalized briefs separately (e.g., `drafts/<slug>_final.json`) and load them when re-opening the workbench.
- [ ] Expand tests to cover auto-field extraction, finalize flow, and Suno submission using the enriched draft; update docs (README, agent guide) with the improved workflow.

## Milestone 18: end-to-end TUI regression harness
- [x] Build a high-level integration harness that drives the TUI with scripted inputs (e.g., `expect`/pty-based runner) covering persona creation, ideation, finalize, and Suno render, using environment toggles to mock external calls.
- [ ] Add fixture scripts for persona + Suno connectors so we can replay collaborative sessions without hitting real APIs; parameterize to optionally hit live services when credentials are present.
- [ ] Integrate the harness into CI (`uv run make verify-e2e`) and document local usage for contributors who want to smoke-test the full experience without manual input.

## Milestone 19: TUI Interaction Logging & Analytics
- [x] Add configurable session logging for the TUI (input/output transcript) that redacts sensitive values and stores JSON lines under `logs/tui/<timestamp>.jsonl`.
- [x] Surface log file paths to the user after each session and document retrieval/rotation guidance in README + docs/agents.
- [ ] Extend e2e tests to assert log emission and add a CI-friendly toggle to disable logging when not needed.

## Milestone 20: Chat‑First Creation Workbench (User‑Confirmed Only)
- [x] Single chat screen in Workbench: show LLM guidance text plus an optional fenced JSON block for proposed field updates.
- [x] Draft model (minimal): `title`, `style`, `tags[]`, `lyrics`, `notes`, `duration_sec`, `allow_instrumental`, `ref_url`; seed from persona when present.
- [x] Parser: extract only recognized fields from the fenced JSON; ignore malformed/unknown keys without erroring.
- [x] Strict adopt/edit flow: never auto‑apply; support `/adopt`, `/edit <field>: <value>`, `/show`, `/finalize`, `/undo`, `/help`.
- [x] Finalize preview: build Suno payload solely from Draft; readiness requires `title`, `tags`, and either `lyrics` or detailed `style/notes`.
- [x] Render step: submit via Suno (or stub), persist final Draft + payload + manifest under the selected artist’s track run; log chat turns and accepted deltas.
- [x] Tests: unit (parser + Draft validators), TUI snapshots (adopt/edit/finalize), and one e2e happy path asserting Suno payload validity.

### PR‑Sized Breakdown (Milestone 20)
- [x] Draft model + validation: add model, seed from persona, unit tests.
- [x] Chat UI + JSON parser: show LLM text + fenced JSON, parse into deltas, happy/edge tests.
- [x] Adopt/edit/undo commands: update Draft only on accept/edit, snapshot tests.
- [x] Finalize + payload builder: readiness checks and preview, unit tests for builder.
- [x] Render + persistence + logging: submit via Suno/stub, persist artefacts, log turns/adoptions.
- [x] E2E happy path: persona → chat → adopt → finalize → render (stub), assert payload + files written.

## Milestone 21: Workbench Polish & Guardrails
- [ ] Diff preview before adopt (side‑by‑side for text fields; key‑level for metadata) to reduce accidental changes.
- [ ] Missing‑fields coach: after assistant replies, show what's still needed; include readiness status in `/show`.
- [ ] Lightweight safety checks (profanity toggle, basic copyright hints) with clear user feedback; non‑blocking unless configured.
- [ ] Human‑friendly validation errors mapped from Pydantic; keep user in chat on failure with actionable hints.
- [ ] Telemetry: count adoptions/undos; gate via `ARTIST_MATRIX_TUI_LOG_DIR`.
- [ ] Additional tests for diffs, safety toggles, and error messages.

## Milestone 22: TUI Modernization with Rich Framework (Visual Shell Only)
- [x] **Setup & Environment**: Create feature branch `feature/rich-tui` and add Rich dependency to `pyproject.toml` with version constraints.
- [x] **Parallel Implementation**: Create new module `src/artist_matrix/tui/rich_app.py` alongside existing `app.py` using adapter pattern for compatibility.
- [x] **Enhanced Main Menu**: Replace ASCII banner with Rich Panel containing styled art, Table layout for menu options with icons, gradient colors and borders.
- [ ] **Interactive Wizards**: Convert persona creation to Rich Prompt with validation, Live display for real-time feedback, Columns layout for comparisons.
- [ ] **Creation Workbench Enhancement**: Implement Rich Console with syntax highlighting for chat, Markdown rendering for AI responses, tabbed interface for draft/chat/preview.
- [x] **Visual Theme (Alien: Earth)**: Apply retro-futurist dystopia aesthetic per `docs/tui_visual_guide.md`:
  - Color palette: Acid green (#00FF7F) for warnings/active text, Electric blue (#1E90FF) for system info, Rust/gray for borders
  - ASCII art: Xenomorph silhouettes, Weyland-Yutani [WY] tags, hazard stripes (██░░██), radar blips (* . *)
  - Typography: Wide-spaced ALIEN-style caps for titles, monospaced green-on-black terminal font
  - Motion effects: Slow typing reveals, glitch/static bursts, occasional "jump-scare" rapid scrolls
  - Layout modes: Ship/claustrophobic (dense panels) vs Earth/open (wider spacing)
  - Atmosphere: Interface feels "alive but unstable" with eerie neon highlights on dark backgrounds
- [x] **Feature Flag System**: Environment variable toggle `ARTIST_MATRIX_TUI_MODE=rich|classic` with backward compatibility maintained.
- [x] **Testing Strategy**: Keep existing tests for classic mode, create parallel test suite for Rich implementation, snapshot testing for visual components.
- [x] **Documentation & Migration**: Update CLAUDE.md and README with screenshots of both modes, gradual rollout plan with Rich as opt-in initially.
- [x] **Safety & Rollback**: Maintain all existing interfaces and data structures, comprehensive test coverage, rollback capability via environment variable.

## Milestone 23: Rich TUI Full Feature Implementation
- [x] **Core Infrastructure**: Import session management components (`SessionState`, `PersonaWizardDraft`) and initialize all services (Soul Forge, Creation Engine).
- [x] **Persona Generation Wizard**: Implement `_collect_persona_draft` with Rich prompts, validation, back/edit navigation, and progress displays.
- [x] **Avatar Selection Interface**: Create Rich Table browser for personas with preview panels, numbered selection, and session integration.
- [x] **Creation Workbench**: Port chat interface with Rich Console, Markdown rendering, command system (`/adopt`, `/edit`, `/show`, `/finalize`).
- [x] **Echo Chamber Planning**: Implement campaign UI with Rich Tables, post previews, timeline visualization, and scheduling.
- [x] **Service Integration**: Wire all handlers to actual business logic (Soul Forge, Creation Engine, Echo Chamber services).
- [x] **State Persistence**: Ensure session state, drafts, and transcripts work consistently between Rich and classic modes.
- [x] **Comprehensive Testing**: Test each handler, mock external services, validate UI components, ensure feature parity.
- [x] **Documentation**: Update CLAUDE.md with Rich-specific usage, add screenshots, document both modes thoroughly.
- [x] **End-to-End User Flow Testing**: Create comprehensive integration tests in `tests/tui/test_rich_user_flows.py` that simulate complete user journeys (persona creation → selection → workbench → echo chamber) with mocked inputs and verify all UI flows work without crashes or missing methods.

## Milestone 24: Test Performance & Warning Cleanup
- [x] **LLM Test Optimization**: Replace real API calls with MockTrackIdeationLLM for 99%+ speed improvement (20s → 0.14s).
- [x] **User Flow Test Stabilization**: Fix hanging tests caused by insufficient input sequences and incorrect quit commands.
- [x] **Test Infrastructure Enhancement**: Add integration test markers, comprehensive error handling tests, and mock service framework.
- [ ] **DateTime Deprecation Warnings**: Replace all `datetime.utcnow()` calls with `datetime.now(timezone.utc)` for Python 3.12+ compatibility.
- [ ] **Rich Library Warnings**: Configure or suppress "install ipywidgets" warnings in test configuration.
- [ ] **Pydantic Deprecation Warnings**: Address or suppress Pydantic internal datetime warnings through configuration.
- [ ] **Warning Suppression Strategy**: Add pytest filterwarnings configuration for development vs CI environments.
- [ ] **Clean Test Output**: Achieve zero warnings in test output for better debugging and issue visibility.

### Implementation Details for Milestone 24

#### Phase 1: DateTime Modernization (High Priority)
- **Files to update**: 6 source files using `datetime.utcnow()`
  - `src/artist_matrix/creation_engine/ideation.py:62`
  - `src/artist_matrix/soul_forge/profiles.py:77`
  - `src/artist_matrix/creation_engine/llm.py:55`
  - `src/artist_matrix/creation_engine/connectors.py:367`
  - `src/artist_matrix/tui/logging.py:18, 24`
  - `src/artist_matrix/echo_chamber/planner.py:35`
- **Pattern**: Replace `datetime.utcnow()` → `datetime.now(timezone.utc)`
- **Import additions**: Add `timezone` import where needed
- **Impact**: Future-proof code and eliminate ~80 deprecation warnings

#### Phase 2: Test Configuration (Medium Priority)
- **Warning filters**: Add pytest configuration to suppress external library warnings
- **Environment toggles**: Different warning levels for development vs CI
- **Documentation**: Update contribution guidelines for warning-free development

#### Phase 3: Validation (Low Priority)
- **Verification**: Ensure `uv run make verify` produces zero warnings
- **Performance**: Maintain optimized test performance (sub-second LLM tests)
- **Compatibility**: Verify datetime changes don't break existing functionality

 
