# Workflow Reference

This document tracks end-to-end pipelines, approval gates, and background job lifecycles.
Populate each section as milestones introduce concrete implementations.

## Soul Forge Persona Creation
- Intake request from TUI with genre, mood, descriptors, and influences.
- Route brief to persona generator (LLM) to produce draft metadata.
- Persist validated `ArtistProfile` manifests under `data/artists/<slug>.json`.
- Trigger avatar generator stub to capture prompts and seeds for later rendering.
- Configure generators via `ARTIST_MATRIX_PERSONA_PROVIDER` and `ARTIST_MATRIX_AVATAR_PROVIDER` when wiring external services.
- TUI wizard captures extended attributes (visual palette, narrative tone, safety notes) with back/edit navigation before forging.
- Optional refinement chat allows operators to add iterative instructions that flow into the persona connector prior to manifest persistence.
- When `ARTIST_MATRIX_PERSONA_PROVIDER=deepseek` and an API key is set, refinement calls the DeepSeek chat API using templates stored under `prompts/persona/`.

## Creation Engine Track Production
- Translate profile + `TrackJobSpec` into lyric draft via lyric generator stub.
- Render audio artifact with Creation Engine service, storing metadata and file paths.
- Optionally invoke artwork generator to produce cover art for the track.
- Persist per-track manifests under `data/artists/<slug>/tracks/<track>.json` with job context.

## Echo Chamber Social Amplification
- Derive campaign beats and cadence via `CampaignPlanner` using persona tone guidelines.
- Generate per-platform `SocialPost` entries capturing schedules and copy.
- Publish through configured API clients with analytics logging for success/failure.
- Requeue or adjust beats when failures occur, keeping records for downstream dashboards.

## World Stage Distribution Pipeline
- Validate release metadata against `ReleaseRequest` and ensure manifests exist for tracks/artwork.
- Submit distribution payloads through platform-specific clients, capturing receipts.
- Store release manifests under `data/releases/<slug>/<title>.json` for auditing.
- Log analytics per platform to feed dashboards and royalty tracking.

## Workflow Orchestration & State Management
- `ArtistMatrixGraph` binds Soul Forge, Creation Engine, Echo Chamber, and World Stage nodes.
- Shared Pydantic schemas (`ArtistManifest`, `TrackManifest`, `ReleaseManifest`) transport data between stages.
- Hook callbacks expose lifecycle events for logging, analytics, or human approval gates.
- Integration tests under `tests/integration/` validate cross-node hand-offs and manifest wiring.
