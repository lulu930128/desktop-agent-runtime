from __future__ import annotations

import datetime
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from open_llm_vtuber.character_memory_manager import (
    add_character_memory,
    compact_character_memories,
    delete_character_memory,
    list_character_memories,
    update_character_memory_status,
)

from .config import AppConfig
from .memory_support import (
    classify_memory_text,
    ensure_character_memory_root,
    memory_record_is_active,
    memory_status_from_entry,
)
from .procs import ManagedProc
from .project_manager import ProjectDefinition, list_project_definitions
from .records import CharacterRecord, HistoryRecord, MemoryRecord
from .runtime_conf import build_runtime_conf, write_runtime_conf
from .services import probe_tts, start_bridge, start_llm, start_tts, validate_profile_assets
from .text_helpers import (
    compact_history_text,
    derive_history_title,
    format_omi_evidence_event_inline,
    format_history_tool_event_inline,
    read_text_maybe,
    resolve_repo_path,
)
from .utils import (
    get_listening_pid_windows,
    http_get_json,
    http_post_json,
    log_ts,
    port_is_open,
    read_yaml_file,
    sanitize_ascii,
    taskkill_tree,
    windows_hidden_subprocess_kwargs,
)


LogCallback = Callable[[str], None]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MEMORY_STATUS_LABELS = {
    "active": "啟用",
    "pending_confirmation": "待確認",
    "superseded": "已取代",
    "disabled": "停用",
    "pending_delete": "待刪除",
}
EXPRESSION_PRESETS: dict[str, dict[str, object]] = {
    "neutral": {"label": "一般", "parameters": {}},
    "happy": {
        "label": "開心",
        "parameters": {
            "Param6": 1,
            "ParamCheek": 0.35,
            "ParamEyeLSmile": 0.65,
            "ParamEyeRSmile": 0.65,
            "ParamMouthForm": 0.28,
        },
    },
    "angry": {
        "label": "生氣",
        "parameters": {
            "Param7": 1,
            "ParamBrowLForm": -0.6,
            "ParamBrowRForm": -0.6,
            "ParamMouthForm": -0.32,
        },
    },
    "sad": {
        "label": "難過",
        "parameters": {
            "Param8": 1,
            "ParamBrowLY": -0.25,
            "ParamBrowRY": -0.25,
            "ParamMouthForm": -0.42,
        },
    },
    "cry": {
        "label": "哭哭",
        "parameters": {
            "Param9": 1,
            "Param91": 1,
            "Param92": 1,
            "Param93": 1,
            "Param94": 1,
            "ParamMouthForm": -0.4,
        },
    },
    "shy": {
        "label": "害羞",
        "parameters": {
            "Param6": 0.7,
            "ParamCheek": 0.85,
            "ParamEyeLSmile": 0.35,
            "ParamEyeRSmile": 0.35,
            "ParamMouthForm": 0.12,
        },
    },
    "thinking": {
        "label": "思考",
        "parameters": {
            "ParamBrowLY": 0.25,
            "ParamBrowRY": 0.25,
            "ParamMouthForm": -0.12,
        },
    },
}


@dataclass(frozen=True)
class RuntimeStatus:
    bridge: bool
    tts: bool
    llm: bool
    pet_shell: bool
    pet_mode: str = ""
    ws_connected: bool = False
    ai_state: str = ""
    conf_name: str = ""
    briefing_visible: bool = False
    briefing_date: str = ""
    briefing_updated_at: str = ""
    mic_enabled: bool = False
    camera_enabled: bool = False
    screen_enabled: bool = False
    browser_panel_enabled: bool = False
    reader_visible: bool = False
    pet_game_mode: bool = False
    current_outfit_id: str = ""
    current_expression_id: str = ""
    current_expression_label: str = ""
    current_history_uid: str = ""
    current_history_title: str = ""
    latest_user_text: str = ""
    latest_assistant_text: str = ""
    live2d_inspector_overlay_enabled: bool = False


@dataclass(frozen=True)
class BriefingSummary:
    ok: bool
    date: str = ""
    updated_at: str = ""
    title: str = ""
    section_counts: tuple[tuple[str, str, int], ...] = ()
    source_status: tuple[tuple[str, str, str], ...] = ()
    overview_items: tuple[tuple[str, str, str], ...] = ()
    sections: tuple["BriefingSection", ...] = ()
    error: str = ""


@dataclass(frozen=True)
class BriefingItem:
    text: str
    meta: str = ""
    priority: str = ""
    source: str = ""


@dataclass(frozen=True)
class BriefingModule:
    module_id: str
    title: str
    tag: str
    value: str
    unit: str
    items: tuple[BriefingItem, ...] = ()


@dataclass(frozen=True)
class BriefingSection:
    key: str
    label: str
    icon: str
    count: int
    subtitle: str
    accent: str
    modules: tuple[BriefingModule, ...] = ()


@dataclass(frozen=True)
class PreviewAsset:
    path: str = ""
    kind: str = ""
    error: str = ""


@dataclass(frozen=True)
class PromptPreview:
    key: str
    title: str
    content: str
    source: str = ""


@dataclass(frozen=True)
class HistoryMessage:
    role: str
    timestamp: str
    content: str


