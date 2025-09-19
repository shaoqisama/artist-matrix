# World Stage Agent Guide

## Responsibilities
- Distribute releases to streaming platforms and storefronts.
- Persist audited release manifests under `data/releases/<slug>/` for compliance.
- Emit distribution receipts to analytics services for royalty tracking.

## Key Modules
- `src/artist_matrix/world_stage/release.py`: Release requests, manifest repository, and dispatch service.
- `src/artist_matrix/interfaces/distribution.py`: Distribution and analytics protocol contracts.
- `tests/world_stage/test_release.py`: Regression suite covering receipts and manifest validation.

## Configuration
- Provide platform-specific `DistributionClient` instances when wiring `WorldStageService`.
- Configure analytics sinks via `ReleaseAnalytics`; use environment settings to target dashboards.
- Ensure track manifests from Creation Engine are accessible to the service before dispatch.

## Testing
- Extend `tests/world_stage/` with fixtures representing new platform payloads.
- Include integration scenarios in `tests/integration/` when adding multi-stage release flows or approval gates.
