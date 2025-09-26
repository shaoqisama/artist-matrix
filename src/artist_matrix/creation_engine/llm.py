"""LLM interface for track ideation refinement."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import httpx

from artist_matrix.creation_engine.ideation import ChatTurn, TrackIdeationDraft
from artist_matrix.state import ArtistMatrixSettings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrackIdeationLLM:
    """Simple DeepSeek-backed chat client for track ideation."""

    client: httpx.Client
    endpoint: str
    system_prompt: str
    model: str
    log_dir: Path | None = None

    def chat(
        self,
        persona_summary: str,
        prompt: str,
        transcript: Iterable[ChatTurn],
    ) -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt.format(persona=persona_summary)},
        ]
        for turn in transcript:
            messages.append({"role": turn.role, "content": turn.content})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
        }

        logger.debug("Ideation LLM request", extra={"prompt": prompt[:60]})
        response = self.client.post(self.endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        if self.log_dir is not None:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            path = self.log_dir / f"ideation_{timestamp}.json"
            path.write_text(json.dumps({"request": payload, "response": data}, indent=2), encoding="utf-8")
        return content

    @classmethod
    def build(cls, settings: ArtistMatrixSettings) -> TrackIdeationLLM | None:
        if settings.persona_provider.lower() != "deepseek" or not settings.persona_api_key:
            return None
        endpoint = settings.persona_endpoint or "https://api.deepseek.com/v1"
        endpoint = endpoint.rstrip("/")
        if endpoint.endswith("/chat/completions"):
            final_endpoint = endpoint
        else:
            final_endpoint = f"{endpoint}/chat/completions"
        client = httpx.Client(
            headers={
                "Authorization": f"Bearer {settings.persona_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        model = settings.persona_model or "deepseek-chat"
        prompt_path = settings.prompts_root / "creation" / "ideation_system.md"
        try:
            system_prompt = prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            system_prompt = (
                "You are a music production coach for persona '{persona}'."
                " Respond only with JSON containing keys title, prompt, style,"
                " tags, negative_tags, instrumental, lyrics, notes."
            )

        return cls(
            client=client,
            endpoint=final_endpoint,
            system_prompt=system_prompt,
            model=model,
            log_dir=settings.persona_log_dir,
        )


def apply_llm_guidance(
    llm: TrackIdeationLLM | None,
    persona_summary: str,
    user_message: str,
    transcript: Iterable[ChatTurn],
    _draft: TrackIdeationDraft,
) -> tuple[str | None, dict[str, object], str | None]:
    """Call the LLM and surface guidance alongside structured suggestions.

    The returned mapping contains only the raw fields proposed by the model.
    Callers decide which elements to adopt.
    """

    if llm is None:
        return None, {}, None

    try:
        response = llm.chat(persona_summary, user_message, transcript)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM ideation call failed",
            extra={"error": str(exc)},
        )
        return f"LLM unavailable ({exc})", {}, None

    cleaned = response.strip()
    fenced_json: str | None = None
    if "```" in cleaned:
        segments = cleaned.split("```")
        for segment in segments:
            candidate = segment.strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered.startswith("json"):
                fenced_json = candidate[4:].strip()
                break
            if candidate.startswith("{") and candidate.endswith("}"):
                fenced_json = candidate
                break

    payload = fenced_json or cleaned
    suggestions: dict[str, object] = {}
    pretty_json: str | None = None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        logger.debug("LLM response did not include valid JSON", extra={"response": response})
    else:
        if isinstance(parsed, dict):
            suggestions = parsed
            pretty_json = json.dumps(parsed, indent=2)

    return response, suggestions, pretty_json


__all__ = ["TrackIdeationLLM", "apply_llm_guidance"]
