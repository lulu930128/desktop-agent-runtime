import re
import requests
from loguru import logger
from .tts_interface import TTSInterface
import os,json,time

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
            # ✅ 讓 fastapi 解析成 bool（GET query 最安全是 true/false 小寫字串）
            "streaming_mode": "true" if str(self.streaming_mode).lower() in ["1","true","yes"] else "false",
        }

        dump_path = r"C:\kuro\launcher_logs\tts_params_dump.jsonl"
        resp_dump = r"C:\kuro\launcher_logs\tts_response_dump.jsonl"
        os.makedirs(os.path.dirname(dump_path), exist_ok=True)

        # 1) 先 dump params（永遠要成功）
        with open(dump_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "data": data, "orig_text": text}, ensure_ascii=False) + "\n")
        logger.warning(f"[DEBUG TTS PARAMS] {data}")

        # 2) 再打 TTS
        try:
            response = requests.get(self.api_url, params=data, timeout=120)
        except requests.RequestException as e:
            logger.critical(f"TTS request failed: {e}")
            return None

        # 3) dump response（包含 body）
        with open(resp_dump, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "status": response.status_code,
                "url": getattr(response.request, "url", None),
                "resp_text": (response.text or "")[:2000],
            }, ensure_ascii=False) + "\n")

        if response.status_code == 200:
            with open(file_name, "wb") as audio_file:
                audio_file.write(response.content)
            return file_name

        logger.critical(f"Error: Failed to generate audio. Status code: {response.status_code}; body: {response.text}")
        return None