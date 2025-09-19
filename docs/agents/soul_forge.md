# Soul Forge Agent Guide

## Responsibilities
- Draft artist personas by routing briefs through persona generators.
- Persist validated `ArtistProfile` manifests and avatar metadata under `data/artists/`.
- Provide profile context to downstream nodes via `ArtistManifest` schemas.

## Key Modules
- `src/artist_matrix/soul_forge/profiles.py`: Immutable profile schema utilities.
- `src/artist_matrix/soul_forge/service.py`: Persona + avatar orchestration and manifest persistence.
- `src/artist_matrix/interfaces/creative.py`: Protocols for persona and avatar connectors.

## Configuration
- Environment variables: `ARTIST_MATRIX_DATA_ROOT` overrides manifest storage root.
- Register persona and avatar providers in `SoulForgeService` wiring; use dependency injection for model clients.

## Testing
- Unit tests: `tests/soul_forge/test_creation.py` covers manifest writes and connector calls.
- Add fixtures under `tests/fixtures/` for new persona templates or avatar prompt samples.
