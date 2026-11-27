"""Offscreen Qt transport, production conversation trigger and local generation.
The harness supplies the session handshake and a synthetic ServiceContext.
"""

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import time
from unittest.mock import AsyncMock, patch
from quality_replay import MODEL, ROOT, request

sys.path[:0] = [
    str(ROOT),
    str(ROOT / "Open-LLM-VTuber"),
    str(ROOT / "Open-LLM-VTuber/src"),
]
from PySide6.QtCore import QCoreApplication
from websockets.legacy.server import serve
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
from open_llm_vtuber.chat_history_manager import create_new_history, get_history
from open_llm_vtuber.character_memory_manager import list_character_memories
from open_llm_vtuber.websocket_handler import WebSocketHandler


class LocalModel:
    def __init__(self, url):
        self.url = url
        self.calls = []

    async def chat_completion(self, messages, system=None, tools=None):
        items = [{"role": "system", "content": system}]
        for m in messages:
            content = m["content"]
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content)
            items.append({"role": m["role"], "content": content})
        response = await asyncio.to_thread(
            request,
            self.url + "/api/chat",
            dict(
                model=os.getenv("KURO_REPLAY_MODEL", MODEL),
                stream=False,
                think=False,
                messages=items,
                options={
                    "seed": 17,
                    "temperature": 0,
                    "num_gpu": 0,
                    "num_thread": 4,
                    "num_predict": 64,
                },
            ),
        )
        self.calls.append(
            {
                "prompt_tokens": response["prompt_eval_count"],
                "output_tokens": response["eval_count"],
                "has_fact": "無糖抹茶" in system,
            }
        )
        yield response["message"]["content"]


async def run(endpoint):
    app = QCoreApplication.instance() or QCoreApplication([])
    model = LocalModel(endpoint)

    async def turn(actor, query):
        uid = create_new_history(actor)
        live2d = SimpleNamespace(extract_emotion=lambda text: [])
        agent = BasicMemoryAgent(
            model,
            "簡短回答使用者。回憶須依所提供的記憶，缺少證據時回答不知道。",
            live2d,
            use_mcpp=False,
            tts_preprocessor_config=SimpleNamespace(
                remove_special_char=False,
                ignore_brackets=True,
                ignore_parentheses=True,
                ignore_asterisks=True,
                ignore_angle_brackets=True,
            ),
            segment_method="regex",
        )
        agent.set_memory_from_history(actor, uid)
        context = SimpleNamespace(
            history_uid=uid,
            agent_engine=agent,
            live2d_model=live2d,
            tts_engine=None,
            asr_engine=None,
            refresh_system_prompt=AsyncMock(),
            character_config=SimpleNamespace(
                conf_uid=actor,
                character_name=actor,
                human_name="fixture",
                active_project_id="",
                avatar="",
            ),
        )
        handler = WebSocketHandler(context)
        finished = asyncio.get_running_loop().create_future()

        async def connection(ws, path):
            try:
                if path != "/client-ws?client_role=qt-primary":
                    raise AssertionError("Wrong Qt client role")
                socket = SimpleNamespace(send_text=ws.send)
                handler.client_contexts["primary"] = context
                handler.client_connections["primary"] = socket
                handler.client_roles["primary"] = "qt-primary"
                await ws.send(
                    json.dumps(
                        dict(
                            type="set-model-and-conf",
                            client_uid="primary",
                            conf_uid=actor,
                            context_id=actor,
                            history_protocol="kuro.conversation.history.v1",
                            effective_model=os.getenv("KURO_REPLAY_MODEL", MODEL),
                        )
                    )
                )
                async for wire in ws:
                    data = json.loads(wire)
                    if data.get("type") == "fetch-history-list":
                        await ws.send(
                            json.dumps(
                                {
                                    **data,
                                    "type": "history-list",
                                    "current_history_uid": uid,
                                }
                            )
                        )
                    if data.get("type") == "text-input":
                        await handler._handle_conversation_trigger(
                            socket, "primary", data
                        )
                        display = await handler.current_conversation_tasks["primary"]
                        finished.set_result(display)
            except Exception as exc:
                if not finished.done():
                    finished.set_exception(exc)

        received = []
        client = QtRuntimeChatClient()
        client.assistant_text_changed.connect(
            lambda text: received.append(text) if text else None
        )
        async with serve(connection, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            client.connect_to(f"ws://127.0.0.1:{port}/client-ws?client_role=qt-primary")
            try:
                until = time.monotonic() + 10
                requested = False
                while not (client.history_ready and client.current_history_uid == uid):
                    if finished.done():
                        finished.result()
                    if client.history_ready and not requested:
                        requested = client.request_history_list()
                    if time.monotonic() > until:
                        raise TimeoutError("Qt handshake")
                    app.processEvents()
                    await asyncio.sleep(0.01)
                assert client.send_text(query)
                display = await asyncio.wait_for(finished, 240)
                until = time.monotonic() + 5
                while display not in received and time.monotonic() < until:
                    app.processEvents()
                    await asyncio.sleep(0.01)
                assert display and display in received, (display, received)
                transcript = get_history(actor, uid, strict=True)
                assert (
                    transcript[-1]["content"] == display
                    and transcript[-1]["completion"] == "complete"
                )
                return dict(
                    actor=actor,
                    display=display,
                    qt_readback=True,
                    history_readback=True,
                    model=model.calls[-1],
                )
            finally:
                client.disconnect()
        return {}

    with (
        patch(
            "open_llm_vtuber.conversations.single_conversation._load_tts_pronunciation_entries",
            return_value=[],
        ),
        patch(
            "open_llm_vtuber.conversations.single_conversation._load_speech_style_prompt",
            return_value="",
        ),
    ):
        phase = os.getenv("KURO_REPLAY_PHASE")
        if phase == "save":
            return {"turn": await turn("fixture-a", "請記住我喜歡無糖抹茶。")}
        if phase == "read":
            result = await turn("fixture-b", "我喜歡什麼口味的茶？只回答名稱。")
            assert result["model"]["has_fact"] and "抹茶" in result["display"]
            return {"turn": result}
        first = await turn("fixture-a", "請記住我喜歡無糖抹茶。")
        second = await turn("fixture-b", "我喜歡什麼口味的茶？只回答名稱。")
    assert second["model"]["has_fact"] and "抹茶" in second["display"]
    return dict(
        turns=[first, second],
        shared_records=len(list_character_memories("fixture-b")),
        formal_profile=False,
        scope="isolated Qt transport; fixture handshake, actual trigger and local model",
    )


if __name__ == "__main__":
    os.environ["KURO_MEMORY_ROOT"] = str(Path.cwd() / "memories")
    config = Path("settings.yaml").resolve()
    config.write_text("fixture: true\n", encoding="utf-8")
    os.environ["KURO_LAUNCHER_SETTINGS_FILE"] = str(config)
    result = asyncio.run(run(sys.argv[1]))
    Path(sys.argv[2]).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
