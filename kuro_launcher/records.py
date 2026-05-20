from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CharacterRecord:
    yaml_path: Path
    conf_name: str
    conf_uid: str
    live2d_model_name: str
    avatar: str
    persona_prompt_path: str
    default_project_id: str


@dataclass(frozen=True)
class HistoryRecord:
    uid: str
    title: str
    preview: str
    timestamp: str
    is_empty: bool


@dataclass(frozen=True)
class MemoryRecord:
    entry_id: str
    content: str
    memory_type: str
    enabled: bool
    status: str
    scope_level: str
    source: str
    updated_at: str
