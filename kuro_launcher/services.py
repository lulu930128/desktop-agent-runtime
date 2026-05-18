import os
import sys
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
import subprocess
import textwrap
import urllib.error
import urllib.parse
import urllib.request

from .config import AppConfig
from .procs import ManagedProc, spawn_process
from .utils import port_is_open, log_ts, sanitize_ascii, read_yaml_file


def _probe_llm_import(python_llm: str, open_llm_dir: Path, env: dict, logger_cb):
    code = textwrap.dedent(r"""
    import os, sys
    print("PY_EXE=", sys.executable)
    print("CWD=", os.getcwd())
    try:
        import src.open_llm_vtuber.tts.gpt_sovits_tts as m
        print("GPT_SOVITS_TTS_FILE=", getattr(m, "__file__", "<no __file__>"))
    except Exception as e:
        print("IMPORT_ERR=", repr(e))
    """).strip()

    r = subprocess.run(
        [python_llm, "-c", code],
        cwd=str(open_llm_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    out = (r.stdout or "") + (r.stderr or "")
    logger_cb(f"[{log_ts()}] [LLM-PY-PROBE]\n{out}")



def start_bridge(cfg: AppConfig, logger_cb, *, logs_root: Path, run_id: str | None = None) -> Optional[ManagedProc]:
    # 若已在跑：沿用現有（不報錯）
    if port_is_open(cfg.bridge_host, cfg.bridge_port):
        logger_cb(f"[{log_ts()}] Bridge 已在跑：{cfg.bridge_host}:{cfg.bridge_port}（沿用現有）")
        return None

    cmd = [
        sys.executable, "-m", "uvicorn", "deeplx_bridge:app",
        "--host", cfg.bridge_host, "--port", str(cfg.bridge_port),
        "--no-use-colors",
    ]

    env: Dict[str, str] = os.environ.copy()
    env_key = sanitize_ascii(env.get("OPENAI_API_KEY", ""))
    if env_key:
        env["OPENAI_API_KEY"] = env_key

    logger_cb(f"[{log_ts()}] 啟動 Bridge：{' '.join(cmd)}")
    proc = spawn_process("bridge", cmd, cfg.bridge_dir, logs_root, env=env, run_id=run_id, aggregate_daily=True)
    logger_cb(f"[{log_ts()}] Bridge logs：{proc.combined_path}")
    return proc


def _env_python(env_path: Path) -> str:
    p1 = env_path / "python.exe"
    if p1.exists():
        return str(p1)
    p2 = env_path / "Scripts" / "python.exe"
    if p2.exists():
        return str(p2)
    raise FileNotFoundError(f"找不到 env python.exe：{env_path}")


def _pick_tts_infer(cfg: AppConfig, character_name: str) -> Optional[str]:
    try:
        infer_dir = cfg.tts_infer_dir
    except Exception:
        return None

    safe = sanitize_ascii(character_name).strip()
    if not safe:
        safe = character_name.strip() or "default"

    cand_name = cfg.tts_infer_template.format(character=safe)
    cand = infer_dir / cand_name
    if cand.exists():
        return str(cand)

    fallback = infer_dir / cfg.tts_infer_default
    if fallback.exists():
        return str(fallback)

    return None


def _prepare_tts_runtime_infer(
    cfg: AppConfig,
    *,
    character_name: str,
    logs_root: Path,
    run_id: str,
) -> tuple[Optional[str], Optional[str]]:
    source = _pick_tts_infer(cfg, character_name)
    if not source:
        return None, None

    source_path = Path(source)
    runtime_dir = Path(logs_root) / "tts_runtime" / sanitize_ascii(run_id)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_path = runtime_dir / source_path.name
    shutil.copy2(source_path, runtime_path)
    return str(runtime_path), str(source_path)


def _resolve_maybe_abs(path_value: str, base_dir: Path) -> Path:
    p = Path(str(path_value or "").strip())
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()


def _character_tts_cfg(char_cfg: Dict[str, Any]) -> Dict[str, Any]:
    tts_cfg = (char_cfg.get("tts_config") or {}) if isinstance(char_cfg, dict) else {}
    gsv = tts_cfg.get("gpt_sovits_tts") or tts_cfg.get("gpt_sovits") or {}
    return gsv if isinstance(gsv, dict) else {}


def validate_profile_assets(cfg: AppConfig, character_yaml: Path) -> Tuple[list[str], list[str]]:
    """Return (blocking_errors, warnings) for the selected launcher profile."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        data = read_yaml_file(character_yaml)
    except Exception as e:
        return [f"無法讀取角色 YAML：{character_yaml} ({e})"], warnings

    char_cfg = data.get("character_config") or {}
    if not isinstance(char_cfg, dict):
        return [f"角色 YAML 缺少 character_config：{character_yaml}"], warnings

    conf_uid = str(char_cfg.get("conf_uid") or "").strip()
    if not conf_uid:
        errors.append("角色缺少 conf_uid，無法穩定分離記憶/chat_history。")

    live2d_name = str(char_cfg.get("live2d_model_name") or "").strip()
    model_dict_path = cfg.open_llm_dir / "model_dict.json"
    if not live2d_name:
        errors.append("角色缺少 live2d_model_name。")
    elif model_dict_path.exists():
        try:
            models = json.loads(model_dict_path.read_text(encoding="utf-8"))
            match = next((m for m in models if str(m.get("name")) == live2d_name), None)
            if match is None:
                errors.append(f"model_dict.json 找不到 Live2D：{live2d_name}")
            else:
                model_url = str(match.get("url") or "").lstrip("/")
                if model_url:
                    model_path = cfg.open_llm_dir / model_url
                    if not model_path.exists():
                        errors.append(f"Live2D 檔案不存在：{model_path}")
        except Exception as e:
            warnings.append(f"無法檢查 model_dict.json：{e}")
    else:
        warnings.append(f"找不到 model_dict.json：{model_dict_path}")

    tts_cfg = char_cfg.get("tts_config") or {}
    tts_model = str(tts_cfg.get("tts_model") or "").strip()
    if tts_model != "gpt_sovits_tts":
        errors.append(f"目前 launcher profile 只支援 gpt_sovits_tts，角色設定為：{tts_model or '(missing)'}")
    else:
        gsv = _character_tts_cfg(char_cfg)
        ref_audio = str(gsv.get("ref_audio_path") or "").strip()
        if not ref_audio:
            errors.append("GPT-SoVITS 缺少 ref_audio_path。")
        else:
            ref_path = _resolve_maybe_abs(ref_audio, cfg.root)
            if not ref_path.exists():
                errors.append(f"參考音檔不存在：{ref_path}")
            elif ref_path.stat().st_size <= 0:
                errors.append(f"參考音檔是空檔：{ref_path}")

    infer_file = Path(_pick_tts_infer(cfg, character_yaml.stem) or "")
    expected_infer = cfg.tts_infer_dir / cfg.tts_infer_template.format(character=sanitize_ascii(character_yaml.stem))
    if not expected_infer.exists():
        errors.append(f"缺少角色專用 TTS infer config：{expected_infer}")
    elif infer_file.exists():
        try:
            infer_data = read_yaml_file(infer_file)
            custom = infer_data.get("custom") or {}
            if not isinstance(custom, dict):
                errors.append(f"TTS infer config 缺少 custom 區塊：{infer_file}")
            else:
                for label, key in [("GPT", "t2s_weights_path"), ("SoVITS", "vits_weights_path")]:
                    value = str(custom.get(key) or "").strip()
                    if not value:
                        errors.append(f"{label} 權重路徑未設定：{infer_file}")
                        continue
                    weight_path = _resolve_maybe_abs(value, cfg.tts_dir)
                    if not weight_path.exists():
                        errors.append(f"{label} 權重不存在：{weight_path}")
                    elif weight_path.stat().st_size <= 0:
                        errors.append(f"{label} 權重是空檔：{weight_path}")
        except Exception as e:
            errors.append(f"無法讀取 TTS infer config：{infer_file} ({e})")

    return errors, warnings


def probe_tts(
    cfg: AppConfig,
    char_cfg: Dict[str, Any],
    *,
    logs_root: Path,
    run_id: str,
    request_timeout_s: float = 120.0,
) -> Tuple[bool, str]:
    """Make a tiny real GPT-SoVITS request so the launcher does not trust port-open only."""
    gsv = _character_tts_cfg(char_cfg)
    if not gsv:
        return False, "找不到 character_config.tts_config.gpt_sovits_tts"

    text_lang = str(gsv.get("text_lang") or "ja").strip().lower()
    sample_text = {
        "ja": "こんにちは。",
        "zh": "你好。",
        "en": "Hello.",
    }.get(text_lang, "こんにちは。")

    api_url = str(gsv.get("api_url") or f"http://{cfg.tts_host}:{cfg.tts_port}/tts").strip()
    payload = {
        "text": sample_text,
        "text_lang": text_lang,
        "ref_audio_path": str(gsv.get("ref_audio_path") or "").strip(),
        "prompt_lang": str(gsv.get("prompt_lang") or text_lang).strip().lower(),
        "prompt_text": str(gsv.get("prompt_text") or ""),
        "text_split_method": str(gsv.get("text_split_method") or "cut5"),
        "batch_size": str(gsv.get("batch_size") or "1"),
        "media_type": str(gsv.get("media_type") or "wav"),
        "streaming_mode": "false",
    }

    url = api_url + ("&" if "?" in api_url else "?") + urllib.parse.urlencode(payload)
    smoke_dir = Path(logs_root) / "tts_smoke" / (run_id or "manual")
    smoke_dir.mkdir(parents=True, exist_ok=True)
    out_path = smoke_dir / f"smoke.{payload['media_type']}"

    try:
        with urllib.request.urlopen(url, timeout=request_timeout_s) as resp:
            body = resp.read()
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body[:500]}"
    except Exception as e:
        return False, f"request failed: {e}"

    if status != 200:
        text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)
        return False, f"HTTP {status}: {text[:500]}"
    if len(body) <= 44:
        return False, f"回傳音訊太小：{len(body)} bytes, content-type={content_type}"

    out_path.write_bytes(body)
    return True, f"OK，已產生 smoke audio：{out_path}"


def start_tts(
    cfg: AppConfig,
    logger_cb,
    *,
    character_name: str = "",
    logs_root: Path,
    run_id: str,
) -> ManagedProc:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    python_tts = _env_python(cfg.env_tts)

    infer_file, infer_source = _prepare_tts_runtime_infer(
        cfg,
        character_name=character_name or "default",
        logs_root=logs_root,
        run_id=run_id,
    )
    cmd = [
        python_tts,
        ".\\api_v2.py",
        "-a", cfg.tts_host,
        "-p", str(cfg.tts_port),
    ]
    if infer_file:
        cmd += ["-c", infer_file]

    logger_cb(f"[{log_ts()}] 啟動 TTS：{' '.join(cmd)}")
    if infer_file:
        logger_cb(f"[{log_ts()}] TTS infer source：{infer_source}")
        logger_cb(f"[{log_ts()}] TTS infer runtime：{infer_file}")

    proc = proc = spawn_process("tts", cmd, cfg.tts_dir, logs_root, env=env, run_id=run_id, aggregate_daily=False)
    logger_cb(f"[{log_ts()}] TTS logs：{proc.combined_path}")
    return proc


def start_llm(cfg: AppConfig, logger_cb, *, logs_root: Path, run_id: str) -> ManagedProc:
    python_llm = _env_python(cfg.env_llm)
    cmd = [python_llm, ".\\run_server.py"]

    env = os.environ.copy()
    env["OPEN_LLM_VTUBER_CONFIG"] = str(cfg.runtime_conf_path)
    env["KURO_LAUNCHER_LOGS_DIR"] = str(Path(logs_root).resolve())
    env["KURO_MEMORY_ROOT"] = str((Path(cfg.open_llm_dir) / "memories").resolve())

    _probe_llm_import(python_llm, Path(cfg.open_llm_dir), env, logger_cb)

    # 讓 launcher 起的 python 優先 import repo 版本（避免吃到 site-packages 舊版）
    repo_src = str(Path(cfg.open_llm_dir) / "src")
    env["PYTHONPATH"] = repo_src + os.pathsep + env.get("PYTHONPATH", "")

    # （可選，但強烈建議）避免子程序輸出日文炸 cp950
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    logger_cb(f"[{log_ts()}] 啟動 LLM：{' '.join(cmd)}")
    proc = spawn_process("llm", cmd, cfg.open_llm_dir, logs_root, env=env, run_id=run_id, aggregate_daily=False)
    logger_cb(f"[{log_ts()}] LLM logs：{proc.combined_path}")
    return proc
