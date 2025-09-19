# Workflow Reference

This document tracks end-to-end pipelines, approval gates, and background job lifecycles.
Populate each section as milestones introduce concrete implementations.

## Soul Forge Persona Creation
- Intake request from TUI with genre, mood, descriptors, and influences.
- Route brief to persona generator (LLM) to produce draft metadata.
- Persist validated `ArtistProfile` manifests under `data/artists/<slug>.json`.
- Trigger avatar generator stub to capture prompts and seeds for later rendering.

## Creation Engine Track Production
- Translate profile + `TrackJobSpec` into lyric draft via lyric generator stub.
- Render audio artifact with Creation Engine service, storing metadata and file paths.
- Optionally invoke artwork generator to produce cover art for the track.
- Persist per-track manifests under `data/artists/<slug>/tracks/<track>.json` with job context.
