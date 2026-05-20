import json
import os
import re
import time
from pathlib import Path

import requests
from loguru import logger

from .tts_interface import TTSInterface


def _debug_dump_paths() -> tuple[Path, Path]:
    logs_root = (os.getenv("KURO_LAUNCHER_LOGS_DIR", "") or "").strip()
    if logs_root:
        base_dir = Path(logs_root)
    else:
        base_dir = (Path.cwd().parent / "launcher_logs").resolve()

    base_dir.mkdir(parents=True, exist_ok=True)
    return (
        base_dir / "tts_params_dump.jsonl",
        base_dir / "tts_response_dump.jsonl",
    )


def _safe_speed_factor(value, default: float = 1.0) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return default
    # Match GPT-SoVITS UI range. Values outside this range often sound unstable.
    return max(0.6, min(1.65, speed))


class TTSEngine(TTSInterface):
    def __init__(
        self,
        api_url: str = "http://127.0.0.1:9880/tts",
        text_lang: str = "zh",
        ref_audio_path: str = "",
        prompt_lang: str = "zh",
        prompt_text: str = "",
        text_split_method: str = "cut5",
        batch_size: str = "1",
        media_type: str = "wav",
        streaming_mode: str = "false",
        speed_factor: float = 1.0,
    ):
        self.api_url = api_url
        self.text_lang = text_lang
        self.ref_audio_path = ref_audio_path
        self.prompt_lang = prompt_lang
        self.prompt_text = prompt_text
        self.text_split_method = text_split_method
        self.batch_size = batch_size
        self.media_type = media_type
        self.streaming_mode = streaming_mode
        self.speed_factor = _safe_speed_factor(speed_factor)

    def generate_audio(self, text, file_name_no_ext=None):
        file_name = self.generate_cache_file_name(file_name_no_ext, self.media_type)

        cleaned_text = re.sub(r"\[.*?\]", "", text)
        cleaned_text = (cleaned_text or "").strip()

        data = {
            "text": cleaned_text,
            "text_lang": (self.text_lang or "").strip(),
            "ref_audio_path": (self.ref_audio_path or "").strip(),
            "prompt_lang": (self.prompt_lang or "").strip(),
            "prompt_text": (self.prompt_text or ""),
            "text_split_method": self.text_split_method,
            "batch_size": int(self.batch_size) if str(self.batch_size).isdigit() else 1,
            "media_type": self.media_type,
            "streaming_mode": (
                "true"
                if str(self.streaming_mode).lower() in ["1", "true", "yes"]
                else "false"
            ),
            "speed_factor": self.speed_factor,
        }

        dump_path, response_dump_path = _debug_dump_paths()

        with dump_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"ts": time.time(), "data": data, "orig_text": text},
                    ensure_ascii=False,
                )
                + "\n"
            )
        logger.warning(f"[DEBUG TTS PARAMS] {data}")

        try:
            response = requests.get(self.api_url, params=data, timeout=120)
        except requests.RequestException as exc:
            logger.critical(f"TTS request failed: {exc}")
            return None

        with response_dump_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "status": response.status_code,
                        "url": getattr(response.request, "url", None),
                        "resp_text": (response.text or "")[:2000],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        if response.status_code == 200:
            with open(file_name, "wb") as audio_file:
                audio_file.write(response.content)
            return file_name

        logger.critical(
            "Error: Failed to generate audio. Status code: "
            f"{response.status_code}; body: {response.text}"
        )
        return None
