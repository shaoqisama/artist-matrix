# Repository Guidelines

Use this playbook as the quick-start reference before working on the repo. It mirrors the milestones in `docs/project_plan.md`, but compresses the essentials.

## Project Structure
- Source lives in `src/artist_matrix/`:
  - `tui/` – dual-mode interactive shell (classic + Rich with Alien: Earth theming), assets, session logging helpers.
  - `creation_engine/` – ideation chat, Suno integration, finalize workflow.
  - `soul_forge/` – persona connectors (DeepSeek, stubs) and schema validation.
  - `echo_chamber/`, `world_stage/`, `state/`, `interfaces/` – downstream agents and shared models.
- Generated data is written under `data/` (`artists/`, `avatars/`, per-run `tracks/`); prompt templates under `prompts/`; logs (persona, Suno, TUI) under `logs/`.
- Tests mirror the package layout in `tests/` with scripted end-to-end workflows in `tests/e2e/`.

## Tooling & Environment
- Create a virtualenv with `uv venv --python 3.12 .venv` and install dependencies via `uv sync --all-extras`.
- Run `uv run make verify` (ruff + mypy + pytest + e2e) before every commit.
- Key env vars (`.env`) include persona (`ARTIST_MATRIX_PERSONA_PROVIDER/MODEL/API_KEY/ENDPOINT/LOG_DIR`), avatar (`ARTIST_MATRIX_AVATAR_*`), audio (`ARTIST_MATRIX_CREATION_AUDIO_*`), TUI mode (`ARTIST_MATRIX_TUI_MODE=classic|rich`), and optional TUI logging (`ARTIST_MATRIX_TUI_LOG_DIR` – defaults to `logs/tui`). Copy `.env.example` and adjust per provider.

## Architecture Overview
- **Soul Forge** collects persona requirements, calls DeepSeek via `LLMTemplatePersonaGenerator`, normalizes responses, and persists `data/artists/<slug>.json` manifests.
- **Creation Workbench** orchestrates ideation and rendering via `TrackIdeationDraft`:
  1. LLM-guided chat (`creation_engine/llm.py`) returns JSON (title/style/tags/lyrics/notes) that updates the draft.
  2. Manual review/edit preserves the structured brief.
  3. Finalize builds a Suno payload preview (`creation_engine/finalize.py`) before rendering.
  4. Creation Engine submits to Suno (or stub) recording manifests, alternates, and logs.
- Logging hooks (persona, Suno, TUI) provide JSONL transcripts for debugging and replay.

## TUI Workflows
- **Interface Modes**: Classic mode (original terminal UI) or Rich mode (enhanced visuals with Alien: Earth theme - feature branch)
- Main menu offers: `[1] Generate Avatar`, `[2] Select Avatar`, `[3] Creation Workbench`, `[4] Launch Echo`, `[Q] Quit`.
- "Generate" runs the multi-step wizard (back/edit/refine). After forging, jump directly into the workbench or echo flows.
- "Select" enumerates `data/artists/*.json`, previews manifests, and loads the chosen persona into session state.
- "Creation Workbench" is a chat-first loop—type freeform prompts, adopt the AI's structured suggestions with `/adopt`, or `/edit <field>: <value>` to apply manual changes. Use `/show` for status, `/finalize` to preview the Suno payload, then confirm to render. Only adopted/edited fields flow into the payload; transcripts and drafts persist under `data/artists/<slug>/drafts/`.

## Connectors & Logging
- Soul Forge integrates DeepSeek via `DeepSeekPersonaAgent`. Persona prompts live in `prompts/persona/`; creation chat prompt in `prompts/creation/ideation_system.md`.
- Set `ARTIST_MATRIX_PERSONA_LOG_DIR` to capture DeepSeek request/response JSON; list fields are coerced safely.
- Avatar generation uses stub diffusion by default; customize via settings/logs if needed.
- Enable TUI session logging (`ARTIST_MATRIX_TUI_LOG_DIR`) to capture redacted JSONL transcripts (`logs/tui/session_<timestamp>.jsonl`).

## Downstream Handoffs
- Session stores `track_brief` (`CreationBrief`) and `campaign_plan` (`SocialCampaign`) seeded from persona metadata. Creation/Echo menus print these suggestions for downstream work.
- Future automation (Milestone 13+) should wire these suggestions into real job submissions or API calls.

## Style & Testing
- Code style: ruff for lint/format, mypy strict enough to catch typed errors. Keep imports organized, avoid unused dependencies.
- Tests: TUI flows rely on iterator-driven input; ensure new menu paths have coverage. Scripted E2E runs (`tests/e2e/test_tui_workbench.py`) exercise persona → ideation → finalize → render.
- Use `pytest -k` to run focused suites; snapshot tests require updating files in `tests/tui/snapshots/` when UI intentionally changes.

## Contribution Rhythm
- Branch from `main`, keep commits small and imperative (e.g., `add echo handoff menu`).
- Update `docs/project_plan.md` checkboxes as soon as milestone tasks land.
- Document new behavior in `docs/workflows.md` or `docs/agents/` and refresh `README.md` when UX/CLI flows change.
