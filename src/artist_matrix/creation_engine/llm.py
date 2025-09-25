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
        response = self.client.post("/chat/completions", json=payload)
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
        client = httpx.Client(
            base_url=endpoint,
            headers={
                "Authorization": f"Bearer {settings.persona_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        model = settings.persona_model or "deepseek-chat"
        return cls(
            client=client,
            system_prompt=(
                "You are a music production coach for persona '{persona}'."
                " Help refine track briefs concisely without repeating previous context."
            ),
            model=model,
            log_dir=settings.persona_log_dir,
        )


def apply_llm_guidance(
    llm: TrackIdeationLLM | None,
    persona_summary: str,
    user_message: str,
    transcript: Iterable[ChatTurn],
    draft: TrackIdeationDraft,
) -> tuple[str | None, TrackIdeationDraft]:
    if llm is None:
        return None, draft
    try:
        response = llm.chat(persona_summary, user_message, transcript)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM ideation call failed",
            extra={"error": str(exc)},
        )
        return f"LLM unavailable ({exc})", draft
    notes = list(draft.notes)
    notes.append(response)
    new_draft = draft.model_copy(update={"notes": tuple(notes)})
    new_draft.update_timestamp()
    return response, new_draft


__all__ = ["TrackIdeationLLM", "apply_llm_guidance"]
