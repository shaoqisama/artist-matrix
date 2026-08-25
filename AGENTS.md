# Repository Guidelines

Use this playbook as the quick-start reference before working on the repo. It mirrors the milestones in `docs/project_plan.md`, but compresses the essentials.

## Project Structure
- Source lives in `src/artist_matrix/`:
  - `agent_runtime/` – Codex harness adapter, specialist registry, normalized events, thread
    bindings, action ledger, and read/propose-only MCP server.
  - `tui/` – legacy dual-mode shell (classic + Rich), assets, and session logging helpers.
  - `creation_engine/` – ideation chat, Suno integration, finalize workflow.
  - `soul_forge/` – persona connectors (DeepSeek, stubs) and schema validation.
  - `echo_chamber/`, `world_stage/`, `state/`, `interfaces/` – downstream agents and shared models.
- Generated data is written under `data/` (`artists/`, `actions/`, `outbox/`, per-run `tracks/`);
  packaged specialist instructions live under `src/artist_matrix/prompts/agents/`; legacy prompt
  templates remain under their domain folders; logs (persona, Suno, TUI) live under `logs/`.
- Tests mirror the package layout in `tests/` with scripted end-to-end workflows in `tests/e2e/`.

## Tooling & Environment
- Create a virtualenv with `uv venv --python 3.12 .venv` and install dependencies via
  `uv sync --all-extras --frozen`.
- Run `uv run make verify` (ruff lint/format + mypy + unit tests) before every commit; use
  `uv run make verify-all` for deterministic integration coverage too.
- Sign in once with `uv run artist-matrix login`; `uv run artist-matrix doctor` reports non-secret
  runtime and account metadata. The host injects required MCP settings directly; `.codex/config.toml`
  supplies the matching configuration to other Codex surfaces after project trust.
- Key native env vars include `ARTIST_MATRIX_AGENT_RUNTIME`, `ARTIST_MATRIX_CODEX_MODEL`,
  `ARTIST_MATRIX_CODEX_HOME`, `ARTIST_MATRIX_CODEX_THREAD_STORE`, and
  `ARTIST_MATRIX_ACTION_ROOT`. Provider, TUI mode, and logging settings remain for legacy/domain
  adapters. Copy `.env.example` and adjust as needed.

## Architecture Overview
- **NativeAgentRuntime** is the primary orchestration boundary. It starts/resumes one persistent
  Codex thread per specialist role and product scope, and streams project-owned `RuntimeEvent`s.
- **CodexHarness** is the only SDK-coupled module. Keep `openai-codex` and its pinned runtime at the
  same exact version; use only public root imports. Its app-owned Codex home and empty workspace
  isolate product agents from user tools and repository engineering instructions.
- **Artist Matrix MCP** exposes canonical product reads plus typed proposal creation. It must never
  expose action approval, rejection, execution, provider credentials, shell, or arbitrary paths.
- **ActionStore/ActionExecutor** implement `prepare -> review -> approve -> execute`. Codex creates
  only `pending` records; the host application owns every consequential transition. Missing remote
  adapters enter `queued` with `external_effect=not_executed`, never false completion.
- **Domain services** remain deterministic execution adapters and canonical schema owners. Thread
  history is useful context but never product state.
- See `docs/architecture_codex_native.md` for the complete contract.

## Product Workflows
- **Native CLI**: `artist-matrix` defaults to a persistent Director chat. Use `/agent`, `/scope`,
  `/new`, `/actions`, `/approve`, `/reject`, and `/doctor` inside the session.
- **One-shot turns**: `artist-matrix run --agent <role> --scope <scope> "<prompt>"` streams one
  turn and preserves its thread binding.
- **Legacy modes**: launch the earlier deterministic shell with `artist-matrix-legacy` or
  `ARTIST_MATRIX_AGENT_RUNTIME=legacy`. New orchestration behavior belongs in the native runtime.
- The legacy main menu offers: `[1] Generate Avatar`, `[2] Select Avatar`, `[3] Creation Workbench`, `[4] Launch Echo`, `[Q] Quit`.
- Main menu offers: `[1] Generate Avatar`, `[2] Select Avatar`, `[3] Creation Workbench`, `[4] Launch Echo`, `[Q] Quit`.
- "Generate" runs the multi-step wizard (back/edit/refine). After forging, jump directly into the workbench or echo flows.
- "Select" enumerates `data/artists/*.json`, previews manifests, and loads the chosen persona into session state.
- "Creation Workbench" is a chat-first loop—type freeform prompts, adopt the AI's structured suggestions with `/adopt`, or `/edit <field>: <value>` to apply manual changes. Use `/show` for status, `/finalize` to preview the Suno payload, then confirm to render. Only adopted/edited fields flow into the payload; transcripts and drafts persist under `data/artists/<slug>/drafts/`.

## Connectors & Logging
- Soul Forge integrates DeepSeek via `DeepSeekPersonaAgent`. Packaged persona prompts live in
  `src/artist_matrix/prompts/persona/`; the creation chat prompt lives in
  `src/artist_matrix/prompts/creation/ideation_system.md`.
- Set `ARTIST_MATRIX_PERSONA_LOG_DIR` to capture DeepSeek request/response JSON; list fields are coerced safely.
- Avatar generation uses stub diffusion by default; customize via settings/logs if needed.
- Enable TUI session logging (`ARTIST_MATRIX_TUI_LOG_DIR`) to capture redacted JSONL transcripts (`logs/tui/session_<timestamp>.jsonl`).

## Downstream Handoffs
- Session stores `track_brief` (`CreationBrief`) and `campaign_plan` (`SocialCampaign`) seeded from persona metadata. Creation/Echo menus print these suggestions for downstream work.
- Future automation (Milestone 13+) should wire these suggestions into real job submissions or API calls.

## Style & Testing
- Code style: ruff for lint/format, mypy strict enough to catch typed errors. Keep imports organized, avoid unused dependencies.
- Native runtime/domain tests must inject `AgentHarness` fakes; they must not require live Codex
  authentication or make model calls. Adapter tests should feed deterministic SDK notifications.
- MCP tests must assert the exact allowlist and the absence of approve/execute/reject tools. Action
  tests must cover validation, transition safety, idempotency, failure persistence, and retries.
- Tests: TUI flows rely on iterator-driven input; ensure new menu paths have coverage. Scripted E2E runs (`tests/e2e/test_tui_workbench.py`) exercise persona → ideation → finalize → render.
- Use `pytest -k` to run focused suites; snapshot tests require updating files in `tests/tui/snapshots/` when UI intentionally changes.

## Contribution Rhythm
- Branch from `main`, keep commits small and imperative (e.g., `add echo handoff menu`).
- Update `docs/project_plan.md` checkboxes as soon as milestone tasks land.
- Document new behavior in `docs/workflows.md` or `docs/agents/` and refresh `README.md` when UX/CLI flows change.
