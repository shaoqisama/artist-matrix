from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from httpx import MockTransport, Request, Response

from artist_matrix.creation_engine.connectors import SunoAudioGenerator
from artist_matrix.interfaces.production import LyricDraft
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state.jobs import TrackJobSpec


@pytest.fixture()
def artist_profile() -> ArtistProfile:
    return ArtistProfile(
        name="Neon Wasteland",
        persona_tags=("cyberpunk",),
        lyric_style="synth metal narration",
        visual_style="retro neon",
        influences=("Perturbator",),
    )


@pytest.fixture()
def lyric_draft() -> LyricDraft:
    return LyricDraft(
        title="Signal Burn",
        body="Neon rivers carve the rusted sky",
        references=("future",),
    )


def test_suno_audio_generator_downloads_audio(
    tmp_path: Path,
    artist_profile: ArtistProfile,
    lyric_draft: LyricDraft,
) -> None:
    spec = TrackJobSpec(title="Signal Burn", mood="fierce", references=("future",))

    poll_attempts = {"count": 0}

    def handler(request: Request) -> Response:
        if request.method == "POST" and request.url.path == "/api/v1/generate":
            payload = json.loads(request.content.decode())
            assert payload["title"] == "Signal Burn"
            assert payload["customMode"] is True
            assert payload["instrumental"] is False
            assert payload["model"] == "suno-test"
            return Response(
                200, json={"code": 200, "msg": "success", "data": {"taskId": "job-123"}}
            )

        if request.method == "GET" and request.url.path == "/api/v1/generate/record-info":
            task_id = request.url.params.get("taskId")
            assert task_id == "job-123"
            poll_attempts["count"] += 1
            if poll_attempts["count"] < 2:
                return Response(
                    200,
                    json={
                        "code": 200,
                        "msg": "pending",
                        "data": {"status": "PENDING"},
                    },
                )
            return Response(
                200,
                json={
                    "code": 200,
                    "msg": "success",
                    "data": {
                        "status": "SUCCESS",
                        "response": {
                            "sunoData": [
                                {
                                    "id": "result-1",
                                    "audioUrl": "https://cdn.suno.fake/audio/job-123.mp3",
                                    "streamAudioUrl": "https://cdn.suno.fake/audio/job-123-stream",
                                    "duration": 123.0,
                                },
                                {
                                    "id": "result-2",
                                    "audioUrl": "https://cdn.suno.fake/audio/job-123-alt.mp3",
                                    "streamAudioUrl": "https://cdn.suno.fake/audio/job-123-alt-stream",
                                    "duration": 222.0,
                                },
                            ]
                        },
                    },
                },
            )

        if request.method == "GET" and request.url.path == "/audio/job-123.mp3":
            return Response(200, content=b"AUDIO", headers={"Content-Type": "audio/mpeg"})

        if request.method == "GET" and request.url.path == "/audio/job-123-stream":
            return Response(200, content=b"AUDIO", headers={"Content-Type": "audio/mpeg"})

        if request.method == "GET" and request.url.path == "/audio/job-123-alt.mp3":
            return Response(200, content=b"ALT", headers={"Content-Type": "audio/mpeg"})

        if request.method == "GET" and request.url.path == "/audio/job-123-alt-stream":
            return Response(200, content=b"ALT", headers={"Content-Type": "audio/mpeg"})

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = MockTransport(handler)

    def client_factory() -> httpx.Client:
        return httpx.Client(base_url="https://api.suno.fake", transport=transport)

    log_dir = tmp_path / "logs"

    generator = SunoAudioGenerator(
        api_key="test-key",
        output_root=tmp_path,
        base_url="https://api.suno.fake",
        model="suno-test",
        callback_url="https://callback.example/test",
        poll_interval=0.0,
        timeout_seconds=10.0,
        client_factory=client_factory,
        log_dir=log_dir,
    )

    artifact = generator.render_track(artist_profile, spec, lyric_draft)

    expected_path = tmp_path / artist_profile.slug / "tracks" / "signal-burn.mp3"

    assert artifact.audio_path == expected_path
    assert artifact.duration_seconds == pytest.approx(123.0)
    assert expected_path.exists()
    assert expected_path.read_bytes() == b"AUDIO"

    alternates = artifact.alternates
    assert alternates
    alt_path = alternates[0]
    assert alt_path.exists()
    assert alt_path.read_bytes() == b"ALT"

    assert poll_attempts["count"] >= 2

    logs = generator.last_run_logs()
    assert logs
    for path in logs:
        assert path.exists()
        assert path.read_text(encoding="utf-8")  # non-empty

    written_files = sorted(log_dir.glob("*.json"))
    assert written_files
