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
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]

    updated_fields: dict[str, object] = {}
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            updated_fields = parsed
    except json.JSONDecodeError:
        logger.debug("LLM response not JSON; falling back to heuristic", extra={"response": response})
        lines = [line.strip() for line in response.replace("**", "").splitlines() if line.strip()]
        for line in lines:
            lowered = line.lower()
            if lowered.startswith("title:"):
                updated_fields["title"] = line.split(":", 1)[1].strip()
            elif lowered.startswith("vibe:") or lowered.startswith("style:"):
                updated_fields["style"] = line.split(":", 1)[1].strip()
            elif lowered.startswith("tags:"):
                updated_fields["tags"] = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
            elif lowered.startswith("instrument"):
                updated_fields["instrumental"] = line.split(":", 1)[1].strip()
            elif lowered.startswith("lyrics:"):
                updated_fields["lyrics"] = line.split(":", 1)[1].strip()
            elif lowered.startswith("core vibe:"):
                updated_fields["prompt"] = line.split(":", 1)[1].strip()

    updates: dict[str, object] = {
        "notes": tuple(list(draft.notes) + [response]),
        "summary": response,
        "extracted_fields": {**(draft.extracted_fields or {}), **updated_fields} if updated_fields else draft.extracted_fields,
    }
    title = updated_fields.get("title")
    if isinstance(title, str) and title:
        updates["title"] = title
    style = updated_fields.get("style")
    if isinstance(style, str) and style:
        updates["style"] = style
    prompt_value = updated_fields.get("prompt")
    if isinstance(prompt_value, str) and prompt_value:
        updates["prompt"] = prompt_value
    tags_value = updated_fields.get("tags")
    if isinstance(tags_value, list):
        updates["tags"] = tuple(str(tag).strip() for tag in tags_value if str(tag).strip())
    elif isinstance(tags_value, str):
        updates["tags"] = tuple(part.strip() for part in tags_value.split(",") if part.strip())
    negative_value = updated_fields.get("negative_tags")
    if isinstance(negative_value, list):
        updates["negative_tags"] = tuple(str(tag).strip() for tag in negative_value if str(tag).strip())
    instrumental_value = updated_fields.get("instrumental")
    if isinstance(instrumental_value, bool):
        updates["instrumental"] = instrumental_value
    elif isinstance(instrumental_value, str):
        updates["instrumental"] = instrumental_value.lower() in {"yes", "y", "true", "1"}
    lyrics_value = updated_fields.get("lyrics")
    if isinstance(lyrics_value, str) and lyrics_value:
        updates["lyrics"] = lyrics_value

    new_draft = draft.model_copy(update=updates)
    new_draft.update_timestamp()
    return response, new_draft


__all__ = ["TrackIdeationLLM", "apply_llm_guidance"]
