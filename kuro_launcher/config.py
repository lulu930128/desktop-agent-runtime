import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_VAR_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def _expand_vars(s: str, mapping: Dict[str, str]) -> str:
    # 支援 ${KEY} 形式
    def repl(m: re.Match) -> str:
        k = m.group(1)
        return mapping.get(k, m.group(0))
    return _VAR_PATTERN.sub(repl, s)


def _resolve_path(p: str, mapping: Dict[str, str]) -> Path:
    # 先做 ${KEY} 代換，再做 Windows %ENV% / Unix $ENV 展開
    expanded = _expand_vars(p, mapping)
    expanded = os.path.expandvars(expanded)
    return Path(expanded)


@dataclass(frozen=True)
class AppConfig:
    config_path: Path

    # paths
    root: Path
    open_llm_dir: Path
    characters_dir: Path
    bridge_dir: Path
    tts_dir: Path
    tts_infer_dir: Path
    tts_infer_default: str
    tts_infer_template: str
    env_tts: Path
    env_llm: Path
    runtime_conf_path: Path
    logs_dir: Path
    electron_lnk: Path

    # network
    bridge_host: str
    bridge_port: int
    tts_host: str
    tts_port: int
    llm_host: str
    llm_port: int

    # llm (provider / openai settings)
    llm_provider_env: str
    llm_default_provider: str
    openai_model_env: str
    openai_default_model: str
    openai_temp_env: str
    openai_inject_key_env: str
    openai_api_key_env: str
    openai_fallback_key_env: str

    # bridge routes
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


def load_config(config_path: Path) -> AppConfig:
    cfg = _read_yaml(config_path)

    cfg_dir = config_path.parent.resolve()

    # 第一階段 mapping：HERE
    mapping: Dict[str, str] = {
        "HERE": str(cfg_dir),
    }

    # ROOT 先解析出來
    root_str = (((cfg.get("paths") or {}).get("ROOT")) or "${HERE}").strip()
    root = _resolve_path(root_str, mapping).resolve()

    # 第二階段 mapping：ROOT + 會被引用到的其他 keys
    mapping["ROOT"] = str(root)

    paths = cfg.get("paths") or {}

    # 先把 open_llm_vtuber_dir 展開，後面的 keys 會用到它
    open_llm_dir = _resolve_path(str(paths.get("open_llm_vtuber_dir", "")), mapping).resolve()
    mapping["open_llm_vtuber_dir"] = str(open_llm_dir)

    # characters_dir 可能用 open_llm_vtuber_dir
    characters_dir = _resolve_path(str(paths.get("characters_dir", "")), mapping).resolve()
    mapping["characters_dir"] = str(characters_dir)

    bridge_dir = _resolve_path(str(paths.get("bridge_dir", "")), mapping).resolve()
    tts_dir = _resolve_path(str(paths.get("tts_dir", "")), mapping).resolve()
    mapping["bridge_dir"] = str(bridge_dir)
    mapping["tts_dir"] = str(tts_dir)


    # GPT-SoVITS infer configs dir (for per-character voice)
    # Default: <tts_dir>\GPT_SoVITS\configs
    tts_infer_dir = _resolve_path(
        str(paths.get("tts_infer_dir", "")) or str(tts_dir / "GPT_SoVITS" / "configs"),
        mapping
    ).resolve()
    tts_infer_default = str(paths.get("tts_infer_default", "tts_infer.yaml"))
    tts_infer_template = str(paths.get("tts_infer_template", "tts_infer_{character}.yaml"))
    env_tts = _resolve_path(str(paths.get("env_tts", "")), mapping).resolve()
    env_llm = _resolve_path(str(paths.get("env_llm", "")), mapping).resolve()
    runtime_conf_path = _resolve_path(str(paths.get("runtime_conf_path", "")), mapping).resolve()
    logs_dir = _resolve_path(str(paths.get("logs_dir", "")), mapping).resolve()
    electron_lnk = _resolve_path(str(paths.get("electron_lnk", "")), mapping).resolve()

    net = cfg.get("network") or {}
    b = net.get("bridge") or {}
    t = net.get("tts") or {}
    l = net.get("llm") or {}

    llm = cfg.get("llm") or {}
    oai = llm.get("openai") or {}

    br = cfg.get("bridge") or {}

    return AppConfig(
        config_path=config_path.resolve(),

        root=root,
        open_llm_dir=open_llm_dir,
        characters_dir=characters_dir,
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

        bridge_host=str(b.get("host", "127.0.0.1")),
        bridge_port=int(b.get("port", 1188)),
        tts_host=str(t.get("host", "127.0.0.1")),
        tts_port=int(t.get("port", 9881)),
        llm_host=str(l.get("host", "127.0.0.1")),
        llm_port=int(l.get("port", 23456)),

        llm_provider_env=str(llm.get("provider_env", "KURO_LLM_PROVIDER")),
        llm_default_provider=str(llm.get("default_provider", "openai_llm")),
        openai_model_env=str(oai.get("model_env", "OPENAI_LLM_MODEL")),
        openai_default_model=str(oai.get("default_model", "gpt-5-mini")),
        openai_temp_env=str(oai.get("temperature_env", "OPENAI_LLM_TEMPERATURE")),
        openai_inject_key_env=str(oai.get("inject_key_env", "OPENAI_LLM_INJECT_KEY")),
        openai_api_key_env=str(oai.get("api_key_env", "OPENAI_LLM_API_KEY")),
        openai_fallback_key_env=str(oai.get("fallback_api_key_env", "OPENAI_API_KEY")),

        bridge_translate_path=str(br.get("translate_path", "/translate")),
        bridge_debug_path=str(br.get("debug_path", "/translate_debug")),
    )
