# Soul Forge Agent Guide

## Responsibilities
- Draft artist personas by routing briefs through persona generators.
- Persist validated `ArtistProfile` manifests and avatar metadata under `data/artists/`.
- Provide profile context to downstream nodes via `ArtistManifest` schemas.
- Collect extended persona attributes (visual palettes, narrative tone, safety guardrails) via the TUI wizard and propagate them into manifests.
- Support collaborative refinement: after initial wizard input, users can provide iterative instructions that route through the persona connector before the final forge.

## Key Modules
- `src/artist_matrix/soul_forge/profiles.py`: Immutable profile schema utilities.
- `src/artist_matrix/soul_forge/service.py`: Persona + avatar orchestration and manifest persistence.
- `src/artist_matrix/interfaces/creative.py`: Protocols for persona and avatar connectors.

## Configuration
- Environment variables: `ARTIST_MATRIX_DATA_ROOT`, `ARTIST_MATRIX_PERSONA_PROVIDER`, `ARTIST_MATRIX_PERSONA_MODEL`, `ARTIST_MATRIX_PERSONA_API_KEY`, `ARTIST_MATRIX_AVATAR_PROVIDER`, `ARTIST_MATRIX_AVATAR_MODEL`, and `ARTIST_MATRIX_AVATAR_API_KEY` control storage and connector selection.
- DeepSeek integration also honors `ARTIST_MATRIX_PERSONA_ENDPOINT` (default `https://api.deepseek.com/v1/chat/completions`).
- Register persona and avatar providers in `SoulForgeService` wiring; use dependency injection for model clients when introducing bespoke SDKs.
- Default "stub" providers can be replaced with DeepSeek/Claude or SDXL-style adapters once credentials are configured.
- The TUI wizard now supports back/edit navigation and persists draft state in `SessionState` to streamline iterative persona creation.
- Prompt templates live under `prompts/persona/`; DeepSeek connectors load `deepseek_artist_template.md` (fallback template embedded) and can be replaced or extended per deployment.

## Testing
- Unit tests: `tests/soul_forge/test_creation.py` covers manifest writes and connector calls.
- Add fixtures under `tests/fixtures/` for new persona templates or avatar prompt samples.
