# Workflow Reference

This document tracks end-to-end pipelines, approval gates, and background job lifecycles. Native
workflows enter through a persistent Codex specialist, read canonical records through the local MCP
server, and create typed proposals. Existing domain services execute only after application-owned
approval.

## Native Agent Workflow

1. Select a specialist role and product scope in `artist-matrix chat` or `artist-matrix run`.
2. `NativeAgentRuntime` resumes the saved Codex thread for that `(role, scope)` pair or starts one.
3. Codex reads artist, track, and action records through the read/propose-only MCP server.
4. Creative suggestions remain conversational until a proposal tool validates and writes a
   `pending` action record.
5. The agent surfaces the action ID; the user inspects it with `artist-matrix actions`.
6. The application—not Codex—accepts `approve` or `reject` and applies the guarded state transition.
7. Approved actions call a deterministic domain adapter. Unconfigured or non-idempotent external
   integrations write a safe local outbox envelope and become `queued`.

An agent message is never proof of a provider operation. A `queued` action explicitly means
`external_effect=not_executed`. Only a `completed` action result and its canonical manifest or
provider receipt establish completion.

## Soul Forge Persona Creation
- Native entry point: `artist-matrix chat --agent soul_forge --scope <artist-slug>`.
- Soul Forge gathers a complete identity and calls `propose_artist_profile`; it cannot persist the
  profile directly.
- On explicit approval, `ArtistProfileRepository` persists the canonical artist manifest and the
  configured local avatar generator records its approved avatar asset/blueprint.
- Intake request from TUI with genre, mood, descriptors, and influences.
- Route brief to persona generator (LLM) to produce draft metadata.
- Persist validated `ArtistProfile` manifests under `data/artists/<slug>.json`.
- Trigger avatar generator stub to capture prompts and seeds for later rendering.
- Configure generators via `ARTIST_MATRIX_PERSONA_PROVIDER` and `ARTIST_MATRIX_AVATAR_PROVIDER` when wiring external services.
- TUI wizard captures extended attributes (visual palette, narrative tone, safety notes) with back/edit navigation before forging.
- Optional refinement chat allows operators to add iterative instructions that flow into the persona connector prior to manifest persistence.
- When `ARTIST_MATRIX_PERSONA_PROVIDER=deepseek` and an API key is set, refinement calls the DeepSeek chat API using templates packaged under `src/artist_matrix/prompts/persona/`.
- Set `ARTIST_MATRIX_PERSONA_LOG_DIR` to capture request/response JSON for audit trails when operating DeepSeek in production.
- After forging or selecting a persona, the TUI offers direct hand-offs into Creation Engine (track brief) and Echo Chamber (campaign) using auto-populated suggestions.

## Creation Engine Track Production
- Native entry point: `artist-matrix chat --agent creation_engine --scope <artist-slug>`.
- Creation Engine inspects the artist record, co-creates a `TrackIdeationDraft`, and calls
  `propose_track_render` only after presenting the exact brief.
- Approved local/stub render proposals use the existing `CreationEngineService`, preserving the
  accepted lyrics or instrumental choice and writing the canonical track manifest.
- Remote render providers remain queued until an application adapter forwards the action UUID as
  the provider idempotency key; approval alone never calls a charged provider.
- Translate profile + `TrackJobSpec` into lyric draft via lyric generator stub.
- Render audio artifact with Creation Engine service, storing metadata and file paths.
- Optionally invoke artwork generator to produce cover art for the track.
- Persist per-track manifests under `data/artists/<slug>/tracks/<track>.json` with job context.

## Echo Chamber Social Amplification
- Native entry point: `artist-matrix chat --agent echo_chamber --scope <artist-slug>`.
- Echo Chamber creates a reviewable `propose_social_campaign` action. A pending action is not a
  scheduled or published post.
- Derive campaign beats and cadence via `CampaignPlanner` using persona tone guidelines.
- Generate per-platform `SocialPost` entries capturing schedules and copy.
- Publish through configured API clients with analytics logging for success/failure.
- Requeue or adjust beats when failures occur, keeping records for downstream dashboards.

## World Stage Distribution Pipeline
- Native entry point: `artist-matrix chat --agent world_stage --scope <artist-slug>`.
- World Stage verifies canonical artist and track records before `propose_release`. Only the host
  application can dispatch an approved release.
- Validate release metadata against `ReleaseRequest` and ensure manifests exist for tracks/artwork.
- Submit distribution payloads through platform-specific clients, capturing receipts.
- Store release manifests under `data/releases/<slug>/<title>.json` for auditing.
- Log analytics per platform to feed dashboards and royalty tracking.

## Workflow Orchestration & State Management
- `NativeAgentRuntime` is the primary orchestrator. It binds specialist roles and product scopes to
  durable Codex threads while keeping product state outside those threads.
- `ArtistMatrixGraph` remains a deterministic legacy/domain integration path during migration.
- Shared Pydantic schemas (`ArtistManifest`, `TrackManifest`, `ReleaseManifest`) transport data between stages.
- Normalized runtime events expose lifecycle updates without coupling the CLI or future UIs to
  generated Codex protocol types.
- The `ActionStore` state machine provides the human approval gate and durable execution result.
- Per-action and per-scope OS locks prevent concurrent CLI/UI workers from double-running a
  provider action or racing the same Codex thread.
- Integration tests under `tests/integration/` validate cross-node hand-offs and manifest wiring.
