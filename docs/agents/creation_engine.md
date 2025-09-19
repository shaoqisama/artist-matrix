# Creation Engine Agent Guide

## Responsibilities
- Generate lyrics, render audio, and produce cover art for tracks.
- Maintain per-track manifests in `data/artists/<slug>/tracks/` with job metadata.
- Surface `TrackManifest` payloads to the workflow graph for downstream release preparation.

## Key Modules
- `src/artist_matrix/creation_engine/service.py`: Orchestrates lyric/audio/artwork jobs and manifest writes.
- `src/artist_matrix/interfaces/production.py`: Protocol definitions for lyric, audio, and artwork generators.
- `src/artist_matrix/state/jobs.py`: Dataclasses describing track and artwork job specs.

## Configuration
- Inject generator implementations into `CreationEngineService`; use `uv run make verify` to ensure they satisfy protocols.
- Use `ARTIST_MATRIX_DATA_ROOT` to relocate manifest and artifact directories when deploying to cloud storage.

## Testing
- Unit tests: `tests/creation_engine/test_service.py` verifies artifact metadata and manifest content.
- Add golden samples in `tests/creation_engine/fixtures/` when extending to new render modes or queue backends.
