import json
import os
import re
import time
import io
import wave
import threading
from pathlib import Path

import requests
from loguru import logger

from .tts_interface import TTSInterface


# Health is an observation, not a reservation of the shared active model.
# Even a warm request may need to load its voice after another consumer switches.
CENTRAL_READ_TIMEOUT_SECONDS = 180
CENTRAL_FAILURE_COOLDOWN_SECONDS = 5


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


def _response_dump_payload(response: requests.Response) -> dict:
    payload = {
        "ts": time.time(),
        "status": response.status_code,
        "url": getattr(response.request, "url", None),
        "content_type": response.headers.get("Content-Type", ""),
        "content_length": response.headers.get("Content-Length", ""),
        "response_bytes": len(response.content or b""),
    }
    if response.status_code != 200:
        payload["body_preview"] = (response.text or "")[:500]
    return payload


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
        voice_id: str = "",
    ):
        self.api_url = api_url
        self.voice_id = voice_id
        self.text_lang = text_lang
        self.ref_audio_path = ref_audio_path
        self.prompt_lang = prompt_lang
        self.prompt_text = prompt_text
        self.text_split_method = text_split_method
        self.batch_size = batch_size
        self.media_type = media_type
        self.streaming_mode = streaming_mode
        self.speed_factor = _safe_speed_factor(speed_factor)
        self._voice_lock = threading.Lock()
        self._voice_retry_at = 0.0

    def generate_audio(self, text, file_name_no_ext=None):
        file_name = self.generate_cache_file_name(file_name_no_ext, self.media_type)

        cleaned_text = re.sub(r"\[.*?\]", "", text)
        cleaned_text = (cleaned_text or "").strip()
        if self.voice_id:
            with self._voice_lock:
                return self._generate_central_audio(cleaned_text, file_name)

        return self._generate_legacy_audio(text, cleaned_text, file_name)

    def _generate_central_audio(self, cleaned_text, file_name):
        if not cleaned_text:
            return None
        if time.monotonic() < self._voice_retry_at:
            logger.debug('Central voice skipped: failure cooldown; voice={}', self.voice_id)
            return None
        started = time.monotonic()
        phase = 'discovery'
        payload = dict(voice=self.voice_id, text=cleaned_text, language=self.text_lang,
                       speed_factor=self.speed_factor)
        try:
            # Discovery is cheap and never synthesizes speech. Do not queue a
            # backlog against an unavailable shared engine or retry an utterance.
            health = requests.get(self.api_url.rsplit('/tts', 1)[0] + '/health', timeout=(1, 2), allow_redirects=False)
            if health.status_code != 200:
                return self._central_http_failure(health.status_code, phase, started)
            identity = health.json()
            if not isinstance(identity, dict) or identity.get('service') != 'voice-runtime' or identity.get('protocol_version') != 1:
                raise ValueError('Unexpected voice runtime identity')
            voices = identity.get('voices')
            if not isinstance(voices, list) or not any(
                isinstance(item, dict) and item.get('voice_id') == self.voice_id for item in voices
            ):
                raise ValueError('Voice runtime does not provide the selected voice')
            if identity.get('status') == 'busy':
                return self._central_failure('busy', phase, started)
            if identity.get('status') != 'available':
                raise ValueError('Voice runtime unavailable')
            phase = 'synthesis'
            response = requests.post(self.api_url, json=payload,
                                     timeout=(1, CENTRAL_READ_TIMEOUT_SECONDS), allow_redirects=False)
            if response.status_code != 200:
                return self._central_http_failure(response.status_code, phase, started)
            phase = 'audio_validation'
            if response.headers.get('Content-Type', '').split(';')[0] != 'audio/wav':
                raise ValueError('Expected WAV audio')
            if len(response.content) > 32 * 1024 * 1024:
                raise ValueError('Oversized WAV audio')
            with wave.open(io.BytesIO(response.content), 'rb') as audio:
                count = audio.getnframes()
                if count <= 0 or len(audio.readframes(count)) != count * audio.getnchannels() * audio.getsampwidth():
                    raise ValueError('Empty or truncated WAV')
            Path(file_name).write_bytes(response.content)
            self._voice_retry_at = 0.0
            logger.info('Central voice synthesis passed: voice={} elapsed_s={:.3f} bytes={}',
                        self.voice_id, time.monotonic() - started, len(response.content))
            return file_name
        except requests.ConnectTimeout:
            return self._central_failure('offline', phase, started,
                                         cooldown=CENTRAL_FAILURE_COOLDOWN_SECONDS)
        except requests.Timeout:
            # A synthesis timeout is ambiguous: the server may still finish.
            # Never resend this utterance. The next utterance checks health again.
            cooldown = CENTRAL_FAILURE_COOLDOWN_SECONDS if phase == 'discovery' else 0
            return self._central_failure('timeout', phase, started, cooldown=cooldown)
        except requests.ConnectionError:
            return self._central_failure('offline', phase, started,
                                         cooldown=CENTRAL_FAILURE_COOLDOWN_SECONDS)
        except (requests.RequestException, ValueError, wave.Error, EOFError, OSError) as exc:
            return self._central_failure(type(exc).__name__, phase, started,
                                         cooldown=CENTRAL_FAILURE_COOLDOWN_SECONDS)

    def _central_http_failure(self, status, phase, started):
        # A race between discovery and POST is expected on a shared service.
        return self._central_failure('busy' if status == 429 else 'http_error', phase, started,
                                     cooldown=0 if status == 429 else CENTRAL_FAILURE_COOLDOWN_SECONDS,
                                     http_status=status)

    def _central_failure(self, reason, phase, started, *, cooldown=0, http_status=None):
        self._voice_retry_at = time.monotonic() + cooldown if cooldown else 0.0
        # Do not log utterances, response bodies, or private model/reference paths.
        logger.warning('Central voice unavailable: reason={} phase={} voice={} elapsed_s={:.3f} '
                       'http_status={} cooldown_s={}', reason, phase, self.voice_id,
                       time.monotonic() - started, http_status, cooldown)
        return None

    def _generate_legacy_audio(self, text, cleaned_text, file_name):
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
                    _response_dump_payload(response),
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
