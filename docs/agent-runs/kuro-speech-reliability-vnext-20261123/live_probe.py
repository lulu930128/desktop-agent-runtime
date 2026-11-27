"""Exercise the real Conversation/LLM/central voice path with a real Pet subscriber.
The sender uses an isolated primary and no production history. Restore Pet on exit.
"""

import asyncio
import json
import os
from pathlib import Path
import sys
import time

import requests
import websockets

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".tmp" / "speech-vnext-probes" / str(time.time_ns())
sys.path[:0] = [
    str(ROOT),
    str(ROOT / "Open-LLM-VTuber/src"),
    str(ROOT / "Open-LLM-VTuber"),
]
import launcher_qt
from loguru import logger
from kuro_launcher.config import load_config
from open_llm_vtuber.config_manager import Config, read_yaml
from open_llm_vtuber.service_context import ServiceContext
from open_llm_vtuber.conversations.single_conversation import (
    process_single_conversation,
)
from open_llm_vtuber.websocket_handler import PrimaryConversationOutput
from open_llm_vtuber.conversations.speech_presentation import (
    _semantic_flags,
    _asserted_success,
)


async def main(mode):
    OUT.mkdir(parents=True)
    print(f"Evidence directory: {OUT}", flush=True)
    launcher_qt._load_env()
    cfg = load_config(ROOT / "kuro_launcher.settings.yaml")
    config = Config(**read_yaml(str(cfg.runtime_conf_path)))
    os.environ["KURO_LAUNCHER_SETTINGS_FILE"] = str(cfg.config_path)
    os.chdir(ROOT / "Open-LLM-VTuber")
    logger.remove()
    logger.add(
        OUT / (mode + "-events.log"),
        filter=lambda r: r["message"].startswith(("speech_", "Central voice ")),
        format="{message}",
    )
    ctx = ServiceContext()
    ctx.config, ctx.system_config, ctx.character_config = (
        config,
        config.system_config,
        config.character_config,
    )
    ctx.history_uid = None
    ctx.init_live2d(config.character_config.live2d_model_name)
    ctx.init_tts(config.character_config.tts_config)
    if mode == "tool":
        await ctx._init_mcp_components(True, ["omi-search"])
    await ctx.init_agent(
        config.character_config.agent_config, config.character_config.persona_prompt
    )
    subscribers, status, wavs, spoken, display, receipts, tools = (
        {},
        [],
        [],
        [],
        [],
        [],
        [],
    )
    llm_calls = []
    completion = ctx.agent_engine._llm.chat_completion

    async def observe_llm(*args, **kw):
        llm_calls.append(bool(kw.get("tools")))
        async for event in completion(*args, **kw):
            yield event

    ctx.agent_engine._llm.chat_completion = observe_llm
    generate = ctx.tts_engine.async_generate_audio

    async def observe_tts(text, **kw):
        spoken.append(text)
        # Deterministic failure injection. Adjacent segments still use the physical TTS.
        if mode == "fault" and len(spoken) == 2:
            return None
        path = await generate(text=text, **kw)
        if mode == "no-punctuation" and path:
            (OUT / "no-punctuation-last.wav").write_bytes(Path(path).read_bytes())
        return path

    ctx.tts_engine.async_generate_audio = observe_tts

    async def primary(raw):
        e = json.loads(raw)
        if e.get("audio"):
            wavs.append((e.get("segment_id"), e.get("audio_seconds")))
        if e.get("display_append"):
            display.append(e["display_text"]["text"])
        if e["type"] == "speech-status":
            status.append(e)
        if e["type"] == "tool_call_status":
            tools.append({key: e.get(key) for key in ("tool_name", "status", "execution_status", "reason_code")})

    output = PrimaryConversationOutput(primary, lambda: subscribers)
    phases = []
    ready = asyncio.Event()

    class Socket:
        def __init__(self, ws):
            self.ws = ws

        async def send_text(self, value):
            await self.ws.send(value)

    async def pet(ws):
        async for raw in ws:
            e = json.loads(raw)
            if e["type"] == "request-init-config":
                subscribers["pet"] = Socket(ws)
                ready.set()
            if e["type"] == "audio-play-start":
                phases.append([e.get("segment_id"), e.get("phase")])
                output.observe_segment(
                    "pet", e.get("request_id"), e.get("segment_id"), e.get("phase")
                )
                if (
                    mode == "cancel"
                    and e.get("phase") == "playing"
                    and not result.get("stop_requested")
                ):
                    result["stop_requested"] = True
                    stop = await asyncio.to_thread(
                        requests.post,
                        url + "/command",
                        json={"action": "stop-playback"},
                        timeout=6,
                    )
                    result["stop_accepted"] = stop.json()["ok"]
            if e["type"] == "frontend-playback-complete":
                receipts.append(e)
                output.acknowledge(
                    "pet", e.get("request_id"), e.get("status"), e.get("ended_segments")
                )

    url = "http://127.0.0.1:23567"
    before = requests.get(url + "/status", timeout=5).json()["renderer"]
    assert before["aiState"] in ("idle", "interrupted")
    questions = {
        "no-punctuation": "不用工具。請用日文畫面逐字顯示並全文朗讀以下這段文字，保留沒有句號的格式：朝早く目を覚ました私は窓を開けて冷たい空気を吸い込みましたそれから静かな道を歩いて駅前の小さな店に立ち寄り温かいお茶を飲みながら今日の予定をゆっくり考えました昼には懐かしい友人と会って近くの公園を散歩し夕方には橋を渡って坂道を上り最後に家の明かりが見えました",
        "mixed": "不用工具。請說明測試沒有成功，操作尚未驗證，明天再檢查。請在畫面中段附上樣本網址 https://example.test/voice 以及程式碼片段 `retry = false`，並在結尾說明現在不能執行。日文口述正常內容即可。",
        "fault": "不用工具。請只以日文顯示下面三句並全文朗讀：朝は静かでした。昼は風が吹きました。夜は家に戻りました。",
        "cancel": "不用工具。用日文寫三句關於散步的自然描述並全文朗讀。",
        "zh-detail": "不用工具。畫面只以繁體中文逐字顯示這段虛構測試文字：這次測試的價格是100.5，停損是95。操作失敗，來源尚未驗證。明天再檢查。請用日文全文朗讀。",
        "short": "不用工具，告訴我今天適合如何放鬆，簡短說一句就好。",
        "long": "不用工具。請寫一篇日文自然散文，描寫清晨走到海邊、午間在小店休息、黃昏返家的過程，約五百個日文字，四段連貫 prose，最後一句用「家の明かりが見えました。」結尾。以日文顯示，全文朗讀所有內容。",
        "tool": "請先透過 kuro_discover 找 omi_read_data_freshness，再依工具 schema 實際呼叫它查台股資料新鮮度。只讀，不刷新，不下單。若工具回傳失敗或不可用，請清楚說明操作失敗與來源尚未驗證。",
    }
    result = {"mode": mode, "request_id": output.request_id, "formal_qt": False}
    try:
        async with websockets.serve(pet, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            try:
                reply = await asyncio.to_thread(
                    requests.post,
                    url + "/backend-config",
                    json=dict(
                        baseUrl=f"http://127.0.0.1:{port}",
                        wsUrl=f"ws://127.0.0.1:{port}/client-ws",
                        reload=True,
                    ),
                    timeout=6,
                )
                assert reply.json()["ok"]
                await asyncio.wait_for(ready.wait(), 20)
                st = time.monotonic()
                response = await process_single_conversation(
                    ctx,
                    output,
                    "isolated",
                    questions[mode],
                    metadata={"skip_history": True},
                )
                result.update(
                    elapsed_s=round(time.monotonic() - st, 2),
                    display_matches=response == "".join(display),
                    display_chars=len(response),
                    spoken_chars=sum(map(len, spoken)),
                    wav_segments=wavs,
                    status=status,
                    tool_events=tools,
                    segment_phases=phases,
                    llm_calls=len(llm_calls),
                    pet_receipts=receipts,
                    final_sentence_in_display="家の明かりが見えました" in response,
                    final_sentence_in_speech=any(
                        "家の明かりが見えました" in s for s in spoken
                    ),
                )
                if mode == "tool":
                    result["semantic_observations"] = dict(
                        display_flags=sorted(_semantic_flags(response)),
                        spoken_flags=sorted(_semantic_flags(" ".join(spoken))),
                        display_claimed_success=_asserted_success(response),
                        speech_claimed_success=_asserted_success(" ".join(spoken)),
                    )
                if mode != "tool":
                    (OUT / (mode + "-synthetic-content.json")).write_text(
                        json.dumps(
                            dict(display=response, spoken=spoken), ensure_ascii=False
                        ),
                        encoding="utf8",
                    )
            finally:
                reply = await asyncio.to_thread(
                    requests.post,
                    url + "/backend-config",
                    json=dict(
                        baseUrl=before["baseUrl"], wsUrl=before["wsUrl"], reload=True
                    ),
                    timeout=8,
                )
                result["restore_accepted"] = reply.json()["ok"]
    finally:
        (OUT / (mode + "-receipt.json")).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
        )
        print(json.dumps(result, ensure_ascii=True), flush=True)
        await ctx.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=[
            "short",
            "long",
            "mixed",
            "no-punctuation",
            "zh-detail",
            "tool",
            "fault",
            "cancel",
        ],
    )
    asyncio.run(main(parser.parse_args().mode))
