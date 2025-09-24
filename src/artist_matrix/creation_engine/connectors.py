"""Audio generator connectors for the Creation Engine."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from artist_matrix.interfaces.production import (
    AudioGenerator,
    LyricDraft,
    LyricGenerator,
    TrackArtifact,
)
from artist_matrix.soul_forge import ArtistProfile
from artist_matrix.state import ArtistMatrixSettings
from artist_matrix.state.jobs import TrackJobSpec


def _slugify(value: str) -> str:
    lowered = value.lower().strip()
    sanitized = "".join(ch if ch.isalnum() else "-" for ch in lowered)
    collapsed = "-".join(part for part in sanitized.split("-") if part)
    return collapsed or "track"


@dataclass
class StubAudioGenerator(AudioGenerator):
    """Writes placeholder audio artifacts for local prototyping."""

    output_root: Path

    def render_track(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
        lyrics: LyricDraft,
    ) -> TrackArtifact:
        artist_dir = self.output_root / profile.slug / "tracks"
        artist_dir.mkdir(parents=True, exist_ok=True)
        track_slug = _slugify(spec.title)
        audio_path = artist_dir / f"{track_slug}.wav"
        if not audio_path.exists():
            audio_path.write_bytes(b"stub-audio")
        return TrackArtifact(
            title=spec.title,
            audio_path=audio_path,
            duration_seconds=180.0,
            preview_url=None,
        )


@dataclass
class HeuristicLyricGenerator(LyricGenerator):
    """Lightweight lyric generator based on persona metadata."""

    max_lines: int = 8

    def generate_lyrics(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
    ) -> LyricDraft:
        title = spec.title or f"{profile.name} Anthem"
        narrative = spec.narrative or profile.narrative_tone or spec.mood
        influences = ", ".join(profile.influences) if profile.influences else ", ".join(spec.references)
        visual = ", ".join(profile.visual_palette)
        body_lines: list[str] = []
        line_templates = [
            f"{profile.name} rides the {spec.mood} skyline",
            f"Echoes of {influences or 'forgotten signals'} ignite the night",
            f"Chromed hearts pulse where {narrative or 'legends'} collide",
            f"{visual or 'Neon haze'} bleeds into fractured dawn",
        ]
        while len(body_lines) < self.max_lines:
            body_lines.extend(line_templates)
        body = "\n".join(body_lines[: self.max_lines])
        references = spec.references if spec.references else profile.influences
        return LyricDraft(title=title, body=body, references=references)


@dataclass
class SunoAudioGenerator(AudioGenerator):
    """Calls the Suno API to render audio tracks for a persona."""

    api_key: str
    output_root: Path
    base_url: str = "https://api.sunoapi.org"
    model: str | None = None
    callback_url: str | None = None
    poll_interval: float = 5.0
    timeout_seconds: float = 300.0
    client_factory: Callable[[], httpx.Client] | None = None
    download_chunk_size: int = 64 * 1024

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("SunoAudioGenerator requires an API key")
        if not self.base_url:
            raise ValueError("SunoAudioGenerator requires a base URL")
        self.base_url = self.base_url.rstrip("/")
        self.output_root.mkdir(parents=True, exist_ok=True)
        if self.client_factory is None:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            self.client_factory = lambda: httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
            )

    def render_track(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
        lyrics: LyricDraft,
    ) -> TrackArtifact:
        artist_dir = self.output_root / profile.slug / "tracks"
        artist_dir.mkdir(parents=True, exist_ok=True)
        track_slug = _slugify(spec.title)
        output_path = artist_dir / f"{track_slug}.mp3"

        if self.client_factory is None:
            raise RuntimeError("SunoAudioGenerator client factory is not configured")

        with self.client_factory() as client:
            job_id = self._submit_job(client, profile, spec, lyrics)
            job_payload = self._poll_job(client, job_id)
            result_payload = self._select_primary_result(job_payload)
            audio_url = self._extract_audio_url(result_payload)
            duration = self._extract_duration(result_payload)
            self._download_audio(client, audio_url, output_path)

        preview_url = result_payload.get("streamAudioUrl")
        if not isinstance(preview_url, str):
            preview_url = None

        return TrackArtifact(
            title=spec.title,
            audio_path=output_path,
            duration_seconds=duration,
            preview_url=preview_url,
        )

    # --- Internals -------------------------------------------------

    def _submit_job(
        self,
        client: httpx.Client,
        profile: ArtistProfile,
        spec: TrackJobSpec,
        lyrics: LyricDraft,
    ) -> str:
        prompt = self._build_prompt(profile, spec, lyrics)
        style = spec.mood or profile.visual_style or profile.lyric_style or "Experimental"
        title = spec.title or f"{profile.name} Track"
        callback_url = self.callback_url or "https://artist-matrix.local/callback"
        payload: dict[str, object] = {
            "prompt": prompt,
            "style": style[:1000],
            "title": title[:80],
            "customMode": True,
            "instrumental": False,
            "model": self.model or "V3_5",
            "callBackUrl": callback_url,
        }
        references = list(spec.references) or list(profile.influences)
        if references:
            payload["tags"] = ", ".join(references)
        if profile.safety_notes:
            payload["negativeTags"] = profile.safety_notes[:200]
        if spec.narrative:
            payload["styleWeight"] = 0.65
            payload["weirdnessConstraint"] = 0.65
            payload["audioWeight"] = 0.65

        response = client.post("/api/v1/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 200:
            raise RuntimeError(f"Suno API error {data.get('code')}: {data.get('msg')}")
        job_id = data.get("data", {}).get("taskId")
        if not job_id:
            raise RuntimeError("Suno API response missing taskId")
        return str(job_id)

    def _poll_job(self, client: httpx.Client, job_id: str) -> dict[str, object]:
        deadline = time.monotonic() + self.timeout_seconds
        status_path = "/api/v1/generate/record-info"
        last_payload: dict[str, object] | None = None
        while time.monotonic() < deadline:
            response = client.get(status_path, params={"taskId": job_id})
            response.raise_for_status()
            payload = response.json()
            last_payload = payload
            if payload.get("code") != 200:
                raise RuntimeError(
                    f"Suno status error {payload.get('code')}: {payload.get('msg')}"
                )
            data = payload.get("data")
            if isinstance(data, dict):
                status = str(data.get("status", "")).upper()
                if status in {"SUCCESS", "FIRST_SUCCESS", "TEXT_SUCCESS"}:
                    return data
                if status in {
                    "CREATE_TASK_FAILED",
                    "GENERATE_AUDIO_FAILED",
                    "CALLBACK_EXCEPTION",
                    "SENSITIVE_WORD_ERROR",
                }:
                    error_message = data.get("errorMessage") or payload.get("msg")
                    raise RuntimeError(
                        f"Suno generation failed ({status}): {error_message}"
                    )
            time.sleep(max(self.poll_interval, 0.0))
        raise TimeoutError(
            f"Timed out waiting for Suno generation {job_id}; last payload: {json.dumps(last_payload or {}, indent=2)}"
        )

    def _select_primary_result(self, payload: dict[str, object]) -> dict[str, object]:
        response = payload.get("response")
        if isinstance(response, dict):
            suno_data = response.get("sunoData")
            if isinstance(suno_data, list) and suno_data:
                first = suno_data[0]
                if isinstance(first, dict):
                    return first
        return payload

    def _extract_audio_url(self, payload: dict[str, object]) -> str:
        audio_url = payload.get("audioUrl") or payload.get("audio_url")
        if audio_url:
            return str(audio_url)
        stream_url = payload.get("streamAudioUrl") or payload.get("stream_audio_url")
        if stream_url:
            return str(stream_url)
        raise RuntimeError("Suno payload missing audio URL")

    def _extract_duration(self, payload: dict[str, object]) -> float | None:
        duration = payload.get("duration")
        if isinstance(duration, (int, float)):
            return float(duration)
        return None

    def _download_audio(
        self,
        client: httpx.Client,
        url: str,
        output_path: Path,
    ) -> None:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_bytes(self.download_chunk_size):
                    handle.write(chunk)

    def _build_prompt(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
        lyrics: LyricDraft,
    ) -> str:
        content = lyrics.body.strip() or spec.narrative or spec.mood
        if not content:
            content = f"Instrumental piece inspired by {profile.name}"
        return content[:5000]


def build_audio_generator(settings: ArtistMatrixSettings) -> AudioGenerator:
    provider = settings.creation_audio_provider.lower()
    output_root = settings.data_root / "artists"
    if provider in {"stub", "local"}:
        return StubAudioGenerator(output_root=output_root)
    if provider == "suno":
        api_key = settings.creation_audio_api_key
        if not api_key:
            raise RuntimeError(
                "Suno audio provider selected but ARTIST_MATRIX_CREATION_AUDIO_API_KEY is not set"
            )
        base_url = (
            settings.creation_audio_base_url
            or getattr(settings, "creation_audio_endpoint", None)
            or "https://api.sunoapi.org"
        )
        return SunoAudioGenerator(
            api_key=api_key,
            output_root=output_root,
            base_url=base_url,
            model=settings.creation_audio_model,
            callback_url=settings.creation_audio_callback_url,
            poll_interval=settings.creation_audio_poll_interval,
            timeout_seconds=settings.creation_audio_timeout_seconds,
        )
    raise NotImplementedError(
        f"Audio provider '{settings.creation_audio_provider}' is not implemented."
    )


def build_lyric_generator(settings: ArtistMatrixSettings) -> LyricGenerator:
    """Return a lyric generator implementation based on settings."""

    # Placeholder until external LLM lyric generation is integrated.
    return HeuristicLyricGenerator()


__all__ = [
    "StubAudioGenerator",
    "SunoAudioGenerator",
    "build_audio_generator",
    "HeuristicLyricGenerator",
    "build_lyric_generator",
]
