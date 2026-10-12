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
_WINDOWS_VAR_PATTERN = re.compile(r"%[^%]+%")
_CORE_STUDY_MAX_TTL_SECONDS = 30 * 24 * 60 * 60
_CORE_STUDY_DEFAULT_MAX_BYTES = 2 * 1024 * 1024
_CORE_STUDY_MAX_BYTES = 16 * 1024 * 1024
_CORE_MAIL_MAX_TTL_SECONDS = 30 * 24 * 60 * 60
_CORE_MAIL_DEFAULT_MAX_BYTES = 64 * 1024
_CORE_MAIL_MAX_BYTES = 64 * 1024


def _expand_vars(value: str, mapping: Dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        return mapping.get(key, match.group(0))

    return _VAR_PATTERN.sub(repl, value)


def _resolve_path(value: str, mapping: Dict[str, str]) -> Path:
    expanded = _expand_vars(value, mapping)
    expanded = os.path.expandvars(expanded)
    return Path(expanded)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _load_core_study_config(
    core_cfg: Dict[str, Any],
    mapping: Dict[str, str],
    root: Path,
) -> tuple[bool, Optional[Path], int, int]:
    integrations = core_cfg.get("integrations") or {}
    if not isinstance(integrations, dict):
        raise ValueError("core.integrations must be a mapping")
    study_cfg = integrations.get("study") or {}
    if not isinstance(study_cfg, dict):
        raise ValueError("core.integrations.study must be a mapping")

    enabled = _coerce_bool(study_cfg.get("enabled"), False)
    ttl_seconds = study_cfg.get("ttl_seconds", 3600)
    max_bytes = study_cfg.get("max_bytes", _CORE_STUDY_DEFAULT_MAX_BYTES)
    for field_name, value, maximum in (
        ("ttl_seconds", ttl_seconds, _CORE_STUDY_MAX_TTL_SECONDS),
        ("max_bytes", max_bytes, _CORE_STUDY_MAX_BYTES),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValueError(
                f"core.integrations.study.{field_name} must be an integer between 1 and {maximum}"
            )

    raw_path = study_cfg.get("snapshot_path")
    if raw_path is not None and not isinstance(raw_path, str):
        raise ValueError("core.integrations.study.snapshot_path must be a string")
    path_text = (raw_path or "").strip()
    if enabled and not path_text:
        raise ValueError("Enabled Study requires an explicit snapshot_path")

    snapshot_path: Optional[Path] = None
    if path_text:
        expanded = os.path.expandvars(_expand_vars(path_text, mapping))
        if _VAR_PATTERN.search(expanded) or _WINDOWS_VAR_PATTERN.search(expanded):
            raise ValueError("core.integrations.study.snapshot_path contains unresolved variables")
        snapshot_path = Path(expanded)
        if not snapshot_path.is_absolute():
            snapshot_path = root / snapshot_path
        snapshot_path = snapshot_path.resolve()

    return enabled, snapshot_path, ttl_seconds, max_bytes


def _load_core_mail_config(
    core_cfg: Dict[str, Any],
    mapping: Dict[str, str],
    root: Path,
) -> tuple[bool, Optional[Path], int, int, Optional[Path], int]:
    integrations = core_cfg.get("integrations") or {}
    if not isinstance(integrations, dict):
        raise ValueError("core.integrations must be a mapping")
    mail_cfg = integrations.get("mail") or {}
    if not isinstance(mail_cfg, dict):
        raise ValueError("core.integrations.mail must be a mapping")

    enabled = _coerce_bool(mail_cfg.get("enabled"), False)
    ttl_seconds = mail_cfg.get("ttl_seconds", 1800)
    max_bytes = mail_cfg.get("max_bytes", _CORE_MAIL_DEFAULT_MAX_BYTES)
    work_max_bytes = mail_cfg.get("work_max_bytes", 2097152)
    for field_name, value, maximum in (
        ("ttl_seconds", ttl_seconds, _CORE_MAIL_MAX_TTL_SECONDS),
        ("max_bytes", max_bytes, _CORE_MAIL_MAX_BYTES),
        ("work_max_bytes", work_max_bytes, 2097152),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValueError(
                f"core.integrations.mail.{field_name} must be an integer between 1 and {maximum}"
            )

    raw_path = mail_cfg.get("status_path")
    if raw_path is not None and not isinstance(raw_path, str):
        raise ValueError("core.integrations.mail.status_path must be a string")
    path_text = (raw_path or "").strip()
    if enabled and not path_text:
        raise ValueError("Enabled Mail requires an explicit status_path")

    status_path: Optional[Path] = None
    if path_text:
        expanded = os.path.expandvars(_expand_vars(path_text, mapping))
        if _VAR_PATTERN.search(expanded) or _WINDOWS_VAR_PATTERN.search(expanded):
            raise ValueError("core.integrations.mail.status_path contains unresolved variables")
        status_path = Path(expanded)
        if not status_path.is_absolute():
            status_path = root / status_path
        status_path = status_path.resolve()

    raw_work = mail_cfg.get("work_path")
    if raw_work is not None and not isinstance(raw_work, str):
        raise ValueError("core.integrations.mail.work_path must be a string")
    work_text = (raw_work or "").strip()
    if enabled and not work_text:
        raise ValueError("Enabled Mail requires an explicit work_path")
    work_path = None
    if work_text:
        expanded = os.path.expandvars(_expand_vars(work_text, mapping))
        if "\x00" in expanded or _VAR_PATTERN.search(expanded) or _WINDOWS_VAR_PATTERN.search(expanded):
            raise ValueError("core.integrations.mail.work_path contains unresolved variables")
        work_path = Path(expanded)
        if not work_path.is_absolute():
            work_path = root / work_path
        work_path = work_path.resolve()
        if work_path == status_path:
            raise ValueError("Mail work_path must differ from status_path")
    return enabled, status_path, ttl_seconds, max_bytes, work_path, work_max_bytes


def _coerce_string_tuple(value: Any, fallback: tuple[str, ...]) -> tuple[str, ...]:
    items = value if isinstance(value, (list, tuple)) else []
    normalized: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return tuple(normalized) or fallback


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
    startup_character: str
    startup_project: str
    startup_outfit: str
    startup_auto_start: bool

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
    openai_models: tuple[str, ...]
    openai_temp_env: str
    openai_inject_key_env: str
    openai_api_key_env: str
    openai_fallback_key_env: str

    bridge_translate_path: str
    bridge_debug_path: str

    tts_mode: str = "legacy"
    voice_ids: tuple[tuple[str, str], ...] = ()
    core_enabled: bool = False
    core_port: int = 0
    core_db_path: Optional[Path] = None
    core_timezone: str = "UTC"
    core_study_enabled: bool = False
    core_study_snapshot_path: Optional[Path] = None
    core_study_ttl_seconds: int = 3600
    core_study_max_bytes: int = _CORE_STUDY_DEFAULT_MAX_BYTES
    core_mail_enabled: bool = False
    core_mail_status_path: Optional[Path] = None
    core_mail_work_path: Optional[Path] = None
    core_mail_work_max_bytes: int = 2097152
    core_mail_ttl_seconds: int = 1800
    core_mail_max_bytes: int = _CORE_MAIL_DEFAULT_MAX_BYTES

    @property
    def voice_url(self) -> str:
        return f"http://{self.tts_host}:{self.tts_port}"

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
    tts_mode = str(tts_net.get("mode", "legacy"))
    if tts_mode not in {"legacy", "central"}:
        raise ValueError("network.tts.mode must be legacy or central")
    if tts_mode == "central" and tts_net.get("host", "127.0.0.1") != "127.0.0.1":
        raise ValueError("Central voice runtime must use loopback")
    llm_net = net.get("llm") or {}
    pet_control_net = net.get("pet_control") or {}
    core_cfg = cfg.get("core") or {}
    if not isinstance(core_cfg, dict):
        raise ValueError("core must be a mapping")
    (
        core_study_enabled,
        core_study_snapshot_path,
        core_study_ttl_seconds,
        core_study_max_bytes,
    ) = _load_core_study_config(core_cfg, mapping, root)
    (
        core_mail_enabled,
        core_mail_status_path,
        core_mail_ttl_seconds,
        core_mail_max_bytes,
        core_mail_work_path,
        core_mail_work_max_bytes,
    ) = _load_core_mail_config(core_cfg, mapping, root)
    core_enabled = _coerce_bool(core_cfg.get("enabled"), False)
    core_port = int(core_cfg.get("port", 0))
    if core_enabled and not 1 <= core_port <= 65535:
        raise ValueError("core.port must be configured before enabling Core")
    if core_port and core_port in {int(x.get("port", 0)) for x in (bridge_net, tts_net, llm_net, pet_control_net)}:
        raise ValueError("core.port conflicts with another configured service")

    llm = cfg.get("llm") or {}
    openai = llm.get("openai") or {}
    bridge_cfg = cfg.get("bridge") or {}
    startup_profile = cfg.get("startup_profile") or {}
    if not isinstance(startup_profile, dict):
        startup_profile = {}

    return AppConfig(
        config_path=config_path.resolve(),
        core_enabled=core_enabled,
        core_timezone=str(core_cfg.get("timezone", "UTC")),
        core_port=core_port,
        core_db_path=_resolve_path(str(core_cfg.get("db_path") or "${ROOT}/local_state/core/work.sqlite3"), mapping).resolve(),
        core_study_enabled=core_study_enabled,
        core_study_snapshot_path=core_study_snapshot_path,
        core_study_ttl_seconds=core_study_ttl_seconds,
        core_study_max_bytes=core_study_max_bytes,
        core_mail_enabled=core_mail_enabled,
        core_mail_status_path=core_mail_status_path,
        core_mail_work_path=core_mail_work_path,
        core_mail_work_max_bytes=core_mail_work_max_bytes,
        core_mail_ttl_seconds=core_mail_ttl_seconds,
        core_mail_max_bytes=core_mail_max_bytes,
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
        startup_character=str(startup_profile.get("character") or "").strip(),
        startup_project=str(startup_profile.get("project") or "").strip(),
        startup_outfit=str(startup_profile.get("outfit") or "").strip(),
        startup_auto_start=_coerce_bool(startup_profile.get("auto_start"), False),
        bridge_host=str(bridge_net.get("host", "127.0.0.1")),
        bridge_port=int(bridge_net.get("port", 1188)),
        tts_host=str(tts_net.get("host", "127.0.0.1")),
        tts_port=int(tts_net.get("port", 9981)),
        tts_mode=tts_mode,
        voice_ids=tuple((str(k), str(v)) for k, v in (tts_net.get("voices") or {}).items()),
        llm_host=str(llm_net.get("host", "127.0.0.1")),
        llm_port=int(llm_net.get("port", 23456)),
        pet_control_host=str(pet_control_net.get("host", "127.0.0.1")),
        pet_control_port=int(pet_control_net.get("port", 23567)),
        llm_provider_env=str(llm.get("provider_env", "KURO_LLM_PROVIDER")),
        llm_default_provider=str(llm.get("default_provider", "openai_llm")),
        openai_model_env=str(openai.get("model_env", "OPENAI_LLM_MODEL")),
        openai_default_model=str(openai.get("default_model", "gpt-5-mini")),
        openai_models=_coerce_string_tuple(
            openai.get("models"),
            (str(openai.get("default_model", "gpt-5-mini")),),
        ),
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