class QtLauncherController:
    """Backend controller for the Qt launcher.

    This intentionally keeps the existing runtime/data pipeline intact:
    - Open-LLM-VTuber and GPT-SoVITS still start through the same helper modules.
    - pet-electron still owns the Live2D shell and briefing store.
    - the Qt shell reads the existing control server instead of inventing a new store.
    """

    def __init__(self, cfg: AppConfig, log_cb: LogCallback):
        self.cfg = cfg
        self.log = log_cb
        self.proc_bridge: Optional[ManagedProc] = None
        self.proc_tts: Optional[ManagedProc] = None
        self.proc_llm: Optional[ManagedProc] = None
        self.proc_pet_electron: Optional[subprocess.Popen] = None
        self.work_panel_control_token = ""
        self.current_run_id: Optional[str] = None
        self.character_records: Dict[str, CharacterRecord] = {}
        self.project_records: Dict[str, ProjectDefinition] = {}
        self.selected_character_key = ""
        self.selected_project_key = ""
        self.outfit_id = "hoodie" if cfg.startup_outfit.strip().lower() == "hoodie" else "normal"
        self.thinking_power = "normal"
        configured_model = str(os.environ.get(cfg.openai_model_env) or cfg.openai_default_model).strip()
        self.llm_model = configured_model if configured_model in cfg.openai_models else cfg.openai_default_model
        self.reload_profiles()

    def reload_profiles(self) -> None:
        self.character_records = self._load_character_records()
        self.project_records = {
            str(project.path): project
            for project in list_project_definitions(self.cfg.projects_dir)
        }
        self.selected_character_key = (
            self._find_startup_character_key(self.cfg.startup_character)
            or next(iter(self.character_records), "")
        )
        self.selected_project_key = (
            self._find_startup_project_key(self.cfg.startup_project)
            or self._default_project_key_for_selected_character()
            or next(iter(self.project_records), "")
        )
        self.log(
            f"[{log_ts()}] Qt profiles loaded: "
            f"{len(self.character_records)} characters, {len(self.project_records)} projects."
        )

    def _load_character_records(self) -> Dict[str, CharacterRecord]:
        records: Dict[str, CharacterRecord] = {}
        if not self.cfg.characters_dir.exists():
            return records
        for path in sorted(self.cfg.characters_dir.glob("*.yaml")):
            try:
                data = read_yaml_file(path)
            except Exception as exc:
                self.log(f"[{log_ts()}] 角色 YAML 讀取失敗：{path.name} / {exc}")
                continue
            cc = data.get("character_config") or {}
            if not isinstance(cc, dict):
                cc = {}
            record = CharacterRecord(
                yaml_path=path,
                conf_name=str(cc.get("conf_name") or path.stem),
                conf_uid=str(cc.get("conf_uid") or ""),
                live2d_model_name=str(cc.get("live2d_model_name") or ""),
                avatar=str(cc.get("avatar") or ""),
                persona_prompt_path=str(cc.get("persona_prompt_path") or ""),
                default_project_id=str(cc.get("default_project_id") or ""),
            )
            records[str(path)] = record
        return records

    def _normalize_token(self, value: str) -> str:
        return sanitize_ascii(value).strip().lower().replace(" ", "").replace("_", "").replace("-", "")

    def _find_startup_character_key(self, value: str) -> Optional[str]:
        target = self._normalize_token(value)
        if not target:
            return None
        for key, record in self.character_records.items():
            tokens = {
                self._normalize_token(record.yaml_path.stem),
                self._normalize_token(record.yaml_path.name),
                self._normalize_token(record.conf_name),
                self._normalize_token(record.conf_uid),
                self._normalize_token(record.live2d_model_name),
            }
            if target in tokens:
                return key
        return None

    def _find_startup_project_key(self, value: str) -> Optional[str]:
        target = self._normalize_token(value)
        if not target:
            return None
        for key, project in self.project_records.items():
            tokens = {
                self._normalize_token(project.path.parent.name),
                self._normalize_token(project.project_id),
                self._normalize_token(project.display_name),
            }
            if target in tokens:
                return key
        return None

    def _default_project_key_for_selected_character(self) -> Optional[str]:
        character = self.selected_character()
        if not character or not character.default_project_id:
            return None
        target = self._normalize_token(character.default_project_id)
        for key, project in self.project_records.items():
            if target == self._normalize_token(project.project_id):
                return key
        return None

    def selected_character(self) -> Optional[CharacterRecord]:
        return self.character_records.get(self.selected_character_key)

    def selected_project(self) -> Optional[ProjectDefinition]:
        return self.project_records.get(self.selected_project_key)

    def set_selected_character(self, key: str) -> None:
        if key in self.character_records:
            self.selected_character_key = key
            default_project = self._default_project_key_for_selected_character()
            if default_project:
                self.selected_project_key = default_project

    def set_selected_project(self, key: str) -> None:
        if key in self.project_records:
            self.selected_project_key = key

    def set_outfit(self, outfit_id: str) -> None:
        self.outfit_id = outfit_id if outfit_id in {"normal", "hoodie"} else "normal"

    def set_thinking_power(self, thinking_power: str) -> None:
        aliases = {
            "low": "fast",
            "quick": "fast",
            "fast": "fast",
            "normal": "normal",
            "medium": "normal",
            "high": "deep",
            "deep": "deep",
        }
        self.thinking_power = aliases.get(str(thinking_power or "").strip().lower(), "normal")

    def set_llm_model(self, model: str) -> None:
        normalized = str(model or "").strip()
        if normalized not in self.cfg.openai_models:
            raise ValueError("選取的模型不在本機允許清單中。")
        self.llm_model = normalized

    def work_panel_profile_state(self) -> dict:
        character = self.selected_character()
        project = self.selected_project()
        characters = [
            {
                "id": record.conf_uid,
                "name": record.conf_name,
                "model": record.live2d_model_name,
                "default_project_id": record.default_project_id,
            }
            for record in self.character_records.values()
            if record.conf_uid
        ]
        projects = [
            {
                "id": record.project_id,
                "name": record.display_name,
            }
            for record in self.project_records.values()
            if record.project_id
        ]
        expressions = [
            {
                "id": expression_id,
                "label": str(preset.get("label") or expression_id),
                "parameters": dict(preset.get("parameters") or {}),
            }
            for expression_id, preset in EXPRESSION_PRESETS.items()
        ]
        return {
            "ok": True,
            "characters": characters,
            "projects": projects,
            "models": list(self.cfg.openai_models),
            "thinking_options": ["fast", "normal", "deep"],
            "expressions": expressions,
            "outfits": [
                {"id": "normal", "label": "一般"},
                {"id": "hoodie", "label": "帽T"},
            ],
            "selected": {
                "character_id": character.conf_uid if character else "",
                "project_id": project.project_id if project else "",
                "model": self.llm_model,
                "thinking_power": self.thinking_power,
            },
        }

    def apply_work_panel_profile(
        self,
        *,
        character_id: str,
        project_id: str,
        model: str,
        thinking_power: str,
    ) -> dict:
        character_key = next(
            (key for key, item in self.character_records.items() if item.conf_uid == character_id),
            "",
        )
        project_key = next(
            (key for key, item in self.project_records.items() if item.project_id == project_id),
            "",
        )
        if not character_key:
            raise ValueError("找不到選取的角色。")
        if not project_key:
            raise ValueError("找不到選取的專案。")

        previous = (
            self.selected_character_key,
            self.selected_project_key,
            self.llm_model,
            self.thinking_power,
        )
        try:
            self.set_selected_character(character_key)
            self.set_selected_project(project_key)
            self.set_llm_model(model)
            self.set_thinking_power(thinking_power)
            result = self.start_profile()
        except Exception:
            (
                self.selected_character_key,
                self.selected_project_key,
                self.llm_model,
                self.thinking_power,
            ) = previous
            raise
        return {
            "ok": True,
            "result": result,
            "profile": self.work_panel_profile_state(),
        }

    def work_panel_history_state(self, history_uid: str = "") -> dict:
        current_uid = self._runtime_current_history_uid()
        records = self.read_history_records()
        selected_uid = str(history_uid or current_uid).strip()
        messages = []
        if selected_uid:
            messages = [
                {
                    "role": item.role,
                    "timestamp": item.timestamp,
                    "content": item.content,
                }
                for item in self.read_history_timeline(selected_uid, limit=120)
            ]
        selected_record = next((item for item in records if item.uid == selected_uid), None)
        return {
            "ok": True,
            "current_history_uid": current_uid,
            "selected_history_uid": selected_uid,
            "title": selected_record.title if selected_record else "",
            "histories": [
                {
                    "uid": item.uid,
                    "title": item.title,
                    "preview": item.preview,
                    "timestamp": item.timestamp,
                    "is_empty": item.is_empty,
                }
                for item in records
            ],
            "messages": messages,
        }

    def work_panel_memory_state(self) -> dict:
        character = self.selected_character()
        records = self.read_memory_records()
        return {
            "ok": True,
            "character_id": character.conf_uid if character else "",
            "character_name": character.conf_name if character else "",
            "memories": [
                {
                    "id": item.entry_id,
                    "content": item.content,
                    "memory_type": item.memory_type,
                    "enabled": item.enabled,
                    "status": item.status,
                    "scope": item.scope_level,
                    "source": item.source,
                    "updated_at": item.updated_at,
                }
                for item in records
            ],
        }

    def work_panel_tool_policy_state(self) -> dict:
        policy_path = self.cfg.open_llm_dir / "tool_policy.json"
        catalog_path = self.cfg.open_llm_dir / "tool_catalog.json"
        policy: dict = {}
        catalog: dict = {}
        try:
            loaded = json.loads(policy_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                policy = loaded
        except Exception as exc:
            return {"ok": False, "error": f"工具政策讀取失敗：{exc}", "tools": []}
        try:
            loaded = json.loads(catalog_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                catalog = loaded
        except Exception:
            catalog = {}

        category_metadata = catalog.get("categories")
        category_metadata = category_metadata if isinstance(category_metadata, dict) else {}
        tool_config = policy.get("tools")
        tool_config = tool_config if isinstance(tool_config, dict) else {}
        tools = []
        for name, raw in tool_config.items():
            config = raw if isinstance(raw, dict) else {}
            mode = str(config.get("mode") or policy.get("default_mode") or "blocked").strip().lower()
            tools.append(
                {
                    "name": str(name),
                    "category": str(config.get("category") or "other"),
                    "mode": mode,
                    "allowed": mode not in {"blocked", "deny", "disabled", "confirm", "needs_confirmation"},
                    "reason": (
                        "目前 runtime 尚未提供逐次確認流程。"
                        if mode in {"confirm", "needs_confirmation"}
                        else "由本機 runtime policy 允許唯讀使用。"
                        if mode in {"read_only", "allowed", "auto"}
                        else "由本機 runtime policy 封鎖。"
                    ),
                }
            )
        categories = [
            {
                "id": str(category_id),
                "title": str(data.get("title") or category_id) if isinstance(data, dict) else str(category_id),
                "description": str(data.get("description") or "") if isinstance(data, dict) else "",
            }
            for category_id, data in category_metadata.items()
        ]
        return {
            "ok": True,
            "version": policy.get("version"),
            "default_mode": str(policy.get("default_mode") or "blocked"),
            "confirmation_available": False,
            "categories": categories,
            "tools": tools,
        }

    def preview_asset(self) -> PreviewAsset:
        character = self.selected_character()
        if not character:
            return PreviewAsset(error="尚未選擇角色。")
        path, kind = self._resolve_preview_asset(character)
        if not path:
            return PreviewAsset(
                kind=kind,
                error=(
                    "目前沒有整張角色預覽。請先啟動 Pet Shell 產生 Live2D 快照，"
                    "或在 avatars / live2d model folder 放置 preview PNG。"
                ),
            )
        return PreviewAsset(path=str(path), kind=kind)

    def _find_avatar_preview(self, character: CharacterRecord) -> Optional[Path]:
        avatars_dir = self.cfg.open_llm_dir / "avatars"
        if not avatars_dir.exists():
            return None

        avatar_name = (character.avatar or "").strip()
        if avatar_name:
            avatar_path = Path(avatar_name)
            candidates = []
            if avatar_path.is_absolute():
                candidates.append(avatar_path)
            else:
                candidates.append(avatars_dir / avatar_name)
                candidates.append(self.cfg.open_llm_dir / avatar_name)
            for candidate in candidates:
                if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
                    return candidate

        for stem in (character.conf_name, character.live2d_model_name):
            stem = (stem or "").strip()
            if not stem:
                continue
            for suffix in IMAGE_EXTENSIONS:
                candidate = avatars_dir / f"{stem}{suffix}"
                if candidate.exists():
                    return candidate

        targets = {
            self._normalize_token(character.conf_name),
            self._normalize_token(character.live2d_model_name),
        }
        for path in sorted(avatars_dir.iterdir()):
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            stem_norm = self._normalize_token(path.stem)
            if not stem_norm:
                continue
            for target in targets:
                if target and (
                    stem_norm == target
                    or stem_norm.startswith(target)
                    or target.startswith(stem_norm)
                ):
                    return path
        return None

    def _preferred_outfit_texture(
        self,
        character: CharacterRecord,
        outfit_id: Optional[str],
    ) -> Optional[Path]:
        model_root = self.cfg.open_llm_dir / "live2d-models" / character.live2d_model_name
        if not model_root.exists():
            return None
        texture_name = "texture_01.png" if outfit_id == "hoodie" else "texture_00.png"
        matches = sorted(
            path
            for path in model_root.rglob(texture_name)
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        return matches[0] if matches else None

    def _find_live2d_preview(
        self,
        character: CharacterRecord,
        outfit_id: Optional[str] = None,
    ) -> Optional[Path]:
        model_root = self.cfg.open_llm_dir / "live2d-models" / character.live2d_model_name
        if not model_root.exists():
            return None

        files = sorted(
            path
            for path in model_root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        for path in files:
            stem = path.stem.lower()
            if any(token in stem for token in ("preview", "thumbnail", "poster", "cover")):
                return path
        for path in files:
            if "texture" not in path.stem.lower():
                return path
        return None

    def _resolve_preview_asset(self, character: CharacterRecord) -> tuple[Optional[Path], str]:
        live2d_capture = self._capture_live2d_preview(character)
        if live2d_capture:
            return live2d_capture, "Live2D renderer preview"
        avatar = self._find_avatar_preview(character)
        if avatar:
            return avatar, "角色圖預覽"
        live2d = self._find_live2d_preview(character, self.outfit_id)
        if live2d:
            return live2d, "Live2D 素材預覽"
        return None, "尚未找到整張角色預覽"

    def _capture_live2d_preview(self, character: CharacterRecord) -> Optional[Path]:
        model_name = (character.live2d_model_name or "").strip()
        if not model_name:
            return None

        try:
            status = http_get_json(f"{self.cfg.pet_control_url}/status", timeout=1.2)
        except Exception:
            return None

        renderer = status.get("renderer") if isinstance(status, dict) else {}
        if not isinstance(renderer, dict):
            return None
        current_model_url = str(renderer.get("currentModelUrl") or "")
        if model_name.lower() not in current_model_url.lower():
            return None

        preview_query = urllib.parse.urlencode(
            {
                "outfitId": self.outfit_id,
                "parameterId": "Param10",
                "value": "1" if self.outfit_id == "hoodie" else "0",
            }
        )
        preview_url = f"{self.cfg.pet_control_url}/live2d-preview.png?{preview_query}"
        try:
            req = urllib.request.Request(preview_url, method="GET")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                image_bytes = resp.read()
        except Exception as exc:
            self.log(f"[{log_ts()}] Live2D preview capture failed: {exc}")
            return None

        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return None

        raw_key = sanitize_ascii(character.conf_name or model_name or "character")
        safe_key = "".join(
            ch if ch.isalnum() or ch in "._-" else "_"
            for ch in raw_key
        ).strip("._-") or "character"
        cache_dir = self.cfg.logs_dir / "ui_preview_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{safe_key}_live2d_preview.png"
        cache_path.write_bytes(image_bytes)
        return cache_path

    def read_prompt_preview(self, key: str) -> PromptPreview:
        character = self.selected_character()
        project = self.selected_project()
        key = (key or "persona").strip().lower()
        labels = {
            "persona": "角色",
            "project": "專案",
            "tool": "工具",
            "policy": "限制",
            "contract": "格式",
            "memory": "記憶",
        }
        content = ""
        source = ""

        if key == "persona" and character:
            path = resolve_repo_path(self.cfg.open_llm_dir, character.persona_prompt_path)
            content = read_text_maybe(path)
            source = str(path) if path else ""
            memory_text = self._format_memory_preview(character)
            if memory_text:
                content = (
                    f"{content.rstrip()}\n\n[角色長期記憶]\n{memory_text}"
                    if content.strip()
                    else f"[角色長期記憶]\n{memory_text}"
                )
        elif key == "memory" and character:
            content = self._format_memory_preview(character)
            source = str(self._memory_path_for_character(character) or "")
        elif key == "project" and project:
            content = read_text_maybe(project.project_prompt_path)
            source = str(project.project_prompt_path)
        elif key == "tool":
            tool_text = read_text_maybe(project.tool_prompt_path) if project else ""
            catalog_text = read_text_maybe(self.cfg.open_llm_dir / "tool_catalog.json")
            content = tool_text
            if catalog_text.strip():
                content = (
                    f"{content.rstrip()}\n\n[tool_catalog.json]\n{catalog_text}"
                    if content.strip()
                    else f"[tool_catalog.json]\n{catalog_text}"
                )
            source = str(project.tool_prompt_path) if project else str(self.cfg.open_llm_dir / "tool_catalog.json")
        elif key == "policy":
            policy_prompt_text = read_text_maybe(
                self.cfg.open_llm_dir / "prompts" / "utils" / "runtime_policy_prompt.txt"
            )
            policy_json_text = read_text_maybe(self.cfg.open_llm_dir / "tool_policy.json")
            strategy_text = read_text_maybe(self.cfg.open_llm_dir / "conversation_strategies.json")
            content = policy_prompt_text
            if policy_json_text.strip():
                content = (
                    f"{content.rstrip()}\n\n[tool_policy.json]\n{policy_json_text}"
                    if content.strip()
                    else policy_json_text
                )
            if strategy_text.strip():
                content = (
                    f"{content.rstrip()}\n\n[conversation_strategies.json]\n{strategy_text}"
                    if content.strip()
                    else f"[conversation_strategies.json]\n{strategy_text}"
                )
            source = str(self.cfg.open_llm_dir / "prompts" / "utils" / "runtime_policy_prompt.txt")
        elif key == "contract":
            path = self.cfg.open_llm_dir / "prompts" / "utils" / "response_contract_prompt.txt"
            content = read_text_maybe(path)
            source = str(path)

        return PromptPreview(
            key=key,
            title=labels.get(key, key),
            content=content or "目前沒有可顯示的內容。",
            source=source,
        )

    def _memory_path_for_character(
        self,
        character: Optional[CharacterRecord] = None,
    ) -> Optional[Path]:
        character = character or self.selected_character()
        if not character or not character.conf_uid:
            return None
        return (
            self.cfg.open_llm_dir
            / "memories"
            / "characters"
            / character.conf_uid
            / "long_term.json"
        )

    def read_memory_records(self) -> tuple[MemoryRecord, ...]:
        character = self.selected_character()
        if not character or not character.conf_uid:
            return ()
        try:
            ensure_character_memory_root(self.cfg.open_llm_dir)
            entries = list_character_memories(character.conf_uid, enabled_only=False)
        except Exception as exc:
            self.log(f"[{log_ts()}] 角色記憶讀取失敗：{exc}")
            return ()
        return self._memory_records_from_entries(entries)

    def _format_memory_preview(self, character: Optional[CharacterRecord] = None) -> str:
        records = self._read_memory_records_for(character) if character else self.read_memory_records()
        lines: list[str] = []
        for record in records:
            if not record.enabled or record.status != "active":
                continue
            label = MEMORY_STATUS_LABELS.get(record.status, record.status or "未知")
            lines.append(f"- [{label}] ({record.memory_type}) {record.content}")
        return "\n".join(lines)

    def _read_memory_records_for(self, character: CharacterRecord) -> tuple[MemoryRecord, ...]:
        if not character or not character.conf_uid:
            return ()
        try:
            ensure_character_memory_root(self.cfg.open_llm_dir)
            entries = list_character_memories(character.conf_uid, enabled_only=False)
        except Exception:
            return ()
        return self._memory_records_from_entries(entries)

    def _memory_records_from_entries(self, entries: object) -> tuple[MemoryRecord, ...]:
        if not isinstance(entries, list):
            return ()

        records: list[MemoryRecord] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("id") or "").strip()
            content = str(entry.get("content") or "").strip()
            if not entry_id or not content:
                continue
            records.append(
                MemoryRecord(
                    entry_id=entry_id,
                    content=content,
                    memory_type=str(entry.get("memory_type") or "fact"),
                    enabled=bool(entry.get("enabled", True)),
                    status=memory_status_from_entry(entry),
                    scope_level=str(entry.get("scope_level") or entry.get("scope") or "character"),
                    source=str(entry.get("source") or "unknown"),
                    updated_at=str(entry.get("updated_at") or ""),
                )
            )
        return tuple(records)

    def _selected_memory_record(self, entry_id: str) -> MemoryRecord:
        entry_id = (entry_id or "").strip()
        if not entry_id:
            raise ValueError("請先選擇一條記憶。")
        for record in self.read_memory_records():
            if record.entry_id == entry_id:
                return record
        raise ValueError("找不到這條記憶。")

    def _maybe_refresh_memory_prompt(self) -> None:
        if not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.1):
            return
        try:
            self.refresh_memory_prompt()
        except Exception as exc:
            self.log(f"[{log_ts()}] 角色記憶 prompt 暫未刷新：{exc}")

    def add_memory(self, content: str) -> bool:
        character = self.selected_character()
        if not character or not character.conf_uid:
            raise ValueError("請先選擇角色。")
        content = (content or "").strip()
        if not content:
            raise ValueError("記憶內容不可空白。")

        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed = add_character_memory(
            character.conf_uid,
            content,
            memory_type=classify_memory_text(content),
        )
        if changed:
            self.log(f"[{log_ts()}] 已新增角色記憶：{compact_history_text(content, 48)}")
            self._maybe_refresh_memory_prompt()
        else:
            self.log(f"[{log_ts()}] 角色記憶未新增，可能是重複內容或包含敏感資料。")
        return changed

    def set_memory_status(self, entry_id: str, status: str) -> bool:
        character = self.selected_character()
        if not character or not character.conf_uid:
            raise ValueError("請先選擇角色。")
        record = self._selected_memory_record(entry_id)
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed = update_character_memory_status(character.conf_uid, record.entry_id, status)
        if changed:
            label = MEMORY_STATUS_LABELS.get(status, status)
            self.log(f"[{log_ts()}] 已更新角色記憶狀態：{label}")
            self._maybe_refresh_memory_prompt()
        return changed

    def toggle_memory(self, entry_id: str) -> bool:
        record = self._selected_memory_record(entry_id)
        next_status = "disabled" if memory_record_is_active(record) else "active"
        return self.set_memory_status(record.entry_id, next_status)

    def approve_memory(self, entry_id: str) -> bool:
        return self.set_memory_status(entry_id, "active")

    def reject_memory(self, entry_id: str) -> bool:
        return self.set_memory_status(entry_id, "disabled")

    def delete_memory(self, entry_id: str) -> bool:
        character = self.selected_character()
        if not character or not character.conf_uid:
            raise ValueError("請先選擇角色。")
        record = self._selected_memory_record(entry_id)
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed = delete_character_memory(character.conf_uid, record.entry_id)
        if changed:
            self.log(f"[{log_ts()}] 已刪除角色記憶：{compact_history_text(record.content, 48)}")
            self._maybe_refresh_memory_prompt()
        return changed

    def compact_memory(self) -> dict:
        character = self.selected_character()
        if not character or not character.conf_uid:
            raise ValueError("請先選擇角色。")
        ensure_character_memory_root(self.cfg.open_llm_dir)
        changed, removed_count = compact_character_memories(character.conf_uid)
        if changed:
            self._maybe_refresh_memory_prompt()
        self.log(f"[{log_ts()}] 角色記憶已整理，合併/移除 {removed_count} 條。")
        return {"changed": changed, "removed_count": removed_count}

    def _history_dir_for_character(
        self,
        character: Optional[CharacterRecord] = None,
    ) -> Optional[Path]:
        character = character or self.selected_character()
        if not character or not character.conf_uid.strip():
            return None
        return self.cfg.open_llm_dir / "chat_history" / character.conf_uid.strip()

    def _history_file_for_character(
        self,
        history_uid: str,
        character: Optional[CharacterRecord] = None,
    ) -> Optional[Path]:
        history_dir = self._history_dir_for_character(character)
        history_uid = (history_uid or "").strip()
        if history_dir is None or not history_uid:
            return None
        return history_dir / f"{history_uid}.json"

    def _history_event_file_for_character(
        self,
        history_uid: str,
        character: Optional[CharacterRecord] = None,
    ) -> Optional[Path]:
        history_path = self._history_file_for_character(history_uid, character)
        if history_path is None:
            return None
        return history_path.with_suffix(".events.jsonl")

    def _safe_history_delete_paths(
        self,
        history_uid: str,
        character: Optional[CharacterRecord] = None,
    ) -> list[Path]:
        history_dir = self._history_dir_for_character(character)
        history_path = self._history_file_for_character(history_uid, character)
        event_path = self._history_event_file_for_character(history_uid, character)
        if history_dir is None or history_path is None:
            return []

        try:
            root = history_dir.resolve()
        except OSError:
            return []

        paths: list[Path] = []
        for path in (history_path, event_path):
            if path is None:
                continue
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            paths.append(path)
        return paths

    def _delete_history_files(
        self,
        history_uid: str,
        character: Optional[CharacterRecord] = None,
    ) -> int:
        deleted = 0
        for path in self._safe_history_delete_paths(history_uid, character):
            try:
                if path.exists():
                    path.unlink()
                    deleted += 1
            except OSError as exc:
                self.log(f"[{log_ts()}] 刪除聊天檔案失敗：{path.name} / {exc}")
        return deleted

    def _runtime_current_history_uid(self) -> str:
        if not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            return ""
        try:
            status = http_get_json(self.llm_launcher_endpoint("/launcher/status"), timeout=2.0)
        except Exception:
            return ""
        status_payload = status if isinstance(status, dict) else {}
        renderer = status_payload.get("renderer")
        renderer = renderer if isinstance(renderer, dict) else {}
        return str(
            status_payload.get("current_history_uid")
            or renderer.get("currentHistoryUid")
            or renderer.get("current_history_uid")
            or ""
        ).strip()

    def delete_history(self, history_uid: str) -> dict:
        character = self.selected_character()
        history_uid = (history_uid or "").strip()
        if not character:
            raise ValueError("請先選擇角色。")
        if not history_uid:
            raise ValueError("請先選擇要刪除的聊天。")

        records = {record.uid: record for record in self.read_history_records()}
        record = records.get(history_uid)
        active_history_uid = self._runtime_current_history_uid()
        deleted_count = self._delete_history_files(history_uid, character)
        if deleted_count <= 0:
            raise FileNotFoundError("找不到可刪除的聊天檔案。")

        switched = False
        warning = ""
        if history_uid == active_history_uid and port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            try:
                self.create_history()
                switched = True
            except Exception as exc:
                warning = f"目前 runtime 聊天刪掉了，但建立新聊天失敗：{exc}"
                self.log(f"[{log_ts()}] {warning}")

        title = record.title if record else history_uid
        self.log(f"[{log_ts()}] 已刪除聊天記錄：{title}")
        return {
            "deleted_count": deleted_count,
            "history_uid": history_uid,
            "title": title,
            "runtime_switched": switched,
            "warning": warning,
        }

    def read_history_records(self) -> tuple[HistoryRecord, ...]:
        history_dir = self._history_dir_for_character()
        if history_dir is None or not history_dir.exists():
            return ()

        items: list[HistoryRecord] = []
        for path in sorted(history_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, list):
                continue

            metadata = {}
            if payload and isinstance(payload[0], dict) and payload[0].get("role") == "metadata":
                metadata = payload[0]
            messages = [
                msg
                for msg in payload
                if isinstance(msg, dict) and msg.get("role") != "metadata"
            ]
            latest = messages[-1] if messages else None
            first_human = next(
                (
                    msg
                    for msg in messages
                    if msg.get("role") == "human" and isinstance(msg.get("content"), str)
                ),
                None,
            )
            title = str(metadata.get("title") or "").strip()
            generic_titles = {"新對話", "New Chat", "New conversation", "Untitled"}
            if not title or title in generic_titles:
                seed = ""
                if first_human:
                    seed = str(first_human.get("content") or "")
                elif latest:
                    seed = str(latest.get("content") or "")
                title = derive_history_title(seed) or "新對話"

            preview = str(metadata.get("last_preview") or "").strip()
            if not preview:
                preview = str(metadata.get("summary_short") or "").strip()
            if not preview and latest:
                preview = compact_history_text(str(latest.get("content") or ""), 88)

            timestamp = (
                str(metadata.get("updated_at") or "").strip()
                or (str(latest.get("timestamp") or "").strip() if latest else "")
                or str(metadata.get("timestamp") or "").strip()
            )
            items.append(
                HistoryRecord(
                    uid=path.stem,
                    title=title,
                    preview=preview,
                    timestamp=timestamp,
                    is_empty=len(messages) == 0,
                )
            )
        items.sort(key=lambda item: item.timestamp, reverse=True)
        return tuple(items)

    def read_history_messages(self, history_uid: str, *, limit: int = 80) -> tuple[HistoryMessage, ...]:
        path = self._history_file_for_character(history_uid)
        if path is None or not path.exists():
            return ()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return ()
        if not isinstance(payload, list):
            return ()

        messages: list[HistoryMessage] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role == "metadata":
                continue
            content = self._normalize_history_message_content(item.get("content"))
            if not content:
                continue
            messages.append(
                HistoryMessage(
                    role=role,
                    timestamp=str(item.get("timestamp") or "").strip(),
                    content=content,
                )
            )
        return tuple(messages[-limit:])

    def read_history_timeline(self, history_uid: str, *, limit: int = 120) -> tuple[HistoryMessage, ...]:
        messages = [
            {
                "role": item.role,
                "timestamp": item.timestamp,
                "content": item.content,
                "priority": 0 if item.role in {"human", "user"} else 2,
            }
            for item in self.read_history_messages(history_uid, limit=limit)
        ]

        event_path = self._history_event_file_for_character(history_uid)
        if event_path is not None and event_path.exists():
            try:
                lines = event_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                lines = []
            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if not isinstance(event, dict):
                    continue
                content = self._format_history_event(event)
                if not content:
                    continue
                event_type = str(event.get("type") or "").strip()
                messages.append(
                    {
                        "role": "event",
                        "timestamp": str(event.get("timestamp") or "").strip(),
                        "content": content,
                        "priority": 3 if event_type.startswith("memory") else 1,
                    }
                )

        messages.sort(key=lambda item: (str(item.get("timestamp") or ""), int(item.get("priority") or 0)))
        return tuple(
            HistoryMessage(
                role=str(item.get("role") or ""),
                timestamp=str(item.get("timestamp") or ""),
                content=str(item.get("content") or ""),
            )
            for item in messages[-limit:]
        )

    def _format_history_event(self, event: dict) -> str:
        event_type = str(event.get("type") or "").strip()
        if event_type == "omi_evidence":
            return format_omi_evidence_event_inline(event)
        if event_type == "tool_call":
            return format_history_tool_event_inline(event)

        title = str(event.get("title") or "").strip()
        if not title:
            title = "角色記憶" if event_type.startswith("memory") else "系統事件"
        status = str(event.get("status") or "").strip().lower()
        status_text = {
            "completed": "完成",
            "ok": "完成",
            "error": "錯誤",
            "blocked": "被擋下",
            "skipped": "略過",
        }.get(status, status)
        summary = compact_history_text(str(event.get("summary") or "").strip(), 140)
        headline = f"{title} · {status_text}" if status_text else title
        return f"{headline}\n{summary}" if summary else headline

    def _normalize_history_message_content(self, content) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(part.strip() for part in parts if part and part.strip())
        if content is None:
            return ""
        return str(content).strip()

    def pet_control_endpoint(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.cfg.pet_control_url}{path}"

    def llm_launcher_endpoint(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.cfg.llm_url}{path}"

    def _post_llm_launcher(self, path: str, payload: dict) -> dict:
        if not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            raise RuntimeError("LLM runtime 尚未在線，請先啟動 Profile。")
        try:
            result = http_post_json(self.llm_launcher_endpoint(path), payload, timeout=5.0)
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {}
            message = parsed.get("error") if isinstance(parsed, dict) else ""
            raise RuntimeError(message or f"LLM launcher API failed: HTTP {exc.code}") from exc
        if not result.get("ok", True):
            raise RuntimeError(str(result.get("error") or result.get("message") or "LLM launcher API failed."))
        return result

    def _decode_http_error(self, exc: urllib.error.HTTPError) -> tuple[int, dict, str]:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"data": payload}
        return exc.code, payload, raw

    def _read_launcher_status(self, *, wait_for_client: bool = False, timeout_s: float = 15.0) -> dict:
        deadline = time.time() + timeout_s
        last_status: dict = {}
        while True:
            try:
                status = http_get_json(self.llm_launcher_endpoint("/launcher/status"), timeout=5.0)
            except Exception:
                status = {}

            if isinstance(status, dict):
                last_status = status
                reason = str(status.get("reason") or "")
                ambiguous_target = "Multiple frontend clients" in reason or "not connected" in reason
                if not wait_for_client or status.get("target_client_uid") or ambiguous_target:
                    return status

            if not wait_for_client or time.time() >= deadline:
                return last_status
            time.sleep(0.25)

    def apply_history_choice(
        self,
        *,
        wait_for_client: bool,
        desired_history_uid: str = "",
        force_new: bool = False,
        selected_character: Optional[CharacterRecord] = None,
    ) -> dict:
        desired_history_uid = (desired_history_uid or "").strip()
        if not force_new and not desired_history_uid:
            return {"ok": True, "skipped": True, "message": "No history change requested."}

        if not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            raise RuntimeError("LLM runtime 尚未在線，請先啟動 Profile。")

        character = selected_character or self.selected_character()
        status = self._read_launcher_status(wait_for_client=wait_for_client)
        if not status or not status.get("target_client_uid"):
            reason = str(status.get("reason") or "前端尚未連線，聊天選擇暫時無法同步。")
            raise RuntimeError(reason)

        active_conf_uid = str(status.get("conf_uid") or status.get("default_conf_uid") or "").strip()
        if character and character.conf_uid and active_conf_uid and character.conf_uid != active_conf_uid:
            raise RuntimeError("目前執行中的角色與聊天列表角色不同，請先啟用角色後再切換聊天。")

        endpoint = "/launcher/create-history" if force_new else "/launcher/select-history"
        payload = {
            "target_client_uid": status.get("target_client_uid"),
            "trigger_source": "launcher-qt",
        }
        if desired_history_uid:
            payload["history_uid"] = desired_history_uid

        try:
            result = http_post_json(self.llm_launcher_endpoint(endpoint), payload, timeout=20.0)
        except urllib.error.HTTPError as exc:
            code, payload, raw = self._decode_http_error(exc)
            message = payload.get("error") or raw[:240] or f"HTTP {code}"
            raise RuntimeError(f"聊天切換失敗：HTTP {code} {message}") from exc
        except Exception as exc:
            raise RuntimeError(f"聊天切換失敗：{exc}") from exc

        if not result.get("ok", True):
            raise RuntimeError(str(result.get("error") or result.get("message") or "聊天切換失敗。"))

        if force_new:
            self.log(f"[{log_ts()}] {result.get('message') or '已建立新聊天。'}")
        else:
            self.log(f"[{log_ts()}] {result.get('message') or '聊天已切換。'}")
        return result

    def select_history(self, history_uid: str) -> dict:
        history_uid = (history_uid or "").strip()
        if not history_uid:
            raise ValueError("請先選擇一段聊天。")
        return self.apply_history_choice(
            wait_for_client=True,
            desired_history_uid=history_uid,
            force_new=False,
        )

    def create_history(self) -> dict:
        return self.apply_history_choice(wait_for_client=True, force_new=True)

    def refresh_memory_prompt(self) -> dict:
        result = self._post_llm_launcher(
            "/launcher/refresh-memory",
            {
                "trigger_source": "launcher-qt",
            },
        )
        self.log(f"[{log_ts()}] 已要求 runtime 刷新角色記憶 prompt。")
        return result

    def read_runtime_status(self) -> RuntimeStatus:
        bridge = port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.1)
        tts = port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.1)
        llm = port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.1)
        pet_shell = False
        pet_mode = ""
        ws_connected = False
        ai_state = ""
        conf_name = ""
        briefing_visible = False
        mic_enabled = False
        camera_enabled = False
        screen_enabled = False
        browser_panel_enabled = False
        reader_visible = False
        pet_game_mode = False
        current_outfit_id = ""
        current_expression_id = ""
        current_expression_label = ""
        current_history_uid = ""
        current_history_title = ""
        latest_user_text = ""
        latest_assistant_text = ""
        live2d_inspector_overlay_enabled = False
        briefing_date = ""
        briefing_updated_at = ""

        try:
            status = http_get_json(self.pet_control_endpoint("/status"), timeout=0.8)
            pet_shell = bool(status.get("ok"))
            pet_mode = str(status.get("mode") or "")
            renderer = status.get("renderer") or {}
            if isinstance(renderer, dict):
                ws_connected = bool(renderer.get("wsConnected"))
                ai_state = str(renderer.get("aiState") or "")
                conf_name = str(renderer.get("confName") or "")
                briefing_visible = bool(renderer.get("briefingVisible"))
                mic_enabled = bool(renderer.get("micEnabled"))
                camera_enabled = bool(renderer.get("cameraEnabled"))
                screen_enabled = bool(renderer.get("screenEnabled"))
                browser_panel_enabled = bool(renderer.get("browserPanelEnabled"))
                reader_visible = bool(renderer.get("readerVisible"))
                pet_game_mode = bool(renderer.get("petGameMode"))
                current_outfit_id = str(renderer.get("currentOutfitId") or "")
                current_expression_id = str(renderer.get("currentExpressionId") or "")
                current_expression_label = str(renderer.get("currentExpressionLabel") or "")
                current_history_uid = str(
                    renderer.get("currentHistoryUid")
                    or renderer.get("current_history_uid")
                    or ""
                )
                current_history_title = str(renderer.get("currentHistoryTitle") or "")
                latest_user_text = str(renderer.get("latestUserText") or "")
                latest_assistant_text = str(renderer.get("latestAssistantText") or "")
                live2d_inspector_overlay_enabled = bool(renderer.get("live2dInspectorOverlayEnabled"))
        except Exception:
            pet_shell = False

        try:
            briefing = http_get_json(self.pet_control_endpoint("/briefing"), timeout=0.8)
            snapshot = briefing.get("snapshot") or {}
            briefing_date = str(snapshot.get("date") or "")
            briefing_updated_at = str(snapshot.get("updatedAt") or briefing.get("updatedAt") or "")
        except Exception:
            pass

        return RuntimeStatus(
            bridge=bridge,
            tts=tts,
            llm=llm,
            pet_shell=pet_shell,
            pet_mode=pet_mode,
            ws_connected=ws_connected,
            ai_state=ai_state,
            conf_name=conf_name,
            briefing_visible=briefing_visible,
            briefing_date=briefing_date,
            briefing_updated_at=briefing_updated_at,
            mic_enabled=mic_enabled,
            camera_enabled=camera_enabled,
            screen_enabled=screen_enabled,
            browser_panel_enabled=browser_panel_enabled,
            reader_visible=reader_visible,
            pet_game_mode=pet_game_mode,
            current_outfit_id=current_outfit_id,
            current_expression_id=current_expression_id,
            current_expression_label=current_expression_label,
            current_history_uid=current_history_uid,
            current_history_title=current_history_title,
            latest_user_text=latest_user_text,
            latest_assistant_text=latest_assistant_text,
            live2d_inspector_overlay_enabled=live2d_inspector_overlay_enabled,
        )

    def read_briefing_summary(self) -> BriefingSummary:
        try:
            payload = http_get_json(self.pet_control_endpoint("/briefing"), timeout=2.0)
        except Exception as exc:
            return BriefingSummary(ok=False, error=str(exc))

        snapshot = payload.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            return BriefingSummary(ok=False, error="Briefing payload has no snapshot.")

        section_counts: list[tuple[str, str, int]] = []
        sections: list[BriefingSection] = []
        for section in snapshot.get("sections") or []:
            if not isinstance(section, dict):
                continue
            parsed_section = self._parse_briefing_section(section)
            sections.append(parsed_section)
            section_counts.append(
                (
                    parsed_section.key,
                    parsed_section.label,
                    parsed_section.count,
                )
            )

        source_status: list[tuple[str, str, str]] = []
        for source in snapshot.get("sourceStatus") or []:
            if not isinstance(source, dict):
                continue
            source_status.append(
                (
                    str(source.get("label") or source.get("id") or ""),
                    str(source.get("status") or ""),
                    str(source.get("message") or ""),
                )
            )

        overview_items: list[tuple[str, str, str]] = []
        overview = next(
            (
                section
                for section in snapshot.get("sections") or []
                if isinstance(section, dict) and section.get("key") == "overview"
            ),
            None,
        )
        if isinstance(overview, dict):
            for module in overview.get("modules") or []:
                if not isinstance(module, dict):
                    continue
                title = str(module.get("title") or "")
                value = str(module.get("value") or "")
                unit = str(module.get("unit") or "")
                overview_items.append((title, value, unit))

        return BriefingSummary(
            ok=bool(payload.get("ok", True)),
            date=str(snapshot.get("date") or ""),
            updated_at=str(snapshot.get("updatedAt") or payload.get("updatedAt") or ""),
            title=str(snapshot.get("title") or "今日簡報"),
            section_counts=tuple(section_counts),
            source_status=tuple(source_status),
            overview_items=tuple(overview_items),
            sections=tuple(sections),
        )

    def refresh_daily_briefing(self) -> dict:
        try:
            result = http_post_json(
                self.pet_control_endpoint("/briefing/mail/refresh"),
                {},
                timeout=90.0,
            )
        except urllib.error.HTTPError as exc:
            code, payload, raw = self._decode_http_error(exc)
            message = payload.get("error") or payload.get("message") or raw[:240] or f"HTTP {code}"
            raise RuntimeError(f"每日 Briefing 更新失敗：HTTP {code} {message}") from exc
        except Exception as exc:
            raise RuntimeError(f"每日 Briefing 更新失敗：{exc}") from exc

        if not result.get("ok", True):
            raise RuntimeError(str(result.get("error") or result.get("message") or "每日 Briefing 更新失敗。"))
        self.log(f"[{log_ts()}] {result.get('message') or '每日 Briefing 已更新。'}")
        return result

    def _parse_briefing_section(self, section: dict) -> BriefingSection:
        modules: list[BriefingModule] = []
        for module in section.get("modules") or []:
            if not isinstance(module, dict):
                continue
            items: list[BriefingItem] = []
            for item in module.get("items") or []:
                if not isinstance(item, dict):
                    continue
                items.append(
                    BriefingItem(
                        text=str(item.get("text") or item.get("title") or "").strip(),
                        meta=str(item.get("meta") or "").strip(),
                        priority=str(item.get("priority") or "").strip(),
                        source=str(item.get("source") or "").strip(),
                    )
                )
            modules.append(
                BriefingModule(
                    module_id=str(module.get("id") or "").strip(),
                    title=str(module.get("title") or "").strip(),
                    tag=str(module.get("tag") or "").strip(),
                    value=str(module.get("value") or "").strip(),
                    unit=str(module.get("unit") or "").strip(),
                    items=tuple(items),
                )
            )
        return BriefingSection(
            key=str(section.get("key") or "").strip(),
            label=str(section.get("label") or section.get("key") or "").strip(),
            icon=str(section.get("icon") or "").strip(),
            count=int(section.get("count") or 0),
            subtitle=str(section.get("subtitle") or "").strip(),
            accent=str(section.get("accent") or "").strip(),
            modules=tuple(modules),
        )

    def _ensure_bridge_on_start(self) -> None:
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            self.log(f"[{log_ts()}] 注意：目前環境裡沒有 OPENAI_API_KEY。")

        proc = start_bridge(self.cfg, self.log, logs_root=self.cfg.logs_dir, run_id=None)
        if proc is not None:
            self.proc_bridge = proc

        for _ in range(40):
            if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.2):
                break
            time.sleep(0.2)

        if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] Bridge 已上線：{self.cfg.bridge_url}")
        else:
            self.log(f"[{log_ts()}] Bridge 沒有成功上線，請查看 bridge log。")

    def toggle_bridge(self) -> None:
        if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] 正在停止 Bridge...")
            self._stop_bridge_impl(kill_external=True)
            return
        self.log(f"[{log_ts()}] 正在啟動 Bridge...")
        self._ensure_bridge_on_start()

    def restart_bridge(self) -> None:
        self.log(f"[{log_ts()}] 正在重啟 Bridge...")
        self._stop_bridge_impl(kill_external=True)
        for _ in range(10):
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.2):
                break
            time.sleep(0.2)
        self._ensure_bridge_on_start()

    def translate_debug(self) -> dict:
        if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            raise RuntimeError("Bridge 尚未啟動，無法測試 translate debug。")
        response = http_post_json(
            self.cfg.bridge_debug_url,
            {"text": "你好，這是一個 translate debug 測試。"},
            timeout=12.0,
        )
        self.log(f"[{log_ts()}] translate_debug => {response}")
        return response

    def _apply_history_choice_after_start(
        self,
        character: CharacterRecord,
        *,
        desired_history_uid: str,
        force_new_history: bool,
    ) -> dict:
        if not force_new_history and not (desired_history_uid or "").strip():
            return {"ok": True, "skipped": True}
        try:
            return self.apply_history_choice(
                wait_for_client=True,
                selected_character=character,
                desired_history_uid=desired_history_uid,
                force_new=force_new_history,
            )
        except Exception as exc:
            warning = f"Profile 已啟動，但聊天選擇未同步：{exc}"
            self.log(f"[{log_ts()}] {warning}")
            return {"ok": False, "warning": warning}

    def start_profile(
        self,
        *,
        desired_history_uid: str = "",
        force_new_history: bool = False,
    ) -> dict:
        character = self.selected_character()
        project = self.selected_project()
        if not character:
            raise ValueError("請先選擇角色。")
        if not project:
            raise ValueError("請先選擇專案。")

        if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] Bridge 尚未啟動，先補啟動。")
            self._ensure_bridge_on_start()
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
                raise RuntimeError("Bridge 仍未成功上線。")

        runtime_conf, char_cfg = self._prepare_runtime_profile(character, project)
        if runtime_conf is None or char_cfg is None:
            raise RuntimeError("runtime profile 準備失敗。")

        if port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
            if self._try_hot_switch_profile(runtime_conf, char_cfg, character, project):
                self.launch_pet_electron()
                self.apply_outfit(wait_for_shell=True)
                history_result = self._apply_history_choice_after_start(
                    character,
                    desired_history_uid=desired_history_uid,
                    force_new_history=force_new_history,
                )
                result = {"ok": True, "mode": "hot-switch", "history": history_result}
                if history_result.get("warning"):
                    result["warning"] = history_result["warning"]
                return result
            raise RuntimeError("LLM 已在執行但無法熱切換；請先停止 profile 再重新啟動。")

        previous_llm_pid = get_listening_pid_windows(self.cfg.llm_port)
        self.stop_profile(silent=True, stop_bridge=False)

        for name, host, port in [
            ("TTS", self.cfg.tts_host, self.cfg.tts_port),
            ("LLM", self.cfg.llm_host, self.cfg.llm_port),
        ]:
            closed, message = self._wait_for_port_closed(name, host, port, timeout_s=15.0)
            if not closed:
                raise RuntimeError(message)

        self.proc_tts = start_tts(
            self.cfg,
            self.log,
            character_name=character.yaml_path.stem,
            logs_root=self.cfg.logs_dir,
            run_id=self.current_run_id or "manual",
        )
        self.log(f"[{log_ts()}] TTS 已啟動，等待 smoke test 成功...")
        tts_ready, tts_message = self._wait_for_tts_smoke_ready(
            self.proc_tts,
            char_cfg,
            timeout_s=120.0,
        )
        if not tts_ready:
            self.stop_profile(silent=True)
            raise RuntimeError(tts_message)
        self.log(f"[{log_ts()}] TTS smoke test：{tts_message}")

        self.proc_llm = start_llm(
            self.cfg,
            self.log,
            logs_root=self.cfg.logs_dir,
            run_id=self.current_run_id or "manual",
        )
        llm_ready, llm_message = self._wait_for_service_ready(
            "LLM",
            self.cfg.llm_host,
            self.cfg.llm_port,
            self.proc_llm,
            timeout_s=35.0,
            previous_pid=previous_llm_pid,
        )
        if not llm_ready:
            raise RuntimeError(llm_message)

        self.log(f"[{log_ts()}] {llm_message}：{self.cfg.llm_url}")
        self.launch_pet_electron()
        self.apply_outfit(wait_for_shell=True)
        history_result = self._apply_history_choice_after_start(
            character,
            desired_history_uid=desired_history_uid,
            force_new_history=force_new_history,
        )
        result = {"ok": True, "mode": "fresh-start", "history": history_result}
        if history_result.get("warning"):
            result["warning"] = history_result["warning"]
        return result

    def stop_profile(self, *, silent: bool = False, stop_bridge: bool = True) -> None:
        self.stop_pet_electron(silent=silent)

        if self.proc_llm:
            try:
                self.proc_llm.stop()
                if not silent:
                    self.log(f"[{log_ts()}] 已停止 LLM。")
            except Exception:
                pass
            self.proc_llm = None

        if self.proc_tts:
            try:
                self.proc_tts.stop()
                if not silent:
                    self.log(f"[{log_ts()}] 已停止 TTS。")
            except Exception:
                pass
            self.proc_tts = None

        for port, name in [(self.cfg.llm_port, "LLM"), (self.cfg.tts_port, "TTS")]:
            pid = get_listening_pid_windows(port)
            if pid:
                try:
                    taskkill_tree(pid)
                    if not silent:
                        self.log(f"[{log_ts()}] 已清理 {name} PID={pid}")
                except Exception:
                    pass

        if stop_bridge:
            bridge_was_running = bool(self.proc_bridge) or port_is_open(
                self.cfg.bridge_host,
                self.cfg.bridge_port,
                0.1,
            )
            self._stop_bridge_impl(kill_external=True)
            if bridge_was_running and not silent:
                self.log(f"[{log_ts()}] 已停止 Bridge。")

    def _prepare_runtime_profile(
        self,
        character: CharacterRecord,
        project: ProjectDefinition,
    ) -> tuple[Optional[Dict[str, object]], Optional[Dict[str, object]]]:
        errors, warnings = validate_profile_assets(self.cfg, character.yaml_path)
        for warning in warnings:
            self.log(f"[{log_ts()}] 警告：{warning}")
        if errors:
            self.log(f"[{log_ts()}] 角色設定檢查失敗：{character.yaml_path.name}")
            for error in errors:
                self.log(f"[{log_ts()}]   - {error}")
            return None, None

        self.log(
            f"[{log_ts()}] 準備 runtime conf：{character.conf_name} / {project.display_name}"
        )
        try:
            runtime_conf, char_cfg = build_runtime_conf(
                open_llm_dir=self.cfg.open_llm_dir,
                character_yaml=character.yaml_path,
                project_yaml=project.path,
                llm_host=self.cfg.llm_host,
                llm_port=self.cfg.llm_port,
                bridge_translate_url=self.cfg.bridge_translate_url,
                tts_host=self.cfg.tts_host,
                tts_port=self.cfg.tts_port,
                llm_provider_env=self.cfg.llm_provider_env,
                llm_default_provider=self.cfg.llm_default_provider,
                openai_model_env=self.cfg.openai_model_env,
                openai_default_model=self.cfg.openai_default_model,
                openai_temp_env=self.cfg.openai_temp_env,
                openai_inject_key_env=self.cfg.openai_inject_key_env,
                openai_api_key_env=self.cfg.openai_api_key_env,
                openai_fallback_key_env=self.cfg.openai_fallback_key_env,
                thinking_power=self.thinking_power,
                openai_model_override=self.llm_model,
            )
            write_runtime_conf(self.cfg.runtime_conf_path, runtime_conf)
            conf_uid = str(char_cfg.get("conf_uid") or "").strip()
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.current_run_id = f"{ts}_{conf_uid or character.yaml_path.stem}"
            self.log(f"[{log_ts()}] runtime conf: {self.cfg.runtime_conf_path}")
            self.log(f"[{log_ts()}] active_project_id: {char_cfg.get('active_project_id', '')}")
            self.log(f"[{log_ts()}] thinking_power: {self.thinking_power}")
            self.log(f"[{log_ts()}] llm_model: {self.llm_model}")
            return runtime_conf, char_cfg
        except Exception as exc:
            self.log(f"[{log_ts()}] 準備 runtime conf 失敗：{exc}")
            return None, None

    def _try_hot_switch_profile(
        self,
        runtime_conf: Dict[str, object],
        char_cfg: Dict[str, object],
        character: CharacterRecord,
        project: ProjectDefinition,
    ) -> bool:
        self.log(
            f"[{log_ts()}] 偵測到 LLM 已在執行，嘗試熱切換 {character.conf_name} / {project.display_name}。"
        )
        try:
            status = http_get_json(f"{self.cfg.llm_url}/launcher/status", timeout=5.0)
        except Exception as exc:
            self.log(f"[{log_ts()}] 讀取熱切換狀態失敗：{exc}")
            return False

        if not bool(status.get("can_hot_switch")):
            self.log(f"[{log_ts()}] 目前不能熱切換：{status.get('reason') or 'unknown'}")
            return False

        if self._should_restart_tts_for_switch(status, char_cfg):
            if not self._restart_tts_runtime(character, char_cfg):
                return False

        payload = {
            "runtime_config": runtime_conf,
            "target_client_uid": status.get("target_client_uid"),
            "trigger_source": "launcher-qt",
        }
        try:
            result = http_post_json(
                f"{self.cfg.llm_url}/launcher/switch-profile",
                payload,
                timeout=20.0,
            )
        except Exception as exc:
            self.log(f"[{log_ts()}] 熱切換請求失敗：{exc}")
            return False

        self.log(f"[{log_ts()}] {result.get('message') or '熱切換完成。'}")
        return True

    def _should_restart_tts_for_switch(self, status: dict, char_cfg: Dict[str, object]) -> bool:
        if not port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.2):
            return True
        desired_conf_uid = str(char_cfg.get("conf_uid") or "").strip()
        desired_conf_name = str(char_cfg.get("conf_name") or "").strip()
        current_conf_uid = str(status.get("conf_uid") or status.get("default_conf_uid") or "").strip()
        current_conf_name = str(status.get("conf_name") or status.get("default_conf_name") or "").strip()
        if desired_conf_uid and current_conf_uid:
            return desired_conf_uid != current_conf_uid
        if desired_conf_name and current_conf_name:
            return desired_conf_name != current_conf_name
        return True

    def _restart_tts_runtime(self, character: CharacterRecord, char_cfg: Dict[str, object]) -> bool:
        self.log(f"[{log_ts()}] 重新載入 TTS：{character.yaml_path.stem}")
        self._stop_tts_impl(kill_external=True)
        closed, message = self._wait_for_port_closed(
            "TTS",
            self.cfg.tts_host,
            self.cfg.tts_port,
            timeout_s=15.0,
        )
        if not closed:
            self.log(f"[{log_ts()}] TTS 關閉等待失敗：{message}")
            return False
        try:
            self.proc_tts = start_tts(
                self.cfg,
                self.log,
                character_name=character.yaml_path.stem,
                logs_root=self.cfg.logs_dir,
                run_id=self.current_run_id or "manual",
            )
        except Exception as exc:
            self.log(f"[{log_ts()}] TTS 重新載入失敗：{exc}")
            return False
        ready, ready_message = self._wait_for_tts_smoke_ready(self.proc_tts, char_cfg, timeout_s=120.0)
        if not ready:
            self.log(f"[{log_ts()}] TTS 重新載入後沒有成功上線：{ready_message}")
            return False
        self.log(f"[{log_ts()}] TTS 熱切換 smoke test：{ready_message}")
        return True

    def _recent_process_log_excerpt(self, proc: Optional[ManagedProc], *, max_lines: int = 10) -> str:
        if not proc or not proc.combined_path.exists():
            return ""
        try:
            lines = proc.combined_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return ""
        tail = [line.rstrip() for line in lines[-max_lines:] if line.strip()]
        return "\n".join(tail)

    def _wait_for_port_closed(self, name: str, host: str, port: int, *, timeout_s: float) -> tuple[bool, str]:
        deadline = time.time() + timeout_s
        last_pid: Optional[int] = None
        while time.time() < deadline:
            pid = get_listening_pid_windows(port)
            if pid:
                last_pid = pid
            if not port_is_open(host, port, 0.2):
                return True, f"{name} port {port} 已釋放"
            time.sleep(0.25)
        pid = get_listening_pid_windows(port) or last_pid
        if pid:
            return False, f"{name} port {port} 仍被占用（PID={pid}）"
        return False, f"{name} port {port} 在 {timeout_s:.0f}s 內沒有釋放"

    def _wait_for_service_ready(
        self,
        name: str,
        host: str,
        port: int,
        proc: Optional[ManagedProc],
        *,
        timeout_s: float,
        previous_pid: Optional[int] = None,
        stable_hits_required: int = 3,
    ) -> tuple[bool, str]:
        deadline = time.time() + timeout_s
        stable_hits = 0
        while time.time() < deadline:
            if proc and proc.popen and proc.popen.poll() is not None:
                excerpt = self._recent_process_log_excerpt(proc)
                message = f"{name} 程序提前結束，exit code={proc.popen.returncode}"
                if excerpt:
                    message += f"\n最近 log：\n{excerpt}"
                return False, message
            listener_pid = get_listening_pid_windows(port)
            is_open = port_is_open(host, port, 0.2)
            if is_open and listener_pid and previous_pid and listener_pid == previous_pid:
                stable_hits = 0
                time.sleep(0.25)
                continue
            if is_open:
                stable_hits += 1
                if stable_hits >= stable_hits_required:
                    return True, f"{name} 已上線（PID={listener_pid}）" if listener_pid else f"{name} 已上線"
            else:
                stable_hits = 0
            time.sleep(0.25)
        excerpt = self._recent_process_log_excerpt(proc)
        message = f"{name} 在 {timeout_s:.0f}s 內沒有成功上線"
        if excerpt:
            message += f"\n最近 log：\n{excerpt}"
        return False, message

    def _wait_for_tts_smoke_ready(
        self,
        proc: Optional[ManagedProc],
        char_cfg: Dict[str, object],
        *,
        timeout_s: float,
    ) -> tuple[bool, str]:
        deadline = time.time() + timeout_s
        last_probe_message = ""
        saw_port = False
        while time.time() < deadline:
            if proc and proc.popen and proc.popen.poll() is not None:
                excerpt = self._recent_process_log_excerpt(proc)
                message = f"TTS 啟動後提前結束，exit code={proc.popen.returncode}"
                if excerpt:
                    message += f"\n最近 log：\n{excerpt}"
                return False, message
            if not port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.2):
                time.sleep(0.4)
                continue
            saw_port = True
            ok, message = probe_tts(
                self.cfg,
                char_cfg,
                logs_root=self.cfg.logs_dir,
                run_id=self.current_run_id or "manual",
                request_timeout_s=25.0,
            )
            if ok:
                return True, message
            last_probe_message = message
            time.sleep(1.0)
        excerpt = self._recent_process_log_excerpt(proc)
        message = f"TTS port 已開，但 {timeout_s:.0f}s 內 smoke test 沒成功" if saw_port else f"TTS 在 {timeout_s:.0f}s 內沒有成功開 port"
        if last_probe_message:
            message += f"：{last_probe_message}"
        if excerpt:
            message += f"\n最近 log：\n{excerpt}"
        return False, message

    def _pet_electron_runtime(self) -> tuple[Optional[Path], Optional[str]]:
        pet_dir = self.cfg.pet_electron_dir
        if not pet_dir.exists():
            return None, "找不到 pet-electron 專案資料夾。"
        electron_exe = pet_dir / "node_modules" / "electron" / "dist" / "electron.exe"
        if electron_exe.exists():
            return electron_exe, None
        package_json = pet_dir / "package.json"
        if package_json.exists():
            return None, f"pet-electron 尚未安裝依賴，請先在 {pet_dir} 執行 npm install。"
        return None, "pet-electron 缺少 package.json。"

    def launch_pet_electron(self) -> bool:
        if self.proc_pet_electron and self.proc_pet_electron.poll() is None:
            self.log(f"[{log_ts()}] 自製桌寵殼已在執行中。")
            return True
        if port_is_open(self.cfg.pet_control_host, self.cfg.pet_control_port, 0.2):
            self.log(f"[{log_ts()}] 自製桌寵殼控制端已在線。")
            return True

        runtime_exe, reason = self._pet_electron_runtime()
        if runtime_exe is None:
            if reason:
                self.log(f"[{log_ts()}] 新桌寵殼未啟動：{reason}")
            return False

        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        popen_kwargs = windows_hidden_subprocess_kwargs(creationflags)
        env = os.environ.copy()
        env["KURO_BACKEND_BASE_URL"] = self.cfg.llm_url
        env["KURO_BACKEND_WS_URL"] = f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws"
        env["KURO_PET_CONTROL_HOST"] = self.cfg.pet_control_host
        env["KURO_PET_CONTROL_PORT"] = str(self.cfg.pet_control_port)
        env["KURO_LAUNCHER_CONTROL_URL"] = self.cfg.launcher_control_url
        if self.work_panel_control_token:
            env["KURO_LAUNCHER_CONTROL_TOKEN"] = self.work_panel_control_token
        self.proc_pet_electron = subprocess.Popen(
            [str(runtime_exe), "."],
            cwd=str(self.cfg.pet_electron_dir),
            close_fds=True,
            env=env,
            **popen_kwargs,
        )
        self.log(f"[{log_ts()}] 已開啟自製桌寵殼：{self.cfg.pet_electron_dir}")
        return True

    def stop_pet_electron(self, *, silent: bool = False) -> None:
        stopped = False
        if self.proc_pet_electron and self.proc_pet_electron.poll() is None:
            try:
                taskkill_tree(self.proc_pet_electron.pid)
                stopped = True
            except Exception:
                try:
                    self.proc_pet_electron.terminate()
                    stopped = True
                except Exception:
                    pass
        self.proc_pet_electron = None

        pid = get_listening_pid_windows(self.cfg.pet_control_port)
        if pid:
            try:
                taskkill_tree(pid)
                stopped = True
            except Exception:
                pass
        if stopped and not silent:
            self.log(f"[{log_ts()}] 已停止自製桌寵殼。")

    def apply_outfit(self, *, wait_for_shell: bool = False) -> None:
        outfit_value = 1 if self.outfit_id == "hoodie" else 0
        outfit_label = "帽T" if self.outfit_id == "hoodie" else "原版"
        if wait_for_shell:
            for _ in range(30):
                if port_is_open(self.cfg.pet_control_host, self.cfg.pet_control_port, 0.25):
                    break
                time.sleep(0.25)
        try:
            http_post_json(
                self.pet_control_endpoint("/command"),
                {
                    "action": "set-outfit",
                    "outfitId": self.outfit_id,
                    "parameterId": "Param10",
                    "value": outfit_value,
                },
                timeout=5.0,
            )
            self.log(f"[{log_ts()}] 已切換服裝：{outfit_label}")
        except Exception as exc:
            self.log(f"[{log_ts()}] 切換服裝失敗：{exc}")
            raise RuntimeError(f"切換服裝失敗：{exc}") from exc

    def run_pet_command(self, action: str, payload: Optional[dict] = None) -> dict:
        body = {"action": action}
        if payload:
            body.update(payload)
        result = http_post_json(self.pet_control_endpoint("/command"), body, timeout=5.0)
        if not result.get("ok", True):
            inner = result.get("result") if isinstance(result.get("result"), dict) else {}
            message = result.get("message") or inner.get("error") or "pet command failed"
            raise RuntimeError(str(message))
        self.log(f"[{log_ts()}] {result.get('message') or f'已送出 {action}'}")
        return result

    def set_pet_toggle(self, action: str, enabled: bool) -> dict:
        allowed = {
            "set-reader-visible",
            "set-briefing-visible",
            "mic-toggle",
            "toggle-camera",
            "toggle-screen",
            "toggle-browser",
            "set-game-mode",
            "set-live2d-inspector",
        }
        if action not in allowed:
            raise ValueError(f"Unsupported pet toggle action: {action}")
        return self.run_pet_command(action, {"enabled": bool(enabled)})

    def interrupt_pet(self) -> dict:
        return self.run_pet_command("interrupt")

    def show_pet(self) -> dict:
        return self.run_pet_command("show-pet")

    def move_pet_next_display(self) -> dict:
        return self.run_pet_command("move-next-display")

    def reload_pet_frontend(self) -> dict:
        return self.run_pet_command("reload-frontend")

    def apply_pet_backend_config(
        self,
        *,
        base_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        reload: bool = True,
    ) -> dict:
        base_url = (base_url or self.cfg.llm_url).strip()
        ws_url = (ws_url or f"ws://{self.cfg.llm_host}:{self.cfg.llm_port}/client-ws").strip()
        if not base_url or not ws_url:
            raise ValueError("桌寵後端 Base URL 和 WebSocket URL 不可空白。")
        result = http_post_json(
            self.pet_control_endpoint("/backend-config"),
            {
                "baseUrl": base_url,
                "wsUrl": ws_url,
                "reload": bool(reload),
            },
            timeout=8.0,
        )
        self.log(f"[{log_ts()}] {result.get('message') or '已套用桌寵後端端點。'}")
        return result

    def send_pet_text(self, text: str, attachments: Optional[list[dict]] = None) -> dict:
        text = (text or "").strip()
        attachments = attachments or []
        if not text and not attachments:
            raise ValueError("訊息不可空白。")
        return self.run_pet_command(
            "send-text",
            {
                "text": text,
                "attachments": attachments,
            },
        )

    def send_pet_text_for_chat(
        self,
        text: str,
        attachments: Optional[list[dict]] = None,
        *,
        create_history: bool = False,
    ) -> dict:
        result: dict = {
            "ok": True,
            "history": {},
            "send": {},
        }
        if create_history:
            history_result = self.create_history()
            result["history"] = history_result
            history_uid = str(history_result.get("history_uid") or "").strip()
            if history_uid:
                result["history_uid"] = history_uid
                time.sleep(0.2)

        result["send"] = self.send_pet_text(text, attachments)
        return result

    def expression_options(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (expression_id, str(data.get("label") or expression_id))
            for expression_id, data in EXPRESSION_PRESETS.items()
        )

    def set_expression(self, expression_id: str) -> dict:
        expression_id = (expression_id or "neutral").strip()
        preset = EXPRESSION_PRESETS.get(expression_id)
        if not preset:
            raise ValueError(f"Unsupported expression: {expression_id}")
        parameters = preset.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        return self.run_pet_command(
            "set-expression",
            {
                "expressionId": expression_id,
                "expressionLabel": str(preset.get("label") or expression_id),
                "parameters": parameters,
            },
        )

    def open_logs_dir(self) -> None:
        self.cfg.logs_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(self.cfg.logs_dir))
        else:
            webbrowser.open(self.cfg.logs_dir.as_uri())

    def _stop_bridge_impl(self, *, kill_external: bool = False) -> None:
        if self.proc_bridge:
            try:
                self.proc_bridge.stop()
            except Exception:
                pass
            self.proc_bridge = None
        if kill_external:
            pid = get_listening_pid_windows(self.cfg.bridge_port)
            if pid:
                try:
                    taskkill_tree(pid)
                except Exception:
                    pass

    def _stop_tts_impl(self, *, kill_external: bool = False) -> None:
        if self.proc_tts:
            try:
                self.proc_tts.stop()
            except Exception:
                pass
            self.proc_tts = None
        if kill_external:
            pid = get_listening_pid_windows(self.cfg.tts_port)
            if pid:
                try:
                    taskkill_tree(pid)
                except Exception:
                    pass

    def close(self) -> None:
        self.stop_profile(silent=True)
