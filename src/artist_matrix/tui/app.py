"""Terminal UI shell for the Artist Matrix experience."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable

from artist_matrix.interfaces.creative import AvatarBlueprint
from artist_matrix.soul_forge import (
    ArtistProfile,
    ArtistProfileRepository,
    SoulForgeRequest,
    SoulForgeService,
    build_avatar_generator,
    build_persona_generator,
)
from artist_matrix.creation_engine import (
    ChatTurn,
    CreationBrief,
    CreationEngineService,
    SunoPayloadPreview,
    TrackIdeationDraft,
    TrackIdeationLLM,
    TrackIdeationStore,
    TrackManifestRepository,
    apply_llm_guidance,
    build_audio_generator,
    build_lyric_generator,
    build_suno_preview,
)
from artist_matrix.creation_engine.service import ArtworkJobSpec, TrackJobSpec
from artist_matrix.interfaces.production import LyricDraft, TrackArtifact
from artist_matrix.echo_chamber import SocialCampaign
from artist_matrix.state import ArtistMatrixSettings
from pydantic import ValidationError
from artist_matrix.tui.logging import SessionLogger

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ASSET_DIR = _PROJECT_ROOT / "assets" / "tui"

logger = logging.getLogger(__name__)


def _to_sequence(raw: str) -> tuple[str, ...]:
    items = [segment.strip() for segment in raw.split(",") if segment.strip()]
    return tuple(items)


@dataclass
class PersonaWizardDraft:
    name: str = ""
    genre: str = ""
    mood: str = ""
    influences: tuple[str, ...] = ()
    descriptors: tuple[str, ...] = ()
    brief: str = ""
    visual_palette: tuple[str, ...] = ()
    narrative_tone: str = ""
    safety_notes: str = ""
    refinement_instructions: tuple[str, ...] = ()


@dataclass
class PersonaRecord:
    path: Path
    manifest: dict[str, object]


@dataclass
class SessionState:
    last_profile: ArtistProfile | None = None
    last_manifest_path: Path | None = None
    last_avatar: AvatarBlueprint | None = None
    last_track_manifest: Path | None = None
    draft: PersonaWizardDraft = field(default_factory=PersonaWizardDraft)
    track_brief: CreationBrief | None = None
    campaign_plan: SocialCampaign | None = None
    track_draft: TrackIdeationDraft | None = None
    transcript: list[ChatTurn] = field(default_factory=list)


@dataclass
class TuiAssets:
    """Lazy loader for banner art and palette metadata."""

    base_path: Path = _ASSET_DIR
    _banner_cache: str | None = field(default=None, init=False)
    _palette_cache: Dict[str, str] | None = field(default=None, init=False)

    def banner(self) -> str:
        if self._banner_cache is None:
            banner_path = self.base_path / "banner.txt"
            self._banner_cache = banner_path.read_text(encoding="utf-8").rstrip()
        return self._banner_cache

    def palette(self) -> Dict[str, str]:
        if self._palette_cache is None:
            palette_path = self.base_path / "palette.json"
            self._palette_cache = json.loads(palette_path.read_text(encoding="utf-8"))
        return self._palette_cache


def _build_default_soul_forge(settings: ArtistMatrixSettings) -> SoulForgeService:
    persona_gen = build_persona_generator(settings)
    avatar_gen = build_avatar_generator(settings)
    return SoulForgeService(
        persona_generator=persona_gen,
        avatar_generator=avatar_gen,
        repository=ArtistProfileRepository(base_path=settings.data_root / "artists"),
    )


def _build_default_creation_engine(settings: ArtistMatrixSettings) -> CreationEngineService:
    lyric_gen = build_lyric_generator(settings)
    audio_gen = build_audio_generator(settings)
    repository = TrackManifestRepository(base_path=settings.data_root / "artists")
    return CreationEngineService(
        lyric_generator=lyric_gen,
        audio_generator=audio_gen,
        repository=repository,
    )


class TuiApp:
    """Interactive shell coordinating avatar selection and creation."""

    def __init__(
        self,
        *,
        input_func: Callable[[str], str] | None = None,
        output_func: Callable[[str], None] | None = None,
        assets: TuiAssets | None = None,
        soul_forge_service: SoulForgeService | None = None,
        creation_service: CreationEngineService | None = None,
        session: SessionState | None = None,
    ) -> None:
        self._input = input_func or input
        self._output = output_func or print
        self.assets = assets or TuiAssets()
        self.settings = ArtistMatrixSettings()
        self.soul_forge = soul_forge_service or _build_default_soul_forge(self.settings)
        self.creation_engine = creation_service or _build_default_creation_engine(self.settings)
        self.ideation_store = TrackIdeationStore(self.settings)
        self.ideation_llm = TrackIdeationLLM.build(self.settings)
        self.session = session or SessionState()
        self._session_logger: SessionLogger | None = None

    def build_main_menu(self) -> str:
        palette = self.assets.palette()
        palette_line = (
            f"[{palette['primary']}] Primary  :: [{palette['accent']}] Accent  ::"
            f" [{palette['warning']}] Alert"
        )
        menu_lines = [
            self.assets.banner(),
            "",
            "// Frequency Map",
            palette_line,
            "",
            " [1] Generate Avatar      -> Soul Forge",
            " [2] Select Avatar        -> Archives",
            " [3] Creation Workbench   -> Track Forge",
            " [4] Launch Echo Chamber  -> Broadcast",
            " [Q] Quit Terminal      -> Sleep Cycle",
            "",
        ]
        return "\n".join(menu_lines)

    def run(self) -> None:
        self._open_session_log()
        try:
            while True:
                self.output(self.build_main_menu())
                choice = self._input("Select mode (1/2/Q): ").strip().lower()
                self._log_event("user", choice)
                if choice in {"1", "g", "generate"}:
                    self.handle_generate()
                elif choice in {"2", "s", "select"}:
                    self.handle_select()
                elif choice in {"3", "c", "creation"}:
                    self.handle_creation_workbench()
                elif choice in {"4", "e", "echo"}:
                    self.handle_echo_chamber()
                elif choice in {"q", "quit", "exit"}:
                    self.output("Shutting down Artist Matrix shell. See you in the wasteland.")
                    self._log_event("assistant", "session_exit")
                    break
                else:
                    self.output("Invalid selection. Enter 1, 2, or Q to exit.")
        finally:
            log_path = self._session_logger.path if self._session_logger else None
            self._close_session_log()
            if log_path:
                self.output(f"Session log saved to {log_path}")

    def handle_generate(self) -> None:
        self.output("\n>> Soul Forge // Persona constructor engaged")
        draft = self._collect_persona_draft()
        if draft is None:
            self.output("\n>> Persona creation cancelled. Returning to main menu.")
            return

        self.session.draft = draft
        self.output("\n>> Forging persona... stand by")
        try:
            result = self.soul_forge.generate(
                SoulForgeRequest(
                    name=draft.name,
                    genre=draft.genre,
                    mood=draft.mood,
                    influences=draft.influences or ("experimental muse",),
                    descriptors=draft.descriptors,
                    brief=draft.brief or None,
                    visual_palette=draft.visual_palette,
                    narrative_tone=draft.narrative_tone or None,
                    safety_notes=draft.safety_notes or None,
                    refinement_instructions=draft.refinement_instructions,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.output(f"!! Forge failure: {exc}")
            if self.session.last_manifest_path:
                self.output(f"Last successful manifest stored at {self.session.last_manifest_path}")
            return

        profile = result.get("profile")
        manifest_path = Path(str(result.get("manifest_path")))
        avatar = result.get("avatar")

        if isinstance(profile, ArtistProfile):
            self.session.last_profile = profile
            self._update_suggestions(profile, draft)
            seed_tags = tuple(
                tag.strip()
                for tag in (
                    tuple(draft.descriptors) or tuple(draft.influences) or tuple(profile.influences)
                )
                if isinstance(tag, str) and tag.strip()
            )
            seed_notes = tuple(
                note.strip()
                for note in (draft.brief, draft.narrative_tone)
                if isinstance(note, str) and note.strip()
            )
            default_draft = TrackIdeationDraft(
                persona_slug=profile.slug,
                title=f"{profile.name} Anthem",
                style=draft.mood or profile.visual_style or profile.lyric_style,
                tags=seed_tags,
                notes=seed_notes,
                allow_instrumental=True,
            )
            self.session.track_draft = default_draft
            self.session.transcript = []
            try:
                self.ideation_store.save_draft(default_draft)
            except Exception as exc:  # noqa: BLE001
                self.output(f" Warning: unable to persist initial track draft ({exc}).")
        self.session.last_manifest_path = manifest_path
        if isinstance(avatar, AvatarBlueprint):
            self.session.last_avatar = avatar

        summary = [
            "\nPersona forged successfully!",
            f" → Manifest saved: {manifest_path}",
        ]
        if isinstance(profile, ArtistProfile):
            summary.extend(
                [
                    f" → Artist slug : {profile.slug}",
                    f" → Lyric style: {profile.lyric_style}",
                    f" → Visual mode: {profile.visual_style}",
                ]
            )
            self._update_suggestions(profile, draft)
        if isinstance(avatar, AvatarBlueprint):
            summary.extend(
                [
                    " → Avatar prompt preview:",
                    f"   '{avatar.prompt}' (seed={avatar.seed or 'n/a'})",
                    f"   asset: {avatar.asset_path or 'n/a'}",
                ]
            )
        if draft.visual_palette:
            summary.append(f" → Visual palette: {', '.join(draft.visual_palette)}")
        if draft.narrative_tone:
            summary.append(f" → Narrative tone: {draft.narrative_tone}")
        if draft.safety_notes:
            summary.append(f" → Safety notes : {draft.safety_notes}")
        self.output("\n".join(summary))
        self._log_event("assistant", "creation_engine_complete")
        self._post_persona_prompt()

    def handle_select(self) -> None:
        self.output("\n>> Accessing artist archives...")
        records = self._load_persona_records()
        if not records:
            self.output(" No personas available. Use 'Generate Avatar' to forge a new profile.")
            return

        while True:
            self.output("\nAvailable personas:")
            for idx, record in enumerate(records, 1):
                manifest = record.manifest
                name = manifest.get("name", "<unknown>")
                slug = manifest.get("slug", "?")
                lyric = manifest.get("lyric_style", "n/a")
                self.output(f" [{idx}] {name} ({slug}) :: {lyric}")

            choice = self._input("Select persona number or Q to cancel: ").strip().lower()
            if choice in {"q", "quit", "exit"}:
                self.output(" Selection cancelled; returning to main menu.")
                return
            if not choice.isdigit():
                self.output("  Enter a valid number or Q to cancel.")
                continue

            index = int(choice) - 1
            if index < 0 or index >= len(records):
                self.output("  Invalid selection. Try again.")
                continue

            record = records[index]
            self.output("\n".join(self._format_manifest_preview(record.manifest)))
            if self._prompt_confirm("Load this persona? (y/n)"):
                if self._apply_persona_selection(record):
                    self.output(
                        f" Persona '{record.manifest.get('name', '<unknown>')}' loaded into session."
                    )
                    self._post_persona_prompt()
                    return
                self.output("  Unable to load persona; select another entry.")

    def _load_persona_records(self) -> list[PersonaRecord]:
        artists_dir = self.settings.data_root / "artists"
        if not artists_dir.exists():
            return []

        records: list[PersonaRecord] = []
        for path in sorted(artists_dir.glob("*.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                records.append(PersonaRecord(path=path, manifest=manifest))
            except (OSError, json.JSONDecodeError) as exc:
                self.output(f"  Skipping corrupt manifest {path.name}: {exc}")
        return records

    def _format_manifest_preview(self, manifest: dict[str, object]) -> list[str]:
        def fmt_list(value: object) -> str:
            items = self._as_str_list(value)
            return ", ".join(items) if items else "—"

        return [
            "",
            ":: Persona Preview ::",
            f" Name       : {manifest.get('name', '<unknown>')}",
            f" Slug       : {manifest.get('slug', '—')}",
            f" Lyric style: {manifest.get('lyric_style', '—')}",
            f" Visual mode: {manifest.get('visual_style', '—')}",
            f" Tags       : {fmt_list(manifest.get('persona_tags', []))}",
            f" Influences : {fmt_list(manifest.get('influences', []))}",
            f" Visuals    : {fmt_list(manifest.get('visual_palette', []))}",
            f" Narrative  : {manifest.get('narrative_tone', '—')}",
            f" Safeguards : {manifest.get('safety_notes', '—')}",
        ]

    def _apply_persona_selection(self, record: PersonaRecord) -> bool:
        manifest = record.manifest
        path = record.path
        try:
            profile = ArtistProfile.model_validate(manifest)
        except ValidationError as exc:
            self.output(f"  Manifest validation failed: {exc}")
            return False

        avatar_data = manifest.get("avatar")
        avatar = None
        if isinstance(avatar_data, dict):
            asset_path = avatar_data.get("asset_path")
            avatar = AvatarBlueprint(
                prompt=avatar_data.get("prompt", ""),
                seed=avatar_data.get("seed"),
                asset_path=Path(asset_path) if asset_path else None,
            )

        self.session.last_profile = profile
        self.session.last_manifest_path = path
        self.session.last_avatar = avatar
        self.session.draft = PersonaWizardDraft(
            name=profile.name,
            genre=str(manifest.get("genre", profile.lyric_style)),
            mood=str(manifest.get("mood", "")),
            influences=tuple(self._as_str_list(manifest.get("influences", profile.influences))),
            descriptors=tuple(
                self._as_str_list(manifest.get("persona_tags", profile.persona_tags))
            ),
            brief=self._as_str(manifest.get("brief", "")),
            visual_palette=tuple(self._as_str_list(manifest.get("visual_palette", []))),
            narrative_tone=self._as_str(
                manifest.get("narrative_tone", profile.lyric_style), profile.lyric_style
            ),
            safety_notes=self._as_str(manifest.get("safety_notes", profile.safety_notes or "")),
            refinement_instructions=tuple(
                self._as_str_list(manifest.get("refinement_instructions", []))
            ),
        )
        self._update_suggestions(profile, self.session.draft)
        final_draft = self.ideation_store.load_final(profile.slug)
        if final_draft:
            self.session.track_draft = final_draft
        else:
            stored_draft = self.ideation_store.load_draft(profile.slug)
            if stored_draft:
                self.session.track_draft = stored_draft
        self.session.transcript = self.ideation_store.load_transcript(profile.slug)
        self.output(
            " Use menu option 3 or 4 to launch Creation Engine or Echo Chamber with this persona."
        )
        return True

    def _as_str_list(self, value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value]
        return []

    def _as_str(self, value: object, default: str = "") -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return default
        return str(value)

    def _update_suggestions(self, profile: ArtistProfile, draft: PersonaWizardDraft) -> None:
        influences = list(draft.influences) or list(profile.influences)
        track_title = f"{profile.name} Anthem"
        track_spec = TrackJobSpec(
            title=track_title,
            mood=draft.mood or "inspired",
            tempo_bpm=None,
            key=None,
            references=influences[:3],
            narrative=draft.brief or draft.narrative_tone or "New narrative",
        )
        artwork_spec = ArtworkJobSpec(
            title=f"{profile.name} Cover",
            style=profile.visual_style,
            references=list(draft.visual_palette)[:3],
            seed=42,
        )
        creation_brief = CreationBrief(
            track=track_spec,
            artwork=artwork_spec,
            narrative=draft.narrative_tone or draft.brief,
        )

        beats = [
            f"Meet {profile.name}",
            f"Share {track_title}",
            "Tease upcoming drop",
        ]
        campaign = SocialCampaign(
            title=f"{profile.name} Launch",
            platform="echo",
            beats=tuple(beats),
            cadence_minutes=90,
        )

        self.session.track_brief = creation_brief
        self.session.campaign_plan = campaign

    def _post_persona_prompt(self) -> None:
        while True:
            selection = (
                self._input("Next action [c]reation workbench / [e]cho chamber / [m]ain menu: ")
                .strip()
                .lower()
            )
            if selection in {"c", "creation", "3"}:
                self.handle_creation_workbench()
                return
            if selection in {"e", "echo", "4"}:
                self.handle_echo_chamber()
                return
            if selection in {"m", "menu", ""}:
                return
            self.output("  Enter 'c', 'e', or 'm'.")

    def _ensure_track_draft(self, profile: ArtistProfile) -> TrackIdeationDraft:
        draft = self.session.track_draft
        if draft is None or draft.persona_slug != profile.slug:
            default_tags = tuple(
                tag.strip() for tag in profile.influences if isinstance(tag, str) and tag.strip()
            )
            default_notes: tuple[str, ...] = ()
            if profile.narrative_tone and profile.narrative_tone.strip():
                default_notes = (profile.narrative_tone.strip(),)
            draft = TrackIdeationDraft(
                persona_slug=profile.slug,
                title=f"{profile.name} Anthem",
                style=profile.lyric_style or profile.visual_style,
                tags=default_tags,
                notes=default_notes,
                allow_instrumental=True,
            )
            self.session.track_draft = draft
        return draft

    def _open_session_log(self) -> None:
        if self.settings.tui_log_dir is None:
            return
        try:
            self._session_logger = SessionLogger(self.settings.tui_log_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to open session log", extra={"error": str(exc)})
            self._session_logger = None

    def _close_session_log(self) -> None:
        if self._session_logger is None:
            return
        self._session_logger.close()
        self._session_logger = None

    def _log_event(self, role: str, message: str) -> None:
        if self._session_logger is None:
            return
        try:
            self._session_logger.write_event(role=role, message=message)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to write session log", extra={"error": str(exc)})

    def handle_creation_workbench(self) -> None:
        profile = self.session.last_profile
        if profile is None:
            self.output(" No persona selected. Generate or select a profile first.")
            return

        draft = self._ensure_track_draft(profile)
        transcript = list(self.session.transcript)
        session_turns: list[ChatTurn] = []
        pending_fields: dict[str, object] | None = None
        pending_json: str | None = None
        history: list[TrackIdeationDraft] = []
        last_assistant_text: str | None = None

        self.output("\n>> Creation Workbench // Chat Mode")
        self.output(" Type a message to brainstorm with the assistant.")
        self.output(
            " Commands -> /help, /show, /adopt, /edit <field>: <value>, /undo, /finalize, /back"
        )
        self.output(" Only /adopt or /edit updates the draft.")
        if self.ideation_llm is None:
            self.output(
                " AI assistant disabled (configure ARTIST_MATRIX_PERSONA_PROVIDER/MODEL/API_KEY for DeepSeek)."
            )

        while True:
            user_input = self._input("workbench> ").strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                command = user_input[1:].strip()
                lowered = command.lower()

                if lowered in {"back", "exit", "quit"}:
                    break

                if lowered == "help":
                    self._show_workbench_help()
                    continue

                if lowered == "show":
                    self.output("\n:: Draft Snapshot ::")
                    for line in self._draft_summary_lines(draft):
                        self.output(f" {line}")
                    ready, missing = self._draft_readiness(draft)
                    if ready:
                        self.output(" Status       : ready for /finalize")
                    else:
                        self.output(f" Status       : pending ({', '.join(missing)})")
                    if pending_fields:
                        self.output(" Pending suggestion available → /adopt.")
                    continue

                if lowered == "undo":
                    if not history:
                        self.output(" Nothing to undo.")
                        continue
                    draft = history.pop()
                    self.session.track_draft = draft
                    pending_fields = None
                    pending_json = None
                    self._log_event("user", "draft:undo")
                    self.output(" Reverted last change.")
                    continue

                if lowered == "adopt":
                    if not pending_fields:
                        self.output(" No pending suggestion to adopt.")
                        continue
                    new_draft, applied, errors = self._apply_draft_updates(
                        draft,
                        pending_fields,
                        mode="adopt",
                        summary=last_assistant_text,
                    )
                    if errors:
                        for message in errors:
                            self.output(f" ! {message}")
                    if not applied:
                        self.output(" Nothing applied from the suggestion.")
                        pending_fields = None
                        pending_json = None
                        continue
                    history.append(draft)
                    draft = new_draft
                    self.session.track_draft = draft
                    pending_fields = None
                    pending_json = None
                    self._log_event("assistant", f"draft:adopt:{','.join(applied)}")
                    self.output(f" Adopted: {', '.join(applied)}.")
                    continue

                if lowered.startswith("edit"):
                    remainder = command[4:].strip()
                    if not remainder:
                        self.output(" Usage: /edit field: value")
                        continue
                    if ":" not in remainder:
                        self.output(" Use format field: value")
                        continue
                    field_name, raw_value = remainder.split(":", 1)
                    field_key = self._normalize_field_name(field_name.strip())
                    if not field_key:
                        self.output(f" Unknown field '{field_name.strip()}'.")
                        continue
                    updates: dict[str, object] = {field_key: raw_value.strip()}
                    new_draft, applied, errors = self._apply_draft_updates(
                        draft,
                        updates,
                        mode="manual",
                        summary=last_assistant_text,
                    )
                    if errors:
                        for message in errors:
                            self.output(f" ! {message}")
                    if not applied:
                        self.output(" No changes applied.")
                        continue
                    history.append(draft)
                    draft = new_draft
                    self.session.track_draft = draft
                    pending_fields = None
                    pending_json = None
                    self._log_event("user", f"draft:edit:{','.join(applied)}")
                    self.output(f" Updated {', '.join(applied)}.")
                    continue

                if lowered == "finalize":
                    ready, missing = self._draft_readiness(draft)
                    if not ready:
                        self.output(f" Draft not ready: {', '.join(missing)}")
                        continue
                    preview = build_suno_preview(draft)
                    self.output("\n:: Suno Payload Preview ::")
                    for line in self._preview_lines(preview):
                        self.output(f" {line}")
                    confirm = self._input("Render with Suno now? [y/N]: ").strip().lower()
                    self._log_event("user", f"workbench_finalize:{confirm}")
                    if confirm not in {"y", "yes"}:
                        self.output(" Preview complete. Continue editing or /back to exit.")
                        continue
                    self._persist_chat_session(
                        profile,
                        draft,
                        transcript,
                        session_turns,
                        final=True,
                    )
                    self._run_creation_engine(profile, draft)
                    return

                self.output(" Unknown command. Use /help for options.")
                continue

            self._log_event("user", f"chat_input:{user_input}")
            user_turn = ChatTurn(role="user", content=user_input)
            transcript.append(user_turn)
            session_turns.append(user_turn)

            assistant_text, suggestions, pretty_json = apply_llm_guidance(
                self.ideation_llm,
                self._persona_summary(profile),
                user_input,
                transcript,
                draft,
            )
            if assistant_text is None:
                assistant_text = self._generate_stub_response(profile, draft, user_input)

            last_assistant_text = assistant_text
            reply_turn = ChatTurn(role="assistant", content=assistant_text)
            transcript.append(reply_turn)
            session_turns.append(reply_turn)
            self.output(f"AI> {assistant_text}")
            self._log_event("assistant", f"chat_output:{assistant_text}")

            suggested_fields: dict[str, object] = {}
            for key, value in suggestions.items():
                field = self._normalize_field_name(key)
                if field is None:
                    continue
                suggested_fields[field] = value

            if suggested_fields:
                pending_fields = suggested_fields
                pending_json = pretty_json or json.dumps(suggested_fields, indent=2)
                self.output("AI suggests (use /adopt to apply):")
                current_pending = pending_fields
                for key, value in current_pending.items():
                    self.output(f"  {key}: {self._format_value(key, value)}")
                if pending_json:
                    self.output("AI (json)>")
                    for line in pending_json.splitlines():
                        self.output(f"  {line}")
                    self._log_event("assistant", f"chat_json:{pending_json}")
            else:
                pending_fields = None
                pending_json = None

        self._persist_chat_session(profile, draft, transcript, session_turns)
        self.output(" Draft saved. Use /finalize when you are ready to render.")

    def _show_workbench_help(self) -> None:
        self.output(" Commands:")
        self.output("  /show      -> display the current draft summary")
        self.output("  /adopt     -> apply the last AI suggestion")
        self.output(
            "  /edit f: v -> manually update a field (title, style, tags, lyrics, notes, duration, allow_instrumental, ref_url)"
        )
        self.output("  /undo      -> revert the last adopt/edit")
        self.output("  /finalize  -> preview the Suno payload and render")
        self.output("  /back      -> exit the workbench")

    def _persist_chat_session(
        self,
        profile: ArtistProfile,
        draft: TrackIdeationDraft,
        transcript: list[ChatTurn],
        session_turns: list[ChatTurn],
        *,
        final: bool = False,
    ) -> None:
        self.session.track_draft = draft
        self.session.transcript = transcript
        self.session.track_brief = self._build_creation_brief_from_draft(profile, draft)
        try:
            self.ideation_store.save_draft(draft)
            if final:
                self.ideation_store.save_final(draft)
            if session_turns:
                self.ideation_store.append_transcript(profile.slug, session_turns)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to persist track ideation data",
                extra={"persona": profile.slug, "error": str(exc)},
            )

    def _draft_summary_lines(self, draft: TrackIdeationDraft) -> Iterable[str]:
        lines = [
            ("Title", draft.title or "—"),
            ("Style", draft.style or "—"),
            ("Tags", ", ".join(draft.tags) if draft.tags else "—"),
            (
                "Lyrics",
                (draft.lyrics[:80] + ("…" if draft.lyrics and len(draft.lyrics) > 80 else ""))
                if draft.lyrics
                else "—",
            ),
            ("Duration", f"{draft.duration_sec}s" if draft.duration_sec else "—"),
            ("Allow instr.", "yes" if draft.allow_instrumental else "no"),
            ("Ref URL", draft.ref_url or "—"),
            ("Updated", draft.updated_at.isoformat(timespec="seconds")),
        ]
        if draft.notes:
            latest_note = draft.notes[-1]
            lines.append(("Latest note", latest_note[:80] + ("…" if len(latest_note) > 80 else "")))
        return [f"{label:12}: {value}" for label, value in lines]

    def _preview_lines(self, preview: SunoPayloadPreview) -> Iterable[str]:
        tags = ", ".join(preview.tags) if preview.tags else "—"
        notes = "; ".join(preview.notes) if preview.notes else "—"
        lines = [
            f"Title        : {preview.title}",
            f"Style        : {preview.style or '—'}",
            f"Tags         : {tags}",
            f"Allow instr. : {'yes' if preview.allow_instrumental else 'no'}",
        ]
        if preview.duration_sec:
            lines.append(f"Duration (s) : {preview.duration_sec}")
        if preview.lyrics:
            snippet = preview.lyrics.strip()
            if len(snippet) > 100:
                snippet = snippet[:100] + "…"
            lines.append(f"Lyrics       : {snippet}")
        if preview.notes:
            snippet = notes
            if len(snippet) > 100:
                snippet = snippet[:100] + "…"
            lines.append(f"Notes        : {snippet}")
        if preview.ref_url:
            lines.append(f"Reference    : {preview.ref_url}")
        return lines

    def _draft_readiness(self, draft: TrackIdeationDraft) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if not (draft.title and draft.title.strip()):
            missing.append("title")
        if not draft.tags:
            missing.append("tags")
        if draft.lyrics:
            pass
        elif draft.style and draft.notes:
            pass
        else:
            missing.append("lyrics or style+notes")
        return (not missing, missing)

    def _normalize_field_name(self, raw: str) -> str | None:
        key = raw.strip().replace("-", "_")
        if not key:
            return None
        lowered = key.lower()
        mapping = {
            "title": "title",
            "track_title": "title",
            "style": "style",
            "mood": "style",
            "tags": "tags",
            "tag": "tags",
            "lyrics": "lyrics",
            "lyric": "lyrics",
            "note": "notes",
            "notes": "notes",
            "duration": "duration_sec",
            "duration_sec": "duration_sec",
            "durationseconds": "duration_sec",
            "length": "duration_sec",
            "allow_instrumental": "allow_instrumental",
            "instrumental": "allow_instrumental",
            "allowinstrumental": "allow_instrumental",
            "ref_url": "ref_url",
            "reference_url": "ref_url",
            "url": "ref_url",
            "link": "ref_url",
        }
        return mapping.get(lowered)

    def _apply_draft_updates(
        self,
        draft: TrackIdeationDraft,
        updates: dict[str, object],
        *,
        mode: str,
        summary: str | None,
    ) -> tuple[TrackIdeationDraft, list[str], list[str]]:
        applied: list[str] = []
        errors: list[str] = []
        payload: dict[str, object] = {}

        for key, raw_value in updates.items():
            field = self._normalize_field_name(key)
            if field is None:
                continue

            if field in {"title", "style", "lyrics", "ref_url"}:
                text = raw_value if isinstance(raw_value, str) else str(raw_value)
                text = text.strip()
                if not text:
                    if field in {"style", "ref_url"} and mode == "manual":
                        if getattr(draft, field) is not None:
                            payload[field] = None
                            applied.append(field)
                        continue
                    errors.append(f"{field} requires a value.")
                    continue
                current = getattr(draft, field)
                if isinstance(current, str) and current.strip() == text:
                    continue
                payload[field] = text
                applied.append(field)
                continue

            if field == "tags":
                tokens: list[str] = []
                if isinstance(raw_value, str):
                    tokens = [part.strip() for part in raw_value.split(",") if part.strip()]
                elif isinstance(raw_value, (list, tuple, set)):
                    for item in raw_value:
                        text = str(item).strip()
                        if text:
                            tokens.append(text)
                if not tokens:
                    errors.append("tags must include at least one entry.")
                    continue
                new_tags = tuple(tokens)
                if tuple(draft.tags) == new_tags:
                    continue
                payload["tags"] = new_tags
                applied.append("tags")
                continue

            if field == "notes":
                entries: list[str] = []
                if isinstance(raw_value, str):
                    text = raw_value.strip()
                    if text:
                        entries.append(text)
                elif isinstance(raw_value, (list, tuple, set)):
                    for item in raw_value:
                        text = str(item).strip()
                        if text:
                            entries.append(text)
                else:
                    errors.append("notes update must be text or a list of text entries.")
                    continue
                if not entries:
                    errors.append("notes update was empty.")
                    continue
                combined = list(draft.notes)
                combined.extend(entries)
                payload["notes"] = tuple(combined)
                applied.append("notes")
                continue

            if field == "duration_sec":
                if raw_value in {"", None}:
                    if draft.duration_sec is not None:
                        payload["duration_sec"] = None
                        applied.append("duration_sec")
                    continue
                try:
                    numeric = (
                        raw_value
                        if isinstance(raw_value, (int, float))
                        else float(str(raw_value).strip())
                    )
                except (TypeError, ValueError):
                    errors.append("duration_sec must be a number of seconds.")
                    continue
                seconds = int(round(numeric))
                if seconds <= 0:
                    errors.append("duration_sec must be positive.")
                    continue
                if draft.duration_sec == seconds:
                    continue
                payload["duration_sec"] = seconds
                applied.append("duration_sec")
                continue

            if field == "allow_instrumental":
                parsed = self._to_bool(raw_value)
                if parsed is None:
                    errors.append("allow_instrumental expected yes/no.")
                    continue
                if draft.allow_instrumental == parsed:
                    continue
                payload["allow_instrumental"] = parsed
                applied.append("allow_instrumental")
                continue

        if summary:
            payload.setdefault("summary", summary)

        if not payload:
            return draft, applied, errors

        new_draft = draft.model_copy(update=payload)
        new_draft.update_timestamp()
        return new_draft, applied, errors

    def _format_value(self, field: str, value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or "—"
        if isinstance(value, (list, tuple, set)):
            items = [str(item).strip() for item in value if str(item).strip()]
            return ", ".join(items) if items else "—"
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)

    def _to_bool(self, value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"yes", "y", "true", "1", "allow"}:
                return True
            if lowered in {"no", "n", "false", "0"}:
                return False
        return None

    def _build_creation_brief_from_draft(
        self,
        profile: ArtistProfile,
        draft: TrackIdeationDraft,
    ) -> CreationBrief:
        existing = self.session.track_brief
        tempo = existing.track.tempo_bpm if existing else None
        key = existing.track.key if existing else None
        references = (
            tuple(draft.tags)
            if draft.tags
            else (tuple(existing.track.references) if existing else ())
        )
        note_values = [note for note in draft.notes if note.strip()]
        narrative = "\n".join(note_values) if note_values else None
        mood = (
            draft.style
            or (existing.track.mood if existing else None)
            or profile.lyric_style
            or "unclassified"
        )
        title = draft.title or (existing.track.title if existing else f"{profile.name} Track")
        track_spec = TrackJobSpec(
            title=title,
            mood=mood,
            tempo_bpm=tempo,
            key=key,
            references=references,
            narrative=narrative,
        )
        artwork = existing.artwork if existing else None
        combined_narrative = narrative or (existing.narrative if existing else None)
        return CreationBrief(track=track_spec, artwork=artwork, narrative=combined_narrative)

    def _generate_stub_response(
        self,
        profile: ArtistProfile,
        draft: TrackIdeationDraft,
        user_input: str,
    ) -> str:
        lowered = user_input.lower()
        if "tags" in lowered:
            focus = ", ".join(draft.tags) if draft.tags else "fresh tags"
            return f"Consider leaning into tags like {focus}. Use /adopt to capture them."
        if "lyrics" in lowered:
            return "Sketch a lyric idea and capture it with /edit lyrics: <text>."
        if "style" in lowered:
            return "Lock the vibe with /edit style: <descriptor> when it feels right."
        return (
            f"Channeling {profile.name}'s {draft.style or profile.lyric_style or 'signature tone'}."
            " Adopt suggestions explicitly to update the brief."
        )

    def _persona_summary(self, profile: ArtistProfile) -> str:
        influences = ", ".join(profile.influences) or "ambient inspirations"
        return f"{profile.name} ({profile.lyric_style}) influenced by {influences}"

    def _run_creation_engine(self, profile: ArtistProfile, draft: TrackIdeationDraft) -> None:
        brief = self._build_creation_brief_from_draft(profile, draft)
        self.session.track_brief = brief
        provider = self.settings.creation_audio_provider
        preview = build_suno_preview(draft)

        self.output(f"\n>> Creation Engine // {provider} dispatch")
        self.output(f" Title       : {preview.title}")
        self.output(f" Style       : {preview.style or '—'}")
        self.output(f" Tags        : {', '.join(preview.tags) if preview.tags else '—'}")
        self.output(f" Allow inst. : {'yes' if preview.allow_instrumental else 'no'}")
        if preview.duration_sec:
            self.output(f" Duration    : {preview.duration_sec}s")
        if preview.ref_url:
            self.output(f" Reference   : {preview.ref_url}")

        self.output(f" Launching Creation Engine via provider '{provider}'...")
        try:
            result = self.creation_engine.produce_track(profile, brief)
        except Exception as exc:  # noqa: BLE001
            self.output(f"!! Creation Engine failure: {exc}")
            if self.session.last_track_manifest:
                self.output(f" Last successful track manifest: {self.session.last_track_manifest}")
            return

        manifest_path: Path | None = None
        manifest_value = result.get("manifest_path") if isinstance(result, dict) else None
        if isinstance(manifest_value, Path):
            manifest_path = manifest_value
        elif isinstance(manifest_value, str):
            manifest_path = Path(manifest_value)
        if manifest_path is not None:
            self.session.last_track_manifest = manifest_path

        track_artifact = result.get("track") if isinstance(result, dict) else None
        if not isinstance(track_artifact, TrackArtifact):
            track_artifact = None

        lyrics = result.get("lyrics") if isinstance(result, dict) else None
        if not isinstance(lyrics, LyricDraft):
            lyrics = None

        captured_logs: tuple[Path, ...] = ()
        log_value = result.get("logs") if isinstance(result, dict) else None
        if isinstance(log_value, (list, tuple)):
            captured_logs = tuple(
                Path(item) if not isinstance(item, Path) else item for item in log_value
            )

        summary = [
            "",
            f"Creation Engine complete via provider '{provider}'.",
        ]
        if manifest_path is not None:
            summary.append(f" → Manifest saved: {manifest_path}")
        if track_artifact is not None:
            summary.append(f" → Track asset : {track_artifact.audio_path}")
            if track_artifact.duration_seconds:
                summary.append(f"   duration   : {track_artifact.duration_seconds:.0f}s")
            if track_artifact.alternates:
                summary.append("   alternates :")
                for path in track_artifact.alternates[:3]:
                    summary.append(f"    - {path}")
                if len(track_artifact.alternates) > 3:
                    summary.append("    - …")
        if lyrics is not None and lyrics.body:
            first_line = lyrics.body.splitlines()[0]
            snippet = first_line[:80]
            if len(first_line) > 80:
                snippet += "…"
            summary.append(f" → Lyrics lead: {snippet}")
        if captured_logs:
            summary.append(" Logs captured:")
            for path in captured_logs[:3]:
                summary.append(f"   {path}")
            if len(captured_logs) > 3:
                summary.append("   …")
        log_dir = self.settings.creation_audio_log_dir
        if log_dir is not None:
            summary.append(f" Log files saved to: {log_dir}")
        self.output("\n".join(summary))
        self._post_persona_prompt()

    def handle_creation_engine(self) -> None:
        profile = self.session.last_profile
        if profile is None:
            self.output(" No persona selected. Generate or select a profile first.")
            return
        draft = self.session.track_draft or self._ensure_track_draft(profile)
        ready, missing = self._draft_readiness(draft)
        if not ready:
            self.output(f" Draft not ready: {', '.join(missing)}")
            return
        preview = build_suno_preview(draft)
        self.output("\n:: Suno Payload Preview ::")
        for line in self._preview_lines(preview):
            self.output(f" {line}")
        confirm = self._input("Render with Suno now? [y/N]: ").strip().lower()
        self._log_event("user", f"creation_engine_confirm:{confirm}")
        if confirm not in {"y", "yes"}:
            self.output(" Creation cancelled.")
            return
        self._persist_chat_session(profile, draft, list(self.session.transcript), [], final=True)
        self._run_creation_engine(profile, draft)

    def handle_echo_chamber(self) -> None:
        self.output("\n>> Echo Chamber // Campaign Plan")
        campaign = self.session.campaign_plan
        if not campaign:
            self.output(" No persona selected. Generate or select a profile first.")
            return
        self.output(f" Title       : {campaign.title}")
        self.output(f" Platform    : {campaign.platform}")
        self.output(f" Cadence     : every {campaign.cadence_minutes} minutes")
        self.output(" Beats:")
        for idx, beat in enumerate(campaign.beats, 1):
            self.output(f"  {idx}. {beat}")
        self.output(" Use this plan to seed Echo Chamber campaigns.")

    def output(self, message: str) -> None:
        self._output(message)

    # --- Wizard helpers -------------------------------------------------

    def _collect_persona_draft(self) -> PersonaWizardDraft | None:
        draft = PersonaWizardDraft(
            name=self.session.draft.name,
            genre=self.session.draft.genre,
            mood=self.session.draft.mood,
            influences=self.session.draft.influences,
            descriptors=self.session.draft.descriptors,
            brief=self.session.draft.brief,
            visual_palette=self.session.draft.visual_palette,
            narrative_tone=self.session.draft.narrative_tone,
            safety_notes=self.session.draft.safety_notes,
        )

        steps = [
            ("name", "Artist alias", True, "text"),
            ("genre", "Primary genre", True, "text"),
            ("mood", "Mood or energy signature", True, "text"),
            (
                "influences",
                "Influences (comma-separated, leave blank if none)",
                False,
                "sequence",
            ),
            (
                "descriptors",
                "Descriptors or persona tags (comma-separated)",
                False,
                "sequence",
            ),
            (
                "brief",
                "One-line creative brief (optional)",
                False,
                "text",
            ),
            (
                "visual_palette",
                "Visual palette cues (comma-separated)",
                False,
                "sequence",
            ),
            (
                "narrative_tone",
                "Narrative tone (optional)",
                False,
                "text",
            ),
            (
                "safety_notes",
                "Safety guardrails (optional)",
                False,
                "text",
            ),
        ]

        self.output("Enter '<' to go back, '.' to keep the current value.")
        index = 0
        while index < len(steps):
            key, prompt, required, kind = steps[index]
            current_value = getattr(draft, key)
            display_value = (
                ", ".join(current_value)
                if isinstance(current_value, tuple)
                else current_value or "—"
            )
            raw = self._input(f"{prompt} [{display_value}]: ").strip()
            if raw in {"<", "b", "back"}:
                if index == 0:
                    self.output("  Already at the first step.")
                    continue
                index -= 1
                continue
            if raw == ".":
                index += 1
                continue
            if not raw:
                if required and not current_value:
                    self.output("  Please provide a value.")
                    continue
                if kind == "sequence":
                    setattr(draft, key, tuple() if not raw else _to_sequence(raw))
                else:
                    setattr(draft, key, current_value if current_value else "")
                index += 1
                continue

            try:
                if kind == "sequence":
                    parsed = _to_sequence(raw)
                    setattr(draft, key, parsed)
                else:
                    setattr(draft, key, raw)
            except ValueError as exc:  # pragma: no cover - defensive
                self.output(f"  Invalid input: {exc}")
                continue
            index += 1

        # Summary + confirmation loop
        while True:
            self.output("\n".join(self._summary_lines(draft)))
            action = self._input("Action [f]orge / [r]efine / [e]dit / [c]ancel: ").strip().lower()
            if action in {"f", "forge"}:
                return draft
            if action in {"c", "cancel"}:
                self.session.draft = draft
                return None
            if action in {"r", "refine"}:
                refined = self._refine_with_ai(draft)
                if refined is None:
                    self.session.draft = draft
                    return None
                draft = refined
                continue
            if action in {"e", "edit"}:
                target = self._input(" Step number to edit (blank for first): ").strip()
                if target.isdigit():
                    idx = int(target) - 1
                    if 0 <= idx < len(steps):
                        index = idx
                    else:
                        self.output("  Invalid step number.")
                        continue
                else:
                    index = 0
                while index < len(steps):
                    key, prompt, required, kind = steps[index]
                    current_value = getattr(draft, key)
                    display_value = (
                        ", ".join(current_value)
                        if isinstance(current_value, tuple)
                        else current_value or "—"
                    )
                    raw = self._input(f"{prompt} [{display_value}]: ").strip()
                    if raw in {"<", "b", "back"}:
                        if index == 0:
                            self.output("  Already at the first step.")
                            continue
                        index -= 1
                        continue
                    if raw == ".":
                        index += 1
                        continue
                    if not raw:
                        if required and not current_value:
                            self.output("  Please provide a value.")
                            continue
                        if kind == "sequence":
                            setattr(
                                draft,
                                key,
                                current_value if isinstance(current_value, tuple) else tuple(),
                            )
                        else:
                            setattr(draft, key, current_value if current_value else "")
                        index += 1
                        continue
                    if kind == "sequence":
                        setattr(draft, key, _to_sequence(raw))
                    else:
                        setattr(draft, key, raw)
                    index += 1
                continue
            self.output("  Enter 'f', 'e', or 'c'.")

    def _summary_lines(self, draft: PersonaWizardDraft) -> list[str]:
        def fmt(value: object) -> str:
            if isinstance(value, tuple):
                return ", ".join(value) if value else "—"
            return value if isinstance(value, str) and value else "—"

        return [
            "",
            ":: Persona Draft Summary ::",
            f" 1. Name            : {fmt(draft.name)}",
            f" 2. Genre           : {fmt(draft.genre)}",
            f" 3. Mood            : {fmt(draft.mood)}",
            f" 4. Influences      : {fmt(draft.influences)}",
            f" 5. Descriptors     : {fmt(draft.descriptors)}",
            f" 6. Brief           : {fmt(draft.brief)}",
            f" 7. Visual palette  : {fmt(draft.visual_palette)}",
            f" 8. Narrative tone  : {fmt(draft.narrative_tone)}",
            f" 9. Safety notes    : {fmt(draft.safety_notes)}",
            f"10. Refinement instr: {fmt(draft.refinement_instructions)}",
        ]

    def _refine_with_ai(self, draft: PersonaWizardDraft) -> PersonaWizardDraft | None:
        generator = getattr(self.soul_forge, "persona_generator", None)
        if generator is None:
            self.output("  Persona generator unavailable.")
            return draft
        if getattr(generator, "prompt_agent", None) is None:
            self.output("  No AI provider configured; using heuristic fallback.")

        instructions = list(draft.refinement_instructions)
        while True:
            instruction = self._input(
                " Enter refinement note (blank to finish, 'c' to cancel): "
            ).strip()
            if not instruction:
                if not instructions:
                    self.output("  No instructions provided; skipping refinement.")
                    return draft
                break
            if instruction.lower() in {"c", "cancel"}:
                return None
            instructions.append(instruction)
            preview = self._generate_preview(draft, instructions)
            self.output("\n".join(self._summary_lines(preview)))
            decision = (
                self._input(" Accept refinement? [y]es / [n]o (add another) / [c]ancel: ")
                .strip()
                .lower()
            )
            if decision in {"y", "yes"}:
                preview.refinement_instructions = tuple(instructions)
                return preview
            if decision in {"c", "cancel"}:
                return None
            if decision in {"n", "no"}:
                continue
            self.output("  Enter 'y', 'n', or 'c'.")

        preview = self._generate_preview(draft, instructions)
        preview.refinement_instructions = tuple(instructions)
        return preview

    def _generate_preview(
        self, draft: PersonaWizardDraft, instructions: list[str]
    ) -> PersonaWizardDraft:
        request = SoulForgeRequest(
            name=draft.name,
            genre=draft.genre,
            mood=draft.mood,
            influences=draft.influences or ("experimental muse",),
            descriptors=draft.descriptors,
            brief=draft.brief or None,
            visual_palette=draft.visual_palette,
            narrative_tone=draft.narrative_tone or None,
            safety_notes=draft.safety_notes or None,
            refinement_instructions=instructions,
        ).to_persona_request()

        generator = self.soul_forge.persona_generator
        persona = generator.draft_persona(request)
        return PersonaWizardDraft(
            name=persona.name,
            genre=draft.genre,
            mood=draft.mood,
            influences=tuple(persona.influences) or draft.influences,
            descriptors=tuple(persona.persona_tags),
            brief=draft.brief,
            visual_palette=tuple(persona.visual_palette) or draft.visual_palette,
            narrative_tone=persona.narrative_tone or draft.narrative_tone,
            safety_notes=persona.safety_notes or draft.safety_notes,
            refinement_instructions=tuple(instructions),
        )

    def _prompt_required(self, prompt: str) -> str:
        while True:
            value = self._input(f"{prompt}: ").strip()
            if value:
                return value
            self.output("  Please provide a value.")

    def _prompt_optional(self, prompt: str, *, allow_empty: bool = True) -> str:
        while True:
            value = self._input(f"{prompt}: ").strip()
            if value:
                return value
            if allow_empty:
                return ""
            self.output("  Please provide a value or leave blank if not required.")

    def _prompt_confirm(self, prompt: str) -> bool:
        while True:
            selection = self._input(f"{prompt} ").strip().lower()
            if selection in {"y", "yes"}:
                return True
            if selection in {"n", "no"}:
                return False
            self.output("  Enter 'y' or 'n'.")


def main() -> None:
    """Entry point for python -m artist_matrix.tui."""

    TuiApp().run()


__all__ = ["TuiApp", "main", "TuiAssets", "SessionState"]
