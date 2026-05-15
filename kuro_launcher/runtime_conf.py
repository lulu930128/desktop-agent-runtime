import os
from pathlib import Path
from typing import Any, Dict, Tuple

from .utils import deep_merge, read_yaml_file, write_yaml_file, sanitize_ascii


def find_base_conf(open_llm_dir: Path) -> Path:
    candidates = [
        open_llm_dir / "configs" / "conf.yaml",
        open_llm_dir / "conf.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "找不到 base conf（試過：\n  - " + "\n  - ".join(str(x) for x in candidates) + "\n）"
    )


def build_runtime_conf(
    open_llm_dir: Path,
    character_yaml: Path,
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
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    base_conf_path = find_base_conf(open_llm_dir)
    base = read_yaml_file(base_conf_path)
    ch = read_yaml_file(character_yaml)
    merged = deep_merge(base, ch)

    # 強制 LLM 監聽
    merged.setdefault("system_config", {})
    merged["system_config"]["host"] = llm_host
    merged["system_config"]["port"] = llm_port

    # ✅ root 有 translator_config（你原本的結構）
    merged.setdefault("translator_config", {})
    tcfg = merged["translator_config"]
    tcfg["translate_provider"] = "deeplx"
    tcfg.setdefault("deeplx", {})
    tcfg["deeplx"]["deeplx_api_endpoint"] = bridge_translate_url

    # （兼容：有些角色檔可能把 translator_config 放在 character_config.tts_preprocessor_config）
    cc = merged.setdefault("character_config", {})
    tpp = cc.get("tts_preprocessor_config")
    if isinstance(tpp, dict):
        tpp.setdefault("translator_config", {})
        tc2 = tpp["translator_config"]
        tc2["translate_provider"] = "deeplx"
        tc2.setdefault("deeplx", {})
        tc2["deeplx"]["deeplx_api_endpoint"] = bridge_translate_url

    # ✅ 強制「腦」走 OpenAI（預留之後可切回）
    provider = (os.environ.get(llm_provider_env) or llm_default_provider).strip()

    agent_cfg = cc.setdefault("agent_config", {})
    agent_settings = agent_cfg.setdefault("agent_settings", {})
    basic = agent_settings.setdefault("basic_memory_agent", {})
    basic["llm_provider"] = provider

    if provider == "openai_llm":
        llm_configs = agent_cfg.setdefault("llm_configs", {})
        openai_cfg = llm_configs.setdefault("openai_llm", {})

        # model / temperature
        model = (os.environ.get(openai_model_env) or openai_cfg.get("model") or openai_default_model).strip()
        openai_cfg["model"] = model

        temp_env = (os.environ.get(openai_temp_env) or "").strip()
        if temp_env:
            try:
                openai_cfg["temperature"] = float(temp_env)
            except ValueError:
                pass

        # key 注入（預留：可以分開腦/翻譯；沒設就共用 OPENAI_API_KEY）
        inject = (os.environ.get(openai_inject_key_env, "1") != "0")
        key = sanitize_ascii(os.environ.get(openai_api_key_env) or os.environ.get(openai_fallback_key_env) or "")
        if inject and key:
            openai_cfg["llm_api_key"] = key

    return merged, cc


def write_runtime_conf(path: Path, data: Dict[str, Any]) -> None:
    write_yaml_file(path, data)


def find_active_conf(open_llm_dir: Path, characters_dir: Path | None = None) -> Path:
    """找 UI/後端啟動時用來初始化的 conf.yaml（你已驗證改它即可決定開場角色）。"""
    candidates = [open_llm_dir / "conf.yaml", open_llm_dir / "configs" / "conf.yaml"]
    if characters_dir is not None:
        candidates.append(characters_dir / "conf.yaml")

    for p in candidates:
        if p.exists():
            return p

    # 保險：掃描一次（只取第一個）
    try:
        hits = list(open_llm_dir.rglob("conf.yaml"))
        if hits:
            return hits[0]
    except Exception:
        pass

    # 都找不到就建立在 open_llm_dir/conf.yaml
    return open_llm_dir / "conf.yaml"


def apply_character_to_active_conf(
    open_llm_dir: Path,
    character_yaml: Path,
    characters_dir: Path | None = None,
) -> Path:
    """把選中的角色 YAML 深度合併到 active conf.yaml，讓後端啟動開場就用它。"""
    conf_path = find_active_conf(open_llm_dir, characters_dir)
    conf_path.parent.mkdir(parents=True, exist_ok=True)

    base = read_yaml_file(conf_path) if conf_path.exists() else {}
    ch = read_yaml_file(character_yaml)

    # 備份（同一份覆寫即可）
    try:
        if conf_path.exists():
            bak = conf_path.with_suffix(".yaml.bak")
            write_yaml_file(bak, base)
    except Exception:
        pass

    merged = deep_merge(base, ch)
    write_yaml_file(conf_path, merged)
    return conf_path
