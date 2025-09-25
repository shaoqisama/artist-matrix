"""Terminal UI shell for the Artist Matrix experience."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable

import logging

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
    TrackIdeationDraft,
    TrackIdeationLLM,
    TrackIdeationStore,
    TrackManifestRepository,
    SunoPayloadPreview,
    build_suno_preview,
    apply_llm_guidance,
    build_audio_generator,
    build_lyric_generator,
)
from artist_matrix.creation_engine.service import ArtworkJobSpec, TrackJobSpec
from artist_matrix.interfaces.production import LyricDraft, TrackArtifact
from artist_matrix.echo_chamber import SocialCampaign
from artist_matrix.state import ArtistMatrixSettings
from pydantic import ValidationError

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
        self.llm_client: TrackIdeationLLM | None = None

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
        while True:
            self.output(self.build_main_menu())
            choice = self._input("Select mode (1/2/Q): ").strip().lower()
            if choice in {"1", "g", "generate"}:
                self.handle_generate()
            elif choice in {"2", "s", "select"}:
                self.handle_select()
            elif choice in {"3", "c", "creation"}:
                self.handle_creation_menu()
            elif choice in {"4", "e", "echo"}:
                self.handle_echo_chamber()
            elif choice in {"q", "quit", "exit"}:
                self.output("Shutting down Artist Matrix shell. See you in the wasteland.")
                break
            else:
                self.output("Invalid selection. Enter 1, 2, or Q to exit.")

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
                self.output(
                    f"Last successful manifest stored at {self.session.last_manifest_path}"
                )
            return

        profile = result.get("profile")
        manifest_path = Path(str(result.get("manifest_path")))
        avatar = result.get("avatar")

        if isinstance(profile, ArtistProfile):
            self.session.last_profile = profile
            self._update_suggestions(profile, draft)
            default_draft = TrackIdeationDraft(
                persona_slug=profile.slug,
                title=f"{profile.name} Anthem",
                style=draft.mood or profile.visual_style,
                references=self.session.track_brief.track.references if self.session.track_brief else (),
                model=self.settings.creation_audio_model,
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
            summary.append(
                f" → Visual palette: {', '.join(draft.visual_palette)}"
            )
        if draft.narrative_tone:
            summary.append(f" → Narrative tone: {draft.narrative_tone}")
        if draft.safety_notes:
            summary.append(f" → Safety notes : {draft.safety_notes}")
        self.output("\n".join(summary))
        self._post_persona_prompt()

    def handle_select(self) -> None:
        self.output("\n>> Accessing artist archives...")
        records = self._load_persona_records()
        if not records:
            self.output(
            " No personas available. Use 'Generate Avatar' to forge a new profile."
            )
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
            descriptors=tuple(self._as_str_list(manifest.get("persona_tags", profile.persona_tags))),
            brief=self._as_str(manifest.get("brief", "")),
            visual_palette=tuple(self._as_str_list(manifest.get("visual_palette", []))),
            narrative_tone=self._as_str(manifest.get("narrative_tone", profile.lyric_style), profile.lyric_style),
            safety_notes=self._as_str(manifest.get("safety_notes", profile.safety_notes or "")),
            refinement_instructions=tuple(self._as_str_list(manifest.get("refinement_instructions", []))),
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
            selection = self._input(
                "Next action [c]reation workbench / [e]cho chamber / [m]ain menu: "
            ).strip().lower()
            if selection in {"c", "creation", "3"}:
                self.handle_creation_menu()
                return
            if selection in {"e", "echo", "4"}:
                self.handle_echo_chamber()
                return
            if selection in {"m", "menu", ""}:
                return
            self.output("  Enter 'c', 'e', or 'm'.")

    def handle_creation_engine(self) -> None:
        self.output("\n>> Creation Engine // Suggested Brief")
        brief = self.session.track_brief
        profile = self.session.last_profile
        if not brief or profile is None:
            self.output(" No persona selected. Generate or select a profile first.")
            return
        draft = self.session.track_draft
        if draft is not None:
            if not brief.track.references and draft.references:
                brief = CreationBrief(
                    track=TrackJobSpec(
                        title=draft.title or brief.track.title,
                        mood=draft.style or brief.track.mood,
                        tempo_bpm=brief.track.tempo_bpm,
                        key=brief.track.key,
                        references=tuple(draft.references),
                        narrative=brief.track.narrative,
                    ),
                    artwork=brief.artwork,
                    narrative=brief.narrative,
                )
                self.session.track_brief = brief
        track = brief.track
        self.output(f" Title       : {track.title}")
        self.output(f" Mood        : {track.mood}")
        self.output(f" References  : {', '.join(track.references) if track.references else '—'}")
        self.output(f" Narrative   : {track.narrative or '—'}")
        if draft is not None:
            self.output(" Draft summary")
            self.output(f"  Prompt      : {draft.prompt or '—'}")
            self.output(f"  Style       : {draft.style or '—'}")
            tags = ", ".join(draft.tags) if draft.tags else "—"
            self.output(f"  Tags        : {tags}")
            self.output(f"  Instrumental: {'yes' if draft.instrumental else 'no'}")
            if draft.lyrics:
                snippet = draft.lyrics.splitlines()[0][:80]
                self.output(f"  Lyrics seed : {snippet}{'…' if len(draft.lyrics) > 80 else ''}")
            if draft.summary:
                self.output("  Summary     :")
                self.output(f"   {draft.summary[:100]}{'…' if len(draft.summary) > 100 else ''}")
        if brief.artwork:
            self.output(" Artwork")
            self.output(f"  Style      : {brief.artwork.style}")
            refs = brief.artwork.references or []
            self.output(f"  References : {', '.join(refs) if refs else '—'}")
        if brief.narrative:
            self.output(f" Campaign narrative: {brief.narrative}")
        provider = self.settings.creation_audio_provider
        selection = self._input(
            f"Generate track via provider '{provider}'? [y/N]: "
        ).strip().lower()
        if selection not in {"y", "yes"}:
            self.output(" Creation cancelled; returning to main menu.")
            return

        self.output(f" Launching Creation Engine via provider '{provider}'...")
        try:
            result = self.creation_engine.produce_track(profile, brief)
        except Exception as exc:  # noqa: BLE001
            self.output(f"!! Creation Engine failure: {exc}")
            if self.session.last_track_manifest:
                self.output(
                    f" Last successful track manifest: {self.session.last_track_manifest}"
                )
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
                Path(item) if not isinstance(item, Path) else item
                for item in log_value
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
                summary.append(
                    f"   duration   : {track_artifact.duration_seconds:.0f}s"
                )
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
        if provider == "stub":
            summary.append(" (Stub provider wrote placeholder audio bytes.)")
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

    def handle_creation_menu(self) -> None:
        options = {
            "1": ("Discuss track concept", self.handle_creation_chat),
            "2": ("Review draft", self.handle_creation_draft_review),
            "3": ("Finalize draft", self.handle_creation_finalize),
            "4": ("Render with Suno", self.handle_creation_engine),
            "b": ("Back to main menu", None),
        }
        while True:
            self.output("\n>> Creation Workbench")
            for key, (label, _) in options.items():
                if key == "b":
                    self.output(f" [{key.upper()}] {label}")
                else:
                    self.output(f" [{key}] {label}")
            selection = self._input("Select action: ").strip().lower()
            if selection in {"b", "back", "exit", ""}:
                return
            entry = options.get(selection)
            if not entry:
                self.output("  Invalid selection.")
                continue
            _, handler = entry
            if handler is None:
                return
            handler()

    def _ensure_track_draft(self, profile: ArtistProfile) -> TrackIdeationDraft:
        draft = self.session.track_draft
        if draft is None or draft.persona_slug != profile.slug:
            draft = TrackIdeationDraft(
                persona_slug=profile.slug,
                title=f"{profile.name} Anthem",
                style=profile.lyric_style,
                references=profile.influences,
                model=self.settings.creation_audio_model,
            )
            self.session.track_draft = draft
        return draft

    def handle_creation_chat(self) -> None:
        profile = self.session.last_profile
        if profile is None:
            self.output(" No persona selected. Generate or select a profile first.")
            return
        draft = self._ensure_track_draft(profile)
        transcript = list(self.session.transcript)
        self.output("\n>> Creation Ideation // Chat Assistant")
        self.output(
            " Enter commands like 'title: Signal Burn' or 'tags: neon, cyberpunk'."
        )
        self.output(" Type 'done' when satisfied, 'help' for fields, or 'quit' to exit.")
        if self.ideation_llm is None:
            self.output(
                " AI assistant disabled (configure ARTIST_MATRIX_PERSONA_PROVIDER/MODEL/API_KEY for DeepSeek)."
            )
        session_turns: list[ChatTurn] = []
        while True:
            user_input = self._input("You> ").strip()
            if not user_input:
                continue
            lowered = user_input.lower()
            if lowered in {"quit", "cancel"}:
                self.output(" Chat cancelled; no changes committed.")
                return
            if lowered in {"done", "finish", "d"}:
                break
            if lowered == "help":
                self.output(
                    " Fields: title, prompt, style, tags, references, negative, instrumental,"
                    " model, lyrics, vocal, notes, style_weight, weirdness, audio_weight."
                    " Any other text is saved as a note."
                )
                continue

            transcript.append(ChatTurn(role="user", content=user_input))
            session_turns.append(ChatTurn(role="user", content=user_input))
            updated, draft = self._apply_draft_command(draft, user_input)
            self.session.track_draft = draft
            persona_summary = self._persona_summary(profile)
            llm_response = None
            if updated == "notes" or (updated is None and self.ideation_llm is not None):
                llm_response, draft = apply_llm_guidance(
                    self.ideation_llm,
                    persona_summary,
                    user_input,
                    transcript,
                    draft,
                )
                self.session.track_draft = draft
            if updated and updated != "notes":
                response = f"Updated {updated}."
                logger.debug(
                    "Track draft update",
                    extra={"persona": profile.slug, "field": updated},
                )
            elif llm_response:
                response = llm_response
            else:
                response = self._generate_stub_response(profile, draft, user_input)
            reply = ChatTurn(role="assistant", content=response)
            transcript.append(reply)
            session_turns.append(reply)
            self.output(f"AI> {response}")

        self.session.transcript = transcript
        try:
            self.ideation_store.save_draft(draft)
            self.ideation_store.append_transcript(profile.slug, session_turns)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to persist track ideation data",
                extra={"persona": profile.slug, "error": str(exc)},
            )
        self._sync_brief_with_draft(draft)
        self.output(" Draft saved. Use 'Review draft' to tweak fields or 'Render with Suno'.")

    def handle_creation_draft_review(self) -> None:
        profile = self.session.last_profile
        if profile is None:
            self.output(" No persona selected. Generate or select a profile first.")
            return
        draft = self._ensure_track_draft(profile)
        while True:
            self.output("\n:: Track Draft Summary ::")
            for line in self._draft_summary_lines(draft):
                self.output(f" {line}")
            self.output(
                " Commands -> 'field: value' to edit, 'sync' to update brief, 'save',"
                " 'reset', or 'back' to exit."
            )
            choice = self._input("draft> ").strip()
            if not choice:
                continue
            lowered = choice.lower()
            if lowered in {"back", "b", "exit"}:
                return
            if lowered in {"reset", "r"}:
                draft = TrackIdeationDraft(persona_slug=profile.slug)
                self.session.track_draft = draft
                self.output(" Draft reset.")
                continue
            if lowered in {"save", "s"}:
                try:
                    self.ideation_store.save_draft(draft)
                    self.output(" Draft persisted to disk.")
                except Exception as exc:  # noqa: BLE001
                    self.output(f" Failed to save draft: {exc}")
                continue
            if lowered in {"sync", "update"}:
                self._sync_brief_with_draft(draft)
                self.output(" Creation brief updated from draft.")
                continue
            updated, draft = self._apply_draft_command(draft, choice)
            self.session.track_draft = draft
            if updated:
                self.output(f" Updated {updated}.")
            else:
                self.output(" Unrecognised command; use 'field: value'.")

    def handle_creation_finalize(self) -> None:
        profile = self.session.last_profile
        if profile is None:
            self.output(" No persona selected. Generate or select a profile first.")
            return
        draft = self._ensure_track_draft(profile)
        brief = self.session.track_brief
        if brief is None:
            self.output(" No creation brief available. Generate or select a persona first.")
            return

        while True:
            self._sync_brief_with_draft(draft)
            brief = self.session.track_brief
            if brief is None:
                self.output(" Brief unavailable; returning to menu.")
                return
            preview = build_suno_preview(profile, draft, brief.track)
            self.output("\n:: Suno Payload Preview ::")
            for line in self._preview_lines(preview):
                self.output(f" {line}")
            self.output(
                " Options: [e]dit field / [s]ave / [r]ender / [b]ack"
            )
            choice = self._input("finalize> ").strip().lower()
            if choice in {"b", "back", "exit", ""}:
                return
            if choice in {"r", "render"}:
                draft = draft.model_copy(update={"finalized": True})
                draft.update_timestamp()
                self.session.track_draft = draft
                try:
                    self.ideation_store.save_draft(draft)
                    self.ideation_store.save_final(draft)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to persist final draft",
                        extra={"persona": profile.slug, "error": str(exc)},
                    )
                self.handle_creation_engine()
                return
            if choice in {"s", "save"}:
                draft = draft.model_copy(update={"finalized": True})
                draft.update_timestamp()
                self.session.track_draft = draft
                try:
                    self.ideation_store.save_draft(draft)
                    self.ideation_store.save_final(draft)
                    self.output(" Final draft saved.")
                except Exception as exc:  # noqa: BLE001
                    self.output(f" Failed to save final draft: {exc}")
                continue
            if choice in {"e", "edit"}:
                command = self._input(" field command (e.g. title: Solar Bounce): ").strip()
                if not command:
                    continue
                updated, draft = self._apply_draft_command(draft, command)
                self.session.track_draft = draft
                if updated:
                    self.output(f" Updated {updated}.")
                else:
                    self.output(" Unrecognised command; use 'field: value'.")
                continue
            self.output("  Enter 'e', 's', 'r', or 'b'.")

    def _apply_draft_command(
        self,
        draft: TrackIdeationDraft,
        command: str,
    ) -> tuple[str | None, TrackIdeationDraft]:
        if ":" not in command:
            notes = list(draft.notes)
            notes.append(command)
            new_draft = draft.model_copy(update={"notes": tuple(notes)})
            new_draft.update_timestamp()
            return "notes", new_draft
        key, raw_value = command.split(":", 1)
        key = key.strip().lower()
        value = raw_value.strip()
        updates: dict[str, object] | None = None
        if key in {"title", "prompt", "style", "model", "lyrics"}:
            updates = {key: value or None}
        elif key in {"tags", "references", "negative", "notes"}:
            items = tuple(part.strip() for part in value.split(",") if part.strip())
            field_map = {
                "tags": "tags",
                "references": "references",
                "negative": "negative_tags",
                "notes": "notes",
            }
            updates = {field_map[key]: items}
        elif key in {"instrumental", "custom", "custommode"}:
            truthy = value.lower() in {"yes", "y", "true", "1"}
            field = "instrumental" if key == "instrumental" else "custom_mode"
            updates = {field: truthy}
        elif key in {"vocal", "vocal_gender"}:
            updates = {"vocal_gender": value or None}
        elif key in {"style_weight", "weirdness", "weirdness_constraint", "audio_weight"}:
            try:
                number = float(value)
            except ValueError:
                return None, draft
            field_map = {
                "style_weight": "style_weight",
                "weirdness": "weirdness_constraint",
                "weirdness_constraint": "weirdness_constraint",
                "audio_weight": "audio_weight",
            }
            updates = {field_map[key]: number}
        else:
            return None, draft
        new_draft = draft.model_copy(update=updates)
        new_draft.update_timestamp()
        return key, new_draft

    def _generate_stub_response(
        self,
        profile: ArtistProfile,
        draft: TrackIdeationDraft,
        user_input: str,
    ) -> str:
        if "tags" in user_input.lower():
            focus = ", ".join(draft.tags) or "fresh references"
            return f"Locked in tags—{focus} will drive the vibe."
        if "instrumental" in user_input.lower():
            return "Instrumental preference captured. We'll tailor the arrangement accordingly."
        return (
            f"Channeling {profile.name}'s {profile.lyric_style}."
            " Keep refining or type 'done' to stage the render."
        )

    def _persona_summary(self, profile: ArtistProfile) -> str:
        influences = ", ".join(profile.influences) or "ambient inspirations"
        return f"{profile.name} ({profile.lyric_style}) influenced by {influences}"

    def _draft_summary_lines(self, draft: TrackIdeationDraft) -> Iterable[str]:
        fields = [
            ("Title", draft.title or "—"),
            (
                "Prompt",
                (draft.prompt or "—")[:80]
                + ("…" if draft.prompt and len(draft.prompt) > 80 else ""),
            ),
            ("Style", draft.style or "—"),
            ("Tags", ", ".join(draft.tags) or "—"),
            ("Negative", ", ".join(draft.negative_tags) or "—"),
            ("References", ", ".join(draft.references) or "—"),
            ("Instrumental", "yes" if draft.instrumental else "no"),
            (
                "Lyrics",
                (draft.lyrics or "—")[:80]
                + ("…" if draft.lyrics and len(draft.lyrics) > 80 else ""),
            ),
            ("Model", draft.model or "—"),
            ("Finalized", "yes" if draft.finalized else "no"),
            ("Updated", draft.updated_at.isoformat(timespec="seconds")),
        ]
        if draft.notes:
            latest_note = draft.notes[-1]
            fields.append(
                (
                    "Notes",
                    latest_note[:80] + ("…" if len(latest_note) > 80 else ""),
                )
            )
        for label, value in fields:
            yield f"{label:12}: {value}"

    def _preview_lines(self, preview: SunoPayloadPreview) -> Iterable[str]:
        tags = ", ".join(preview.tags) if preview.tags else "—"
        negative = ", ".join(preview.negative_tags) if preview.negative_tags else "—"
        lines = [
            f"Title        : {preview.title}",
            f"Prompt       : {preview.prompt[:100]}{'…' if len(preview.prompt) > 100 else ''}",
            f"Style        : {preview.style or '—'}",
            f"Tags         : {tags}",
            f"Negative tags: {negative}",
            f"Instrumental : {'yes' if preview.instrumental else 'no'}",
            f"Custom mode  : {'yes' if preview.custom_mode else 'no'}",
            f"Model        : {preview.model or '—'}",
        ]
        if preview.lyrics:
            snippet = preview.lyrics[:100]
            if len(preview.lyrics) > 100:
                snippet += "…"
            lines.append(f"Lyrics seed  : {snippet}")
        if preview.notes:
            note_snippet = preview.notes[:100]
            if len(preview.notes) > 100:
                note_snippet += "…"
            lines.append(f"Notes        : {note_snippet}")
        return lines

    def _sync_brief_with_draft(self, draft: TrackIdeationDraft) -> None:
        brief = self.session.track_brief
        if not brief:
            return
        references = draft.references or brief.track.references
        narrative = draft.prompt or brief.track.narrative
        updated_track = TrackJobSpec(
            title=draft.title or brief.track.title,
            mood=draft.style or brief.track.mood,
            tempo_bpm=brief.track.tempo_bpm,
            key=brief.track.key,
            references=tuple(references),
            narrative=narrative,
        )
        self.session.track_brief = CreationBrief(
            track=updated_track,
            artwork=brief.artwork,
            narrative=draft.notes[0] if draft.notes else brief.narrative,
        )


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
                            setattr(draft, key, current_value if isinstance(current_value, tuple) else tuple())
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
            decision = self._input(
                " Accept refinement? [y]es / [n]o (add another) / [c]ancel: "
            ).strip().lower()
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
