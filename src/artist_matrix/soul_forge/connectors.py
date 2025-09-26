"""Configurable persona and avatar generators for the Soul Forge."""

from __future__ import annotations

import json
import logging
from logging import Handler
from json import JSONDecodeError
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import httpx

from pydantic import BaseModel

from artist_matrix.interfaces.creative import (
    AvatarBlueprint,
    AvatarGenerator,
    PersonaDraft,
    PersonaGenerator,
    PersonaRequest,
)
from artist_matrix.soul_forge.profiles import ArtistProfile
from artist_matrix.state import ArtistMatrixSettings


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class PersonaLLMOutput(BaseModel):
    name: str
    persona_tags: list[str]
    lyric_style: str
    visual_style: str
    influences: list[str]
    safety_notes: str | None = None
    visual_palette: list[str] = []
    narrative_tone: str | None = None


class PersonaPromptVariables(BaseModel):
    name: str
    genre: str
    mood: str
    influences: list[str]
    descriptors: list[str]
    brief: str | None
    visual_palette: list[str]
    narrative_tone: str | None
    safety_notes: str | None
    refinement_instructions: list[str]


@dataclass
class StubPersonaGenerator(PersonaGenerator):
    """Basic persona generator used when external LLMs are not configured."""

    def draft_persona(self, request: PersonaRequest) -> PersonaDraft:
        influences = tuple(request.influences)
        descriptors = tuple(request.descriptors)
        persona_tags = descriptors or (request.mood, "tui-forged")
        lyric_style = f"{request.genre} narratives"
        visual_style = f"{request.genre} holographic"
        safety_notes = "Ensure generated content remains suitable for all audiences."
        return PersonaDraft(
            name=request.name,
            persona_tags=persona_tags,
            lyric_style=lyric_style,
            visual_style=visual_style,
            influences=influences or ("synthetic muse",),
            safety_notes=safety_notes,
            visual_palette=tuple(request.visual_palette),
            narrative_tone=request.narrative_tone,
        )


@dataclass
class PersonaPromptAgent(Protocol):
    def invoke(self, variables: PersonaPromptVariables) -> PersonaLLMOutput:
        ...


