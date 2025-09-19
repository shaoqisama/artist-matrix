## FEATURE:

### User Story

When the user opens the TUI, they are presented with two options: **Generate Avatar** or **Select Avatar**.

* For first-time users, the natural flow is to generate a new avatar. The system guides them step by step, confirming inputs and saving the profile.
* Once the avatar is generated, the system also creates a visual representation (pixel art style) that the user can select and save.
* After confirming the avatar, the user moves into the creative chat space. Here, they can discuss lyrics, melodies, and arrangements with the AI artist, or simply have casual conversations.
* The music creation node is then activated to produce full tracks. The artwork node generates matching covers, and the video node can produce retro Nintendo-style colorful music videos.
* Once all assets are created, the pipeline concludes with a retro-inspired **TUI music player** that showcases the final output.
* Throughout, the interface maintains a **post-apocalyptic/retro sci-fi 8-bit style**, evoking the feel of classic Fallout or Alien terminals.

---

### Unified TUI Interface (UI Shell)

* **Style**: Post-apocalyptic 8-bit terminal aesthetic with green/amber monochrome display
* **Features**:

  * Interactive panels and menu system with ASCII art and retro typography
  * Real-time progress indicators with vintage computer aesthetics
  * Audio feedback with 8-bit sound effects (optional)
  * Cross-platform compatibility (Windows, macOS, Linux)
  * Responsive design that maintains aesthetic across terminal sizes
  * Chat-like interactive experience (similar to Claude Code or Codex)

---

### AI Music Avatar System — Four Core Nodes Architecture

**1) Soul Forge Agent (Avatar Layer)**

* **Purpose**: Creates and manages virtual music artist identities with unique personalities, styles, and backgrounds.
* **Process**:

  * Interactive TUI-guided artist creation with style generation (genre, era, aesthetic) via chat with agent
  * AI-generated backstory and personality traits using LLM Router (DeepSeek/Claude, task-based)
  * Visual avatar generation using **Stable Diffusion SDXL** (8‑bit/pixel‑art style prompts)
  * Persistent storage of artist profiles in JSON format with metadata
* **Input**: User preferences, style descriptions, artistic influences
* **Output**: Complete artist profile with image assets and personality blueprint

**2) Creation Engine Agent (Creation Layer)**

* **Purpose**: Generates complete music productions including lyrics, audio, and artwork via user chat with this agent (uses the selected virtual artist persona).
* **Process**:

  * Context-aware lyric generation based on artist personality and user themes
  * Music composition and production through **Suno AI API**
  * Album cover and artwork generation matching artist visual style (SDXL)
  * Optional MV/short video content creation via **RunwayML**
  * Quality control with human-in-the-loop approval mechanisms
  * **Voice identity**: default singing via Suno; optional speaking voice via **ElevenLabs** or **Coqui TTS** for promos/skits
* **Input**: Creative briefs, themes, mood descriptors, musical references
* **Output**: Finished songs (audio), lyrics documents, cover artwork, visual assets
* **Key Technologies**: Suno AI API, LLM Router (DeepSeek/Claude), SDXL, RunwayML

**3) Echo Chamber Node (Connection Layer)**

* **Purpose**: Manages social presence and fan interaction for virtual artists
* **Process**:

  * Automated social media content creation in artist's unique voice
  * Cross-platform posting to Twitter/X, Instagram, and Discord
  * Fan interaction simulation through AI-powered responses
  * Collaboration management between different virtual artists
  * Engagement analytics and performance tracking
* **Input**: New releases, upcoming events, fan interactions
* **Output**: Social media posts, engagement metrics, collaboration content
* **Key Technologies**: Twitter/X API, Instagram Graph API, Discord API, LLM Router

**4) World Stage Node (Ecosystem Layer)**

* **Purpose**: Handles distribution, commercialization, and platform presence
* **Process**:

  * Automated distribution to streaming platforms (Spotify, Apple Music, etc.)
  * YouTube content upload and channel management
  * Official website updates and portfolio maintenance
  * Digital merchandise creation and e-commerce integration
  * Performance analytics and royalty tracking
* **Input**: Completed music assets, release metadata, distribution preferences
* **Output**: Platform links, distribution reports, commercial performance data
* **Key Technologies**: DistroKid API, YouTube API, Webflow/WordPress API, e-commerce platforms

---

### Workflow Integration

* **State Management**: LangGraph-managed state object passed between nodes
* **LLM Router**: Task-based selection via **LiteLLM** (or custom ModelBroker) to route prompts to DeepSeek/Claude as appropriate
* **Prompt & Model Management**: Pydantic schemas to validate artist profiles, structured prompts, and workflow configurations (Pydantic Settings for env/config)
* **Job Handling**: Background processing for long renders (async tasks; optional queue like Dramatiq/Celery)
* **Error Handling**: Comprehensive error recovery and user-friendly messages
* **Approval Gates**: Human validation points at critical creative stages
* **Data Persistence**: Local asset storage with project manifests; optional cloud sync (S3/GCS)

---

### Schemas (Pydantic)

* **ArtistProfile**: `name, persona_tags[list[str]], lyric_style, visual_style, influences[list[str]], safety_notes, created_at, version`
* **TrackSpec**: `title, mood, tempo_bpm, key, references[list[str]], narrative, cover_style, video_style`
* **RenderJob**: `id, type["song"|"cover"|"video"], status, params, artifact_paths, started_at, finished_at, error`
* **Manifest**: Maps artifacts to hashes, prompts, seeds, and parameters per run

---

### Documentation: Tools & Frameworks

* **DeepSeek** (LLM) → [https://platform.deepseek.com/api-docs](https://platform.deepseek.com/api-docs)
* **LiteLLM** (multi-provider routing) → [https://docs.litellm.ai](https://docs.litellm.ai)
* **LangGraph** (state management) → [https://langchain-ai.github.io/langgraph/reference/](https://langchain-ai.github.io/langgraph/reference/)
* **Pydantic** (schemas & settings) → [https://docs.pydantic.dev](https://docs.pydantic.dev)
* **Stable Diffusion SDXL** (image gen) → [https://platform.stability.ai/docs](https://platform.stability.ai/docs)
* **Suno AI** (music gen) → [https://docs.suno.ai](https://docs.suno.ai)
* **RunwayML** (video gen) → [https://docs.runwayml.com](https://docs.runwayml.com)

---

