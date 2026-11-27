"""Measure an unpunctuated Japanese reading on the configured central voice and local ASR.

Runs real synthesis sequentially; it does not use a WS subscriber or change Pet configuration.
"""

from pathlib import Path
import json
import os
import sys
import time
import wave

import requests
import numpy as np
from scipy.signal import resample_poly
from io import BytesIO

root = Path(__file__).resolve().parents[3]
d = root / ".tmp" / "speech-vnext-probes" / str(time.time_ns())
sys.path[:0] = [
    str(root),
    str(root / "Open-LLM-VTuber/src"),
    str(root / "Open-LLM-VTuber"),
]
from kuro_launcher.config import load_config
from open_llm_vtuber.config_manager import Config, read_yaml
from open_llm_vtuber.service_context import ServiceContext
from open_llm_vtuber.conversations.conversation_utils import _natural_speech_chunks
from open_llm_vtuber.tts.gpt_sovits_tts import CENTRAL_READ_TIMEOUT_SECONDS
from loguru import logger


def main():
    d.mkdir(parents=True)
    print(f"Evidence directory: {d}", flush=True)
    logger.remove()
    os.chdir(root / "Open-LLM-VTuber")
    ctx = ServiceContext()
    profile = load_config(root / "kuro_launcher.settings.yaml")
    ctx.config = Config(**read_yaml(str(profile.runtime_conf_path)))
    ctx.character_config = ctx.config.character_config
    ctx.init_asr(ctx.character_config.asr_config)
    ctx.init_tts(ctx.character_config.tts_config)
    voice = ctx.tts_engine
    if not voice.voice_id:
        raise ValueError("The selected profile has no central voice identity")
    narrative = "朝の公園は静かで木々の間から風が吹いていました私は駅へ向かう途中で少し足を止めて昨日の話を思い出しました小さな橋を渡り坂道をゆっくり上ると遠くの丘に白い建物が見えました"
    tail = "最後に黄色い傘を見つけました"
    source = (narrative * 30)[: 2000 - len(tail)] + tail + "これで記録は終わりです"
    parts = _natural_speech_chunks(
        source,
        wire_fields=dict(
            voice=voice.voice_id,
            language=voice.text_lang,
            speed_factor=voice.speed_factor,
        ),
    )
    assert "".join(parts) == source
    result = dict(
        chars=len(source), part_chars=list(map(len, parts)), results=[], formal_qt=False
    )
    for idx, part in enumerate(parts):
        st = time.monotonic()
        try:
            r = requests.post(
                voice.api_url,
                json=dict(
                    voice=voice.voice_id,
                    language=voice.text_lang,
                    speed_factor=voice.speed_factor,
                    text=part,
                ),
                timeout=(2, CENTRAL_READ_TIMEOUT_SECONDS),
            )
            item = dict(
                index=idx + 1,
                http=r.status_code,
                elapsed_s=round(time.monotonic() - st, 2),
            )
            if r.status_code != 200:
                item["code"] = r.json().get("error", {}).get("code")
            if r.status_code == 200:
                with wave.open(BytesIO(r.content), "rb") as f:
                    rate = f.getframerate()
                    audio = (
                        np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(
                            "float32"
                        )
                        / 32768
                    )
                clip = resample_poly(audio[-rate * 9 :], 16000, rate).astype("float32")
                item.update(
                    audio_s=round(len(audio) / rate, 2),
                    asr_tail=ctx.asr_engine.transcribe_np(clip),
                )
            result["results"].append(item)
        except Exception as exc:
            result["results"].append(dict(index=idx + 1, error=type(exc).__name__))
        (d / "capacity.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), "utf8"
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