@dataclass
class DeepSeekPersonaAgent(PersonaPromptAgent):
    template: str
    api_key: str
    model: str
    endpoint: str
    timeout: float = 30.0
    max_attempts: int = 3
    log_dir: Path | None = None

    def _render_prompt(self, variables: PersonaPromptVariables) -> str:
        def join(items: list[str]) -> str:
            return ", ".join(items) if items else "None"
        mapping = {
            "name": variables.name,
            "genre": variables.genre,
            "mood": variables.mood,
            "influences": join(variables.influences),
            "descriptors": join(variables.descriptors),
            "brief": variables.brief or "None",
            "visual_palette": join(variables.visual_palette),
            "narrative_tone": variables.narrative_tone or "None",
            "safety_notes": variables.safety_notes or "None",
            "refinement_instructions": join(variables.refinement_instructions),
        }
        return self.template.format(**mapping)

    def invoke(self, variables: PersonaPromptVariables) -> PersonaLLMOutput:
        prompt = self._render_prompt(variables)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an AI music persona architect."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(1, max(1, self.max_attempts) + 1):
            logger.info(
                "DeepSeek persona request", extra={"persona": variables.name, "attempt": attempt}
            )
            try:
                response = httpx.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                if self.log_dir:
                    self.log_dir.mkdir(parents=True, exist_ok=True)
                    log_path = self.log_dir / f"deepseek_{variables.name}_{attempt}.json"
                    log_payload = {
                        "request": payload,
                        "response": data,
                    }
                    log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")
                if content.startswith("```"):
                    parts = content.split("```")
                    if len(parts) >= 3:
                        body = parts[1]
                        newline_index = body.find("\n")
                        if newline_index != -1:
                            body = body[newline_index + 1 :]
                        content = body.strip()
                payload_dict = json.loads(content)
                for key in ("persona_tags", "influences", "visual_palette"):
                    value = payload_dict.get(key)
                    if isinstance(value, str):
                        payload_dict[key] = [value]
                if isinstance(payload_dict.get("visual_palette"), list):
                    payload_dict["visual_palette"] = [str(item) for item in payload_dict["visual_palette"]]
                if isinstance(payload_dict.get("persona_tags"), list):
                    payload_dict["persona_tags"] = [str(item) for item in payload_dict["persona_tags"]]
                if isinstance(payload_dict.get("influences"), list):
                    payload_dict["influences"] = [str(item) for item in payload_dict["influences"]]
                output = PersonaLLMOutput.model_validate(payload_dict)
                if variables.safety_notes:
                    expected = variables.safety_notes.lower()
                    returned = (output.safety_notes or "").lower()
                    if "avoid" in expected and "avoid" not in returned and "explicit" not in returned:
                        raise RuntimeError("DeepSeek output dropped safety instructions")
                logger.info(
                    "DeepSeek persona success",
                    extra={
                        "persona": variables.name,
                        "attempt": attempt,
                        "provider": self.model,
                    },
                )
                return output
            except (httpx.HTTPError, KeyError, JSONDecodeError, RuntimeError, Exception) as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "DeepSeek persona attempt failed",
                    extra={
                        "persona": variables.name,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
        raise RuntimeError(f"DeepSeek persona generation failed: {last_error}")


@dataclass
class LLMTemplatePersonaGenerator(PersonaGenerator):
    """Template-based persona generator mimicking an external LLM response."""

    provider: str
    model: str
    api_key: str | None = None
    prompt_agent: PersonaPromptAgent | None = None

    def draft_persona(self, request: PersonaRequest) -> PersonaDraft:
        if self.prompt_agent and self.api_key:
            variables = PersonaPromptVariables(
                name=request.name,
                genre=request.genre,
                mood=request.mood,
                influences=list(request.influences),
                descriptors=list(request.descriptors),
                brief=request.brief,
                visual_palette=list(request.visual_palette),
                narrative_tone=request.narrative_tone,
                safety_notes=request.safety_notes,
                refinement_instructions=list(request.refinement_instructions),
            )
            try:
                payload = self.prompt_agent.invoke(variables)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"AI persona generation failed: {exc}") from exc
            return PersonaDraft(
                name=payload.name,
                persona_tags=tuple(payload.persona_tags),
                lyric_style=payload.lyric_style,
                visual_style=payload.visual_style,
                influences=tuple(payload.influences),
                safety_notes=payload.safety_notes,
                visual_palette=tuple(payload.visual_palette),
                narrative_tone=payload.narrative_tone,
            )

        influences = tuple(request.influences) or ("experimental muse",)
        descriptors = tuple(request.descriptors)
        persona_tags = descriptors or (request.genre, self.provider)
        lyric_style = f"{request.genre} {self.provider} narratives"
        visual_style = f"{request.genre} holographic {self.provider}"
        safety_notes = (
            "Generated via {provider} model {model}; review for content safety."
        ).format(provider=self.provider, model=self.model)
        if self.api_key:
            safety_notes += " (api key supplied)"
        visual_palette = tuple(request.visual_palette) or (f"{request.genre} neon",)
        narrative_tone = request.narrative_tone or f"{request.mood} chronicle"
        if request.refinement_instructions:
            narrative_tone = f"{narrative_tone} | {'; '.join(request.refinement_instructions)}"
        return PersonaDraft(
            name=request.name,
            persona_tags=persona_tags,
            lyric_style=lyric_style,
            visual_style=visual_style,
            influences=influences,
            safety_notes=safety_notes,
            visual_palette=visual_palette,
            narrative_tone=narrative_tone,
        )


@dataclass
class StubAvatarGenerator(AvatarGenerator):
    """Diffusion stub that records prompt metadata to a local file."""

    asset_root: Path
    prompt_template: Callable[[ArtistProfile], str] | None = None

    def __post_init__(self) -> None:
        self.asset_root.mkdir(parents=True, exist_ok=True)

    def generate_avatar(self, profile: ArtistProfile) -> AvatarBlueprint:
        prompt = (
            self.prompt_template(profile)
            if self.prompt_template
            else f"pixel art portrait of {profile.name} in {profile.visual_style} style"
        )
        asset_path = self.asset_root / f"{profile.slug}.txt"
        asset_path.write_text(
            f"prompt: {prompt}\nvisual_style: {profile.visual_style}\n",
            encoding="utf-8",
        )
        return AvatarBlueprint(prompt=prompt, seed=42, asset_path=asset_path)


