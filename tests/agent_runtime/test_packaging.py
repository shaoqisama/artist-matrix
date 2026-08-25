from __future__ import annotations

import importlib.resources
import shutil
import subprocess
import zipfile
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_FILES = {
    "creation_engine.md",
    "director.md",
    "echo_chamber.md",
    "soul_forge.md",
    "world_stage.md",
}


def test_native_agent_prompts_are_importable_resources() -> None:
    prompt_root = importlib.resources.files("artist_matrix.prompts.agents")

    for filename in _PROMPT_FILES:
        content = prompt_root.joinpath(filename).read_text(encoding="utf-8")
        assert content.startswith("# ")
        assert "proposal" in content.lower()

    creation_prompt = importlib.resources.files("artist_matrix.prompts.creation").joinpath(
        "ideation_system.md"
    )
    persona_prompt = importlib.resources.files("artist_matrix.prompts.persona").joinpath(
        "deepseek_artist_template.md"
    )
    assert "collaborative music production coach" in creation_prompt.read_text(encoding="utf-8")
    assert "music persona architect" in persona_prompt.read_text(encoding="utf-8")


def test_built_wheel_contains_native_agent_prompts(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(_PROJECT_ROOT / "src", project / "src")
    shutil.copy2(_PROJECT_ROOT / "pyproject.toml", project / "pyproject.toml")
    wheel_dir = tmp_path / "dist"
    wheel_dir.mkdir()
    uv = shutil.which("uv")
    assert uv is not None, "the repository's required uv executable is unavailable"

    subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(wheel_dir)],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )

    (wheel,) = wheel_dir.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        packaged_prompts = {
            Path(name).name
            for name in names
            if name.startswith("artist_matrix/prompts/agents/") and name.endswith(".md")
        }

    assert packaged_prompts == _PROMPT_FILES
    assert {
        "artist_matrix/prompts/creation/ideation_system.md",
        "artist_matrix/prompts/persona/deepseek_artist_template.md",
    } <= names
