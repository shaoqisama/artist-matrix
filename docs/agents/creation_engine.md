# Creation Engine Agent Guide

## Responsibilities
- Generate lyrics, render audio, and produce cover art for tracks.
- Maintain per-track manifests in `data/artists/<slug>/tracks/` with job metadata.
- Surface `TrackManifest` payloads to the workflow graph for downstream release preparation.
- When a provider returns multiple takes (e.g., Suno dual outputs), download each variant and record alternate audio paths in the manifest.

## Key Modules
- `src/artist_matrix/creation_engine/service.py`: Orchestrates lyric/audio/artwork jobs and manifest writes.
- `src/artist_matrix/creation_engine/connectors.py`: Stub + Suno audio generators, heuristic lyric generator, and factory helpers.
- `src/artist_matrix/creation_engine/ideation.py`: Track ideation drafts, transcripts, and persistence utilities.
- `src/artist_matrix/creation_engine/llm.py`: Optional DeepSeek-powered ideation chat client and helpers (loads `prompts/creation/ideation_system.md`).
- `src/artist_matrix/creation_engine/finalize.py`: Suno payload preview helpers used by the TUI finalize step.
- `src/artist_matrix/interfaces/production.py`: Protocol definitions for lyric, audio, and artwork generators.
- `src/artist_matrix/state/jobs.py`: Dataclasses describing track and artwork job specs.

## Configuration
- Inject generator implementations into `CreationEngineService`; use `build_audio_generator` / `build_lyric_generator` for defaults.
- Configure audio providers via `.env`:
  - `ARTIST_MATRIX_CREATION_AUDIO_PROVIDER` = `stub` or `suno`
  - `ARTIST_MATRIX_CREATION_AUDIO_MODEL` (e.g., `V3_5`, `V4_5`)
  - `ARTIST_MATRIX_CREATION_AUDIO_API_KEY`
  - `ARTIST_MATRIX_CREATION_AUDIO_BASE_URL` (defaults to `https://api.sunoapi.org`)
  - `ARTIST_MATRIX_CREATION_AUDIO_CALLBACK_URL` (required by Suno for async completion notices)
  - `ARTIST_MATRIX_CREATION_AUDIO_LOG_DIR` (write request/response telemetry here)
  - `ARTIST_MATRIX_CREATION_AUDIO_POLL_INTERVAL`, `ARTIST_MATRIX_CREATION_AUDIO_TIMEOUT_SECONDS`
- Use `ARTIST_MATRIX_DATA_ROOT` to relocate manifest and artifact directories when deploying to cloud storage.
- To enable the ideation LLM, set `ARTIST_MATRIX_PERSONA_PROVIDER=deepseek`, supply `ARTIST_MATRIX_PERSONA_API_KEY`, and optionally `ARTIST_MATRIX_PERSONA_LOG_DIR` for request/response capture.
- Finalized briefs are persisted to `data/artists/<slug>/drafts/final_brief.json`; the TUI will load these on subsequent sessions.

## Testing
- Unit tests: `tests/creation_engine/test_service.py` verifies artifact metadata and manifest content.
- Suno connector: `tests/creation_engine/test_suno_generator.py` uses `httpx.MockTransport` to record/poll/download behaviour.
- Ideation store + LLM helper: `tests/creation_engine/test_ideation.py` exercises draft/transcript round-trips and the guidance adapter.
- TUI finalize flow: `tests/tui/test_creation_flow.py::test_creation_finalize_flow` ensures save/render workflow is covered.
- TUI integration: `tests/tui/test_creation_flow.py` covers the end-user launch path.
- Add golden samples in `tests/creation_engine/fixtures/` when extending to new render modes or queue backends.
