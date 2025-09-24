# Repository Guidelines

Use this playbook as the quick-start reference before working on the repo. It mirrors the milestones in `docs/project_plan.md`, but compresses the essentials.

## Project Structure
- Source lives in `src/artist_matrix/` (`tui/`, `soul_forge/`, `creation_engine/`, `echo_chamber/`, `world_stage/`, `state/`, `interfaces/`).
- Generated data is written under `data/` (`artists/`, `avatars/`), prompt templates under `prompts/`, and API transcripts under `logs/`.
- Tests mirror the package layout in `tests/`; TUI snapshots live in `tests/tui/snapshots/`.

## Tooling & Environment
- Create a virtualenv with `uv venv --python 3.12 .venv` and install dependencies via `uv sync --all-extras`.
- Run `uv run make verify` (ruff + mypy + pytest) before every commit.
- Key env vars (`.env`) include persona (`ARTIST_MATRIX_PERSONA_PROVIDER/MODEL/API_KEY`), avatar (`ARTIST_MATRIX_AVATAR_PROVIDER/MODEL/API_KEY`), and audio generation (`ARTIST_MATRIX_CREATION_AUDIO_PROVIDER/MODEL/API_KEY/BASE_URL/CALLBACK_URL/LOG_DIR`). Copy `.env.example` and adjust per provider.

## TUI Workflows
- Main menu now offers: `[1] Generate Avatar`, `[2] Select Avatar`, `[3] Launch Creation`, `[4] Launch Echo`, `[Q] Quit`.
- "Generate" runs the multi-step wizard. After completion you can jump straight into Creation Engine or Echo Chamber using `[c]` / `[e]`. Select menu options re-use `SessionState` suggestions.
- "Select" enumerates `data/artists/*.json`, previews manifests, and loads the chosen persona (plus avatar) into session state.

## Connectors & Logging
- Soul Forge integrates DeepSeek via `DeepSeekPersonaAgent`. Prompt templates reside in `prompts/persona/`; fallback template is embedded.
- Set `ARTIST_MATRIX_PERSONA_LOG_DIR` to capture request/response JSON and a rolling log. Connector retries 3 times and guards safety notes.
- Avatar generation uses stub diffusion; customize via settings/logs if needed.

## Downstream Handoffs
- Session stores `track_brief` (`CreationBrief`) and `campaign_plan` (`SocialCampaign`) seeded from persona metadata. Creation/Echo menus print these suggestions for downstream work.
- Future automation (Milestone 13+) should wire these suggestions into real job submissions or API calls.

## Style & Testing
- Code style: ruff for lint/format, mypy strict enough to catch typed errors. Keep imports organized, avoid unused dependencies.
- Tests: TUI flows rely on iterator-driven input; ensure new menu paths have coverage (success + empty states).
- Use `pytest -k` to run focused suites; snapshot tests require updating files in `tests/tui/snapshots/` when UI intentionally changes.

## Contribution Rhythm
- Branch from `main`, keep commits small and imperative (e.g., `add echo handoff menu`).
- Update `docs/project_plan.md` checkboxes as soon as milestone tasks land.
- Document new behavior in `docs/workflows.md` or `docs/agents/` and refresh `README.md` when UX/CLI flows change.
