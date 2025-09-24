# Creation Engine Agent Guide

## Responsibilities
- Generate lyrics, render audio, and produce cover art for tracks.
- Maintain per-track manifests in `data/artists/<slug>/tracks/` with job metadata.
- Surface `TrackManifest` payloads to the workflow graph for downstream release preparation.

## Key Modules
- `src/artist_matrix/creation_engine/service.py`: Orchestrates lyric/audio/artwork jobs and manifest writes.
- `src/artist_matrix/creation_engine/connectors.py`: Stub + Suno audio generators, heuristic lyric generator, and factory helpers.
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

## Testing
- Unit tests: `tests/creation_engine/test_service.py` verifies artifact metadata and manifest content.
- Suno connector: `tests/creation_engine/test_suno_generator.py` uses `httpx.MockTransport` to record/poll/download behaviour.
- TUI integration: `tests/tui/test_creation_flow.py` covers the end-user launch path.
- Add golden samples in `tests/creation_engine/fixtures/` when extending to new render modes or queue backends.
