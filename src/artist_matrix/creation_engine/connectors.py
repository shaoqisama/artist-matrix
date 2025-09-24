"""Audio generator connectors for the Creation Engine."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
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
    log_dir: Path | None = None
    _last_logs: list[Path] = field(default_factory=list, init=False, repr=False)

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
        if self.log_dir is not None:
            self.log_dir.mkdir(parents=True, exist_ok=True)

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
        self._last_logs = []

        if self.client_factory is None:
            raise RuntimeError("SunoAudioGenerator client factory is not configured")

        request_payload = self._build_request_payload(profile, spec, lyrics)
        logger.info(
            "Submitting Suno generation",
            extra={
                "artist": profile.slug,
                "track_title": spec.title,
                "model": request_payload.get("model"),
            },
        )

        with self.client_factory() as client:
            job_id = self._submit_job(client, request_payload)
            if self.log_dir is not None:
                self._write_log(profile.slug, job_id, "request", request_payload)
            job_payload = self._poll_job(
                client,
                job_id,
                log_hook=lambda status, payload: self._write_log(
                    profile.slug,
                    job_id,
                    f"status_{status.lower() or 'unknown'}",
                    payload,
                )
                if self.log_dir is not None
                else None,
            )
            results = self._collect_results(job_payload)
            if not results:
                raise RuntimeError("Suno generation returned no audio results")

            alternate_paths: list[Path] = []
            primary_duration: float | None = None
            primary_preview: str | None = None

            for index, result_payload in enumerate(results):
                target_path = (
                    output_path
                    if index == 0
                    else output_path.with_name(
                        f"{output_path.stem}-{index+1}{output_path.suffix}"
                    )
                )
                audio_url = self._extract_audio_url(result_payload)
                duration = self._extract_duration(result_payload)
                self._download_audio(client, audio_url, target_path)
                if index == 0:
                    primary_duration = duration
                    primary_preview = self._extract_preview_url(result_payload)
                else:
                    alternate_paths.append(target_path)

        logger.info(
            "Suno generation completed",
            extra={
                "artist": profile.slug,
                "track_title": spec.title,
                "job_id": job_id,
                "duration": primary_duration,
                "alternates": len(alternate_paths),
            },
        )

        preview_url = primary_preview if isinstance(primary_preview, str) else None

        if self.log_dir is not None:
            self._write_log(profile.slug, job_id, "completion", job_payload)

        return TrackArtifact(
            title=spec.title,
            audio_path=output_path,
            duration_seconds=primary_duration,
            preview_url=preview_url,
            alternates=tuple(alternate_paths),
        )

    # --- Internals -------------------------------------------------

    def _submit_job(
        self,
        client: httpx.Client,
        payload: dict[str, object],
    ) -> str:
        response = client.post("/api/v1/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 200:
            raise RuntimeError(f"Suno API error {data.get('code')}: {data.get('msg')}")
        job_id = data.get("data", {}).get("taskId")
        if not job_id:
            raise RuntimeError("Suno API response missing taskId")
        return str(job_id)

    def _poll_job(
        self,
        client: httpx.Client,
        job_id: str,
        log_hook: Callable[[str, dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        deadline = time.monotonic() + self.timeout_seconds
        status_path = "/api/v1/generate/record-info"
        last_payload: dict[str, object] | None = None
        last_status: str | None = None
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
                if log_hook is not None and status != last_status:
                    log_hook(status or "UNKNOWN", payload)
                    last_status = status
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

    def _build_request_payload(
        self,
        profile: ArtistProfile,
        spec: TrackJobSpec,
        lyrics: LyricDraft,
    ) -> dict[str, object]:
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
        return payload

    def _collect_results(self, payload: dict[str, object]) -> list[dict[str, object]]:
        response = payload.get("response")
        if isinstance(response, dict):
            suno_data = response.get("sunoData")
            if isinstance(suno_data, list):
                return [item for item in suno_data if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    def _extract_audio_url(self, payload: dict[str, object]) -> str:
        audio_url = payload.get("audioUrl") or payload.get("audio_url")
        if audio_url:
            return str(audio_url)
        stream_url = payload.get("streamAudioUrl") or payload.get("stream_audio_url")
        if stream_url:
            return str(stream_url)
        raise RuntimeError("Suno payload missing audio URL")

    def _extract_preview_url(self, payload: dict[str, object]) -> str | None:
        preview = payload.get("streamAudioUrl") or payload.get("stream_audio_url")
        if isinstance(preview, str):
            return preview
        return None

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

    def _write_log(
        self,
        artist_slug: str,
        job_id: str,
        stage: str,
        payload: dict[str, object],
    ) -> None:
        if self.log_dir is None:
            return
        safe_stage = stage.replace("/", "_").replace(" ", "-")
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        filename = f"suno_{timestamp}_{artist_slug}_{job_id}_{safe_stage}.json"
        path = self.log_dir / filename
        try:
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            self._last_logs.append(path)
        except OSError as exc:  # noqa: BLE001
            logger.warning("Failed to write Suno log", extra={"path": str(path), "error": str(exc)})

    def last_run_logs(self) -> tuple[Path, ...]:
        return tuple(self._last_logs)


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
            log_dir=settings.creation_audio_log_dir,
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
logger = logging.getLogger(__name__)
