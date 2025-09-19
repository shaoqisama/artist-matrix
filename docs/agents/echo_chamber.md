# Echo Chamber Agent Guide

## Responsibilities
- Plan campaign beats and publish social posts across configured platforms.
- Capture analytics for successful and failed posts to inform iteration.
- Provide tone and cadence guardrails aligned to each persona.

## Key Modules
- `src/artist_matrix/echo_chamber/planner.py`: Campaign cadence planning with platform metadata.
- `src/artist_matrix/echo_chamber/service.py`: Publishing workflow and analytics recording.
- `src/artist_matrix/interfaces/social.py`: Social client and analytics protocols.

## Configuration
- Register platform clients when instantiating `EchoChamberService`; each client must expose a `platform` slug.
- Override cadence defaults by passing `SocialCampaign` with tailored `cadence_minutes` and platform.
- Use hooks from `ArtistMatrixGraph` to route published post data into dashboards.

## Testing
- Unit tests: `tests/echo_chamber/test_echo_chamber.py` exercises planner spacing and failure handling.
- Add synthetic transcripts under `tests/fixtures/social/` for tone checks when expanding persona scripts.