@dataclass
class DiffusionAvatarGenerator(AvatarGenerator):
    """Simulated diffusion generator writing metadata for downstream rendering."""

    provider: str
    model: str
    asset_root: Path
    prompt_template: Callable[[ArtistProfile], str] | None = None
    api_key: str | None = None

    def __post_init__(self) -> None:
        self.asset_root.mkdir(parents=True, exist_ok=True)

    def generate_avatar(self, profile: ArtistProfile) -> AvatarBlueprint:
        prompt = (
            self.prompt_template(profile)
            if self.prompt_template
            else f"{profile.visual_style} portrait of {profile.name}"
        )
        metadata: dict[str, object] = {
            "provider": self.provider,
            "model": self.model,
            "prompt": prompt,
            "persona_tags": list(profile.persona_tags),
        }
        if self.api_key:
            metadata["api_key_present"] = True
        asset_path = self.asset_root / f"{profile.slug}-{self.provider}.json"
        asset_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return AvatarBlueprint(prompt=prompt, seed=108, asset_path=asset_path)


def build_persona_generator(settings: ArtistMatrixSettings) -> PersonaGenerator:
    provider = settings.persona_provider.lower()
    if provider in {"stub", "local"}:
        return StubPersonaGenerator()
    if provider in {"deepseek", "claude"}:
        api_key = settings.persona_api_key
        model = settings.persona_model or "persona-default"
        agent: PersonaPromptAgent | None = None
        if api_key and provider == "deepseek":
            template_path = settings.prompts_root / "persona" / "deepseek_artist_template.md"
            try:
                template = template_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                template = DEFAULT_DEEPSEEK_TEMPLATE
            endpoint = settings.persona_endpoint or "https://api.deepseek.com/v1/chat/completions"
            log_dir = settings.persona_log_dir
            if log_dir:
                log_dir.mkdir(parents=True, exist_ok=True)
                global _persona_log_handler  # noqa: PLW0603
                if _persona_log_handler is None:
                    handler = logging.FileHandler(log_dir / "deepseek_persona.log")
                    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
                    handler.setFormatter(formatter)
                    logger.addHandler(handler)
                    _persona_log_handler = handler
            agent = DeepSeekPersonaAgent(
                template=template,
                api_key=api_key,
                model=model,
                endpoint=endpoint,
                log_dir=log_dir,
            )
        return LLMTemplatePersonaGenerator(
            provider=provider,
            model=model,
            api_key=api_key,
            prompt_agent=agent,
        )
    raise NotImplementedError(
        f"Persona provider '{settings.persona_provider}' is not implemented."
    )


def build_avatar_generator(settings: ArtistMatrixSettings) -> AvatarGenerator:
    provider = settings.avatar_provider.lower()
    asset_root = settings.data_root / "avatars"
    if provider in {"stub", "local"}:
        return StubAvatarGenerator(asset_root=asset_root)
    if provider in {"sdxl", "diffusion", "runway"}:
        model = settings.avatar_model or "sdxl-stub"
        return DiffusionAvatarGenerator(
            provider=provider,
            model=model,
            asset_root=asset_root,
            api_key=settings.avatar_api_key,
        )
    raise NotImplementedError(
        f"Avatar provider '{settings.avatar_provider}' is not implemented."
    )


__all__ = [
    "StubPersonaGenerator",
    "LLMTemplatePersonaGenerator",
    "StubAvatarGenerator",
    "DiffusionAvatarGenerator",
    "build_persona_generator",
    "build_avatar_generator",
]
DEFAULT_DEEPSEEK_TEMPLATE = "You are an AI music persona architect. Name: {name} Genre: {genre} Mood: {mood}. Influences: {influences}. Descriptors: {descriptors}. Brief: {brief}. Visual Palette: {visual_palette}. Narrative Tone: {narrative_tone}. Safety Notes: {safety_notes}. Refinement Instructions: {refinement_instructions}. Respond with strict JSON containing fields name, persona_tags, lyric_style, visual_style, influences, safety_notes, visual_palette, narrative_tone."
_persona_log_handler: Handler | None = None
