import os
from pathlib import Path
from typing import Any, Dict, Tuple

from .project_manager import load_project_definition
from .utils import deep_merge, read_yaml_file, sanitize_ascii, write_yaml_file


def _normalize_thinking_power(value: str) -> str:
    normalized = (value or "normal").strip().lower()
    aliases = {
        "quick": "fast",
        "light": "fast",
        "fast": "fast",
        "normal": "normal",
        "medium": "normal",
        "default": "normal",
        "deep": "deep",
        "depth": "deep",
        "high": "deep",
    }
    return aliases.get(normalized, "normal")


def _resolve_repo_path(repo_root: Path, raw_path: str) -> str:
    raw_path = (raw_path or "").strip()
    if not raw_path:
        return ""
    path = Path(raw_path)
    if path.is_absolute():
        return path.as_posix()
    return (repo_root / path).resolve().as_posix()


def find_base_conf(open_llm_dir: Path) -> Path:
    candidates = [
        open_llm_dir / "configs" / "conf.yaml",
        open_llm_dir / "conf.yaml",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Could not find a base conf.yaml.\n  - "
        + "\n  - ".join(str(item) for item in candidates)
    )


def build_runtime_conf(
    open_llm_dir: Path,
    character_yaml: Path,
    project_yaml: Path | None,
    llm_host: str,
    llm_port: int,
    bridge_translate_url: str,
    llm_provider_env: str,
    llm_default_provider: str,
    openai_model_env: str,
    openai_default_model: str,
    openai_temp_env: str,
    openai_inject_key_env: str,
    openai_api_key_env: str,
    openai_fallback_key_env: str,
    thinking_power: str = "normal",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    base_conf_path = find_base_conf(open_llm_dir)
    base = read_yaml_file(base_conf_path)
    character_data = read_yaml_file(character_yaml)
    merged = deep_merge(base, character_data)
    repo_root = open_llm_dir.parent.resolve()

    merged.setdefault("system_config", {})
    merged["system_config"]["host"] = llm_host
    merged["system_config"]["port"] = llm_port
    merged["system_config"]["thinking_power"] = _normalize_thinking_power(thinking_power)
    tool_prompts = merged["system_config"].setdefault("tool_prompts", {})
    if isinstance(tool_prompts, dict):
        tool_prompts.setdefault("response_contract_prompt", "response_contract_prompt")
        tool_prompts.setdefault("runtime_policy_prompt", "runtime_policy_prompt")

    merged.setdefault("translator_config", {})
    translator_cfg = merged["translator_config"]
    translator_cfg["translate_provider"] = "deeplx"
    translator_cfg.setdefault("deeplx", {})
    translator_cfg["deeplx"]["deeplx_api_endpoint"] = bridge_translate_url

    character_cfg = merged.setdefault("character_config", {})
    tts_cfg = character_cfg.get("tts_config")
    if isinstance(tts_cfg, dict):
        gsv_cfg = tts_cfg.get("gpt_sovits_tts")
        if isinstance(gsv_cfg, dict):
            gsv_cfg["ref_audio_path"] = _resolve_repo_path(
                repo_root,
                str(gsv_cfg.get("ref_audio_path") or ""),
            )

    tts_preprocessor = character_cfg.get("tts_preprocessor_config")
    if isinstance(tts_preprocessor, dict):
        tts_preprocessor.setdefault("translator_config", {})
        translator_cfg_inner = tts_preprocessor["translator_config"]
        translator_cfg_inner["translate_provider"] = "deeplx"
        translator_cfg_inner.setdefault("deeplx", {})
        translator_cfg_inner["deeplx"]["deeplx_api_endpoint"] = bridge_translate_url

    if project_yaml is not None:
        project = load_project_definition(project_yaml)
        character_cfg["active_project_id"] = project.project_id
        character_cfg["active_project_name"] = project.display_name
        character_cfg["active_project_root"] = project.project_root.as_posix()
        character_cfg["project_prompt_path"] = project.project_prompt_path.as_posix()
        character_cfg["tool_prompt_path"] = project.tool_prompt_path.as_posix()
        if project.response_style_prompt_path is not None:
            character_cfg["response_style_prompt_path"] = (
                project.response_style_prompt_path.as_posix()
            )

    char_provider = str(
        (
            (
                (
                    (character_data.get("character_config") or {}).get("agent_config")
                    or {}
                ).get("agent_settings")
                or {}
            )
            .get("basic_memory_agent", {})
            .get("llm_provider", "")
        )
        or ""
    ).strip()
    provider = (os.environ.get(llm_provider_env) or char_provider or llm_default_provider).strip()

    agent_cfg = character_cfg.setdefault("agent_config", {})
    agent_settings = agent_cfg.setdefault("agent_settings", {})
    basic_agent = agent_settings.setdefault("basic_memory_agent", {})
    basic_agent["llm_provider"] = provider

    if provider == "openai_llm":
        llm_configs = agent_cfg.setdefault("llm_configs", {})
        openai_cfg = llm_configs.setdefault("openai_llm", {})

        model = (
            os.environ.get(openai_model_env)
            or openai_cfg.get("model")
            or openai_default_model
        ).strip()
        openai_cfg["model"] = model

        temp_env = (os.environ.get(openai_temp_env) or "").strip()
        if temp_env:
            try:
                openai_cfg["temperature"] = float(temp_env)
            except ValueError:
                pass

        inject_key = os.environ.get(openai_inject_key_env, "1") != "0"
        api_key = sanitize_ascii(
            os.environ.get(openai_api_key_env)
            or os.environ.get(openai_fallback_key_env)
            or ""
        )
        if inject_key and api_key:
            openai_cfg["llm_api_key"] = api_key

    return merged, character_cfg


def write_runtime_conf(path: Path, data: Dict[str, Any]) -> None:
    write_yaml_file(path, data)


def find_active_conf(open_llm_dir: Path, characters_dir: Path | None = None) -> Path:
    candidates = [open_llm_dir / "conf.yaml", open_llm_dir / "configs" / "conf.yaml"]
    if characters_dir is not None:
        candidates.append(characters_dir / "conf.yaml")

    for path in candidates:
        if path.exists():
            return path

    try:
        hits = list(open_llm_dir.rglob("conf.yaml"))
        if hits:
            return hits[0]
    except Exception:
        pass

    return open_llm_dir / "conf.yaml"


def apply_character_to_active_conf(
    open_llm_dir: Path,
    character_yaml: Path,
    characters_dir: Path | None = None,
) -> Path:
    conf_path = find_active_conf(open_llm_dir, characters_dir)
    conf_path.parent.mkdir(parents=True, exist_ok=True)

    base = read_yaml_file(conf_path) if conf_path.exists() else {}
    character_data = read_yaml_file(character_yaml)

    try:
        if conf_path.exists():
            backup = conf_path.with_suffix(".yaml.bak")
            write_yaml_file(backup, base)
    except Exception:
        pass

    merged = deep_merge(base, character_data)
    write_yaml_file(conf_path, merged)
    return conf_path
