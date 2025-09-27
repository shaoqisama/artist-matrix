# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Setup & Environment:**
- Install dependencies: `uv sync --all-extras` (requires Python 3.12+, uv)
- Activate environment: `source .venv/bin/activate` or prefix commands with `uv run`
- Launch TUI: `uv run python -m artist_matrix.tui`

**Quality Checks (run before PRs):**
- Full verification: `uv run make verify` (lint + type-check + test)
- Lint only: `uv run make lint` (ruff check)
- Type checking: `uv run make type-check` (mypy)
- Format code: `uv run make format` (ruff format)
- Tests only: `uv run make test` (pytest)

**Focused Testing:**
- Run specific test: `uv run pytest tests/path/to/test.py`
- Run by pattern: `uv run pytest -k "test_pattern"`
- Update snapshots: Update files in `tests/tui/snapshots/` when UI changes

## Architecture Overview

Artist Matrix is a terminal-forward agent framework for AI music persona creation and distribution. The system is organized around four main agents:

**Core Agents:**
- **Soul Forge** (`src/artist_matrix/soul_forge/`): Persona creation with DeepSeek LLM integration, manifest persistence
- **Creation Engine** (`src/artist_matrix/creation_engine/`): Track ideation, Suno audio generation, workflow orchestration
- **Echo Chamber** (`src/artist_matrix/echo_chamber/`): Social amplification planning and analytics
- **World Stage** (`src/artist_matrix/world_stage/`): Distribution pipeline and release management

**Shared Infrastructure:**
- **State Management** (`src/artist_matrix/state/`): Pydantic schemas, settings, job orchestration
- **TUI Interface** (`src/artist_matrix/tui/`): Terminal interface with session logging
- **Interfaces** (`src/artist_matrix/interfaces/`): Protocol definitions for external integrations

## Key Data Flow

1. **Persona Creation**: Soul Forge generates artist manifests (`data/artists/<slug>.json`) using DeepSeek LLM
2. **Track Production**: Creation Engine uses persona context for ideation chat, builds Suno payloads, manages audio rendering
3. **Session State**: TUI maintains `track_brief` (CreationBrief) and `campaign_plan` (SocialCampaign) for downstream handoffs
4. **Logging**: All agents support structured logging (persona, Suno, TUI sessions) to `logs/` directories

## Environment Configuration

**Required Environment Variables:**
- `ARTIST_MATRIX_PERSONA_PROVIDER/MODEL/API_KEY` - DeepSeek LLM integration
- `ARTIST_MATRIX_CREATION_AUDIO_PROVIDER/MODEL/API_KEY/BASE_URL` - Suno audio generation
- `ARTIST_MATRIX_TUI_LOG_DIR` - Session logging (defaults to `logs/tui`)

**Optional Logging:**
- `ARTIST_MATRIX_PERSONA_LOG_DIR` - DeepSeek request/response artifacts
- `ARTIST_MATRIX_CREATION_AUDIO_LOG_DIR` - Suno API interaction logs

## Important File Locations

**Prompt Templates:**
- `prompts/persona/` - DeepSeek persona generation prompts
- `prompts/creation/ideation_system.md` - Creation Engine chat system prompt

**Generated Data:**
- `data/artists/` - Artist manifests and per-artist subdirectories
- `data/artists/<slug>/drafts/` - Creation workbench draft persistence
- `data/artists/<slug>/tracks/` - Generated audio files and metadata

**Configuration:**
- `pyproject.toml` - Dependencies, tool config (ruff line-length: 100, Python 3.11+)
- `AGENTS.md` - Detailed development guidelines and architecture

## TUI Workflow Patterns

**Creation Workbench Chat Commands:**
- `/adopt` - Accept AI's structured JSON suggestions into draft
- `/edit <field>: <value>` - Manual field updates
- `/show` - Display current draft status
- `/finalize` - Preview Suno payload before rendering

**Navigation Flow:**
- Main menu → Generate/Select Avatar → Creation Workbench/Echo Chamber
- Back/edit navigation supported in multi-step wizards
- Session state preserved for downstream agent handoffs

## Testing Strategy

- **Unit Tests**: Mirror package structure in `tests/`
- **Integration Tests**: End-to-end workflows in `tests/e2e/`
- **TUI Tests**: Snapshot-based regression testing with iterator-driven input simulation
- **Mocking**: External API calls (DeepSeek, Suno) use dependency injection for test isolation

## Code Style Guidelines

- Follow ruff formatting (line length 100, double quotes)
- Use Pydantic models for all data schemas
- Type hints required (mypy strict mode)
- Imports organized by ruff standards
- Keep agent modules focused on single responsibilities