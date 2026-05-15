from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .utils import read_yaml_file


@dataclass(frozen=True)
class ProjectDefinition:
    path: Path
    project_id: str
    display_name: str
    project_root: Path
    project_prompt_path: Path
    tool_prompt_path: Path
    response_style_prompt_path: Path | None = None
    notes: str = ""


def _resolve_local_path(base_dir: Path, raw_value: str, fallback: str) -> Path:
    value = (raw_value or fallback).strip()
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def load_project_definition(project_yaml: Path) -> ProjectDefinition:
    project_yaml = Path(project_yaml).resolve()
    data = read_yaml_file(project_yaml)
    prompts = data.get("prompts") or {}
    if not isinstance(prompts, dict):
        prompts = {}

    project_dir = project_yaml.parent
    project_id = str(data.get("project_id") or project_dir.name).strip() or project_dir.name
    display_name = str(data.get("display_name") or project_id).strip() or project_id
    project_root = _resolve_local_path(
        project_dir,
        str(data.get("project_root") or project_dir),
        ".",
    )
    response_style_raw = str(prompts.get("response_style_prompt") or "").strip()

    return ProjectDefinition(
        path=project_yaml,
        project_id=project_id,
        display_name=display_name,
        project_root=project_root,
        project_prompt_path=_resolve_local_path(
            project_dir,
            str(prompts.get("project_prompt") or ""),
            "prompts/project_prompt.txt",
        ),
        tool_prompt_path=_resolve_local_path(
            project_dir,
            str(prompts.get("tool_prompt") or ""),
            "prompts/tool_prompt.txt",
        ),
        response_style_prompt_path=(
            _resolve_local_path(project_dir, response_style_raw, response_style_raw)
            if response_style_raw
            else None
        ),
        notes=str(data.get("notes") or "").strip(),
    )


def iter_project_files(projects_dir: Path) -> Iterable[Path]:
    projects_dir = Path(projects_dir)
    if not projects_dir.exists():
        return []
    files = sorted(projects_dir.rglob("project.yaml"))
    return [path for path in files if path.is_file()]


def list_project_definitions(projects_dir: Path) -> List[ProjectDefinition]:
    items: List[ProjectDefinition] = []
    for path in iter_project_files(projects_dir):
        try:
            items.append(load_project_definition(path))
        except Exception:
            continue
    return items
