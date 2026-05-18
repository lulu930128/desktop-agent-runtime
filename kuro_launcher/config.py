import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


_VAR_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def _expand_vars(value: str, mapping: Dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        return mapping.get(key, match.group(0))

    return _VAR_PATTERN.sub(repl, value)


def _resolve_path(value: str, mapping: Dict[str, str]) -> Path:
    expanded = _expand_vars(value, mapping)
    expanded = os.path.expandvars(expanded)
    return Path(expanded)


@dataclass(frozen=True)
class AppConfig:
    config_path: Path

    root: Path
    open_llm_dir: Path
    characters_dir: Path
    projects_dir: Path
    bridge_dir: Path
    tts_dir: Path
    tts_infer_dir: Path
    tts_infer_default: str
    tts_infer_template: str
    env_tts: Path
    env_llm: Path
    runtime_conf_path: Path
    logs_dir: Path
    electron_lnk: Optional[Path]
    pet_electron_dir: Path
    pet_electron_preferred: bool

    bridge_host: str
    bridge_port: int
    tts_host: str
    tts_port: int
    llm_host: str
    llm_port: int
    pet_control_host: str
    pet_control_port: int

    llm_provider_env: str
    llm_default_provider: str
    openai_model_env: str
    openai_default_model: str
    openai_temp_env: str
    openai_inject_key_env: str
    openai_api_key_env: str
    openai_fallback_key_env: str

    bridge_translate_path: str
    bridge_debug_path: str

    @property
    def bridge_url(self) -> str:
        return f"http://{self.bridge_host}:{self.bridge_port}"

    @property
    def bridge_translate_url(self) -> str:
        return f"{self.bridge_url}{self.bridge_translate_path}"

    @property
    def bridge_debug_url(self) -> str:
        return f"{self.bridge_url}{self.bridge_debug_path}"

    @property
    def llm_url(self) -> str:
        return f"http://{self.llm_host}:{self.llm_port}"

    @property
    def pet_control_url(self) -> str:
        return f"http://{self.pet_control_host}:{self.pet_control_port}"


def load_config(config_path: Path) -> AppConfig:
    cfg = _read_yaml(config_path)
    cfg_dir = config_path.parent.resolve()

    mapping: Dict[str, str] = {"HERE": str(cfg_dir)}
    paths = cfg.get("paths") or {}

    root_value = str(paths.get("ROOT") or "${HERE}").strip()
    root = _resolve_path(root_value, mapping).resolve()
    mapping["ROOT"] = str(root)

    open_llm_dir = _resolve_path(
        str(paths.get("open_llm_vtuber_dir") or ""),
        mapping,
    ).resolve()
    mapping["open_llm_vtuber_dir"] = str(open_llm_dir)

    characters_dir = _resolve_path(
        str(paths.get("characters_dir") or ""),
        mapping,
    ).resolve()
    mapping["characters_dir"] = str(characters_dir)

    projects_dir = _resolve_path(
        str(paths.get("projects_dir") or (root / "projects")),
        mapping,
    ).resolve()
    mapping["projects_dir"] = str(projects_dir)

    bridge_dir = _resolve_path(str(paths.get("bridge_dir") or ""), mapping).resolve()
    tts_dir = _resolve_path(str(paths.get("tts_dir") or ""), mapping).resolve()
    mapping["bridge_dir"] = str(bridge_dir)
    mapping["tts_dir"] = str(tts_dir)

    tts_infer_dir = _resolve_path(
        str(paths.get("tts_infer_dir") or (tts_dir / "GPT_SoVITS" / "configs")),
        mapping,
    ).resolve()

    tts_infer_default = str(paths.get("tts_infer_default") or "tts_infer.yaml")
    tts_infer_template = str(
        paths.get("tts_infer_template") or "tts_infer_{character}.yaml"
    )
    env_tts = _resolve_path(str(paths.get("env_tts") or ""), mapping).resolve()
    env_llm = _resolve_path(str(paths.get("env_llm") or ""), mapping).resolve()
    runtime_conf_path = _resolve_path(
        str(paths.get("runtime_conf_path") or ""),
        mapping,
    ).resolve()
    logs_dir = _resolve_path(str(paths.get("logs_dir") or ""), mapping).resolve()
    electron_lnk_value = str(paths.get("electron_lnk") or "").strip()
    electron_lnk = (
        _resolve_path(electron_lnk_value, mapping).resolve()
        if electron_lnk_value
        else None
    )
    pet_electron_dir = _resolve_path(
        str(paths.get("pet_electron_dir") or (root / "pet-electron")),
        mapping,
    ).resolve()
    pet_electron_preferred = bool(paths.get("pet_electron_preferred", True))

    net = cfg.get("network") or {}
    bridge_net = net.get("bridge") or {}
    tts_net = net.get("tts") or {}
    llm_net = net.get("llm") or {}
    pet_control_net = net.get("pet_control") or {}

    llm = cfg.get("llm") or {}
    openai = llm.get("openai") or {}
    bridge_cfg = cfg.get("bridge") or {}

    return AppConfig(
        config_path=config_path.resolve(),
        root=root,
        open_llm_dir=open_llm_dir,
        characters_dir=characters_dir,
        projects_dir=projects_dir,
        bridge_dir=bridge_dir,
        tts_dir=tts_dir,
        tts_infer_dir=tts_infer_dir,
        tts_infer_default=tts_infer_default,
        tts_infer_template=tts_infer_template,
        env_tts=env_tts,
        env_llm=env_llm,
        runtime_conf_path=runtime_conf_path,
        logs_dir=logs_dir,
        electron_lnk=electron_lnk,
        pet_electron_dir=pet_electron_dir,
        pet_electron_preferred=pet_electron_preferred,
        bridge_host=str(bridge_net.get("host", "127.0.0.1")),
        bridge_port=int(bridge_net.get("port", 1188)),
        tts_host=str(tts_net.get("host", "127.0.0.1")),
        tts_port=int(tts_net.get("port", 9881)),
        llm_host=str(llm_net.get("host", "127.0.0.1")),
        llm_port=int(llm_net.get("port", 23456)),
        pet_control_host=str(pet_control_net.get("host", "127.0.0.1")),
        pet_control_port=int(pet_control_net.get("port", 23567)),
        llm_provider_env=str(llm.get("provider_env", "KURO_LLM_PROVIDER")),
        llm_default_provider=str(llm.get("default_provider", "openai_llm")),
        openai_model_env=str(openai.get("model_env", "OPENAI_LLM_MODEL")),
        openai_default_model=str(openai.get("default_model", "gpt-4o")),
        openai_temp_env=str(openai.get("temperature_env", "OPENAI_LLM_TEMPERATURE")),
        openai_inject_key_env=str(
            openai.get("inject_key_env", "OPENAI_LLM_INJECT_KEY")
        ),
        openai_api_key_env=str(openai.get("api_key_env", "OPENAI_LLM_API_KEY")),
        openai_fallback_key_env=str(
            openai.get("fallback_api_key_env", "OPENAI_API_KEY")
        ),
        bridge_translate_path=str(bridge_cfg.get("translate_path", "/translate")),
        bridge_debug_path=str(bridge_cfg.get("debug_path", "/translate_debug")),
    )
