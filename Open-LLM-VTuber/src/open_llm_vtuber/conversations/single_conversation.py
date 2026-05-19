from typing import Union, List, Dict, Any, Optional
import asyncio
import json
from loguru import logger
import numpy as np

from .conversation_utils import (
    create_batch_input,
    process_agent_output,
    send_conversation_start_signals,
    process_user_input,
    finalize_conversation_turn,
    cleanup_conversation,
    EMOJI_LIST,
)
from .types import WebSocketSend
from .tts_manager import TTSTaskManager
from ..chat_event_manager import store_history_event
from ..chat_history_manager import store_message
from ..character_memory_manager import process_character_memory_turn
from ..service_context import ServiceContext
# =========================
# Default translation engine (Bridge)
# Ensures legacy/plain-text path can still translate zh->ja to avoid Chinese being spoken.
# Uses local bridge service: POST /translate {text: "..."} -> {code:200,data:"..."}
# =========================
import os
import urllib.request
import urllib.error


class BridgeSpeechEngine:
    """
    Speech renderer backed by local bridge.
    It converts Chinese subtitle text into SHORT spoken Japanese suitable for TTS,
    and also returns an emotion key for Live2D via `last_emotion`.

    Endpoint: POST /render_spoken
      { "text": "...", "mode": "spoken_short", "style_prompt_ja": "..." }
    Response:
      { "code":200, "data":"...ja...", "emotion":"joy" }
    """

    def __init__(self, style_prompt_ja: str = "", endpoint: str | None = None, timeout_s: float = 18.0) -> None:
        self.endpoint = (endpoint or os.getenv("BRIDGE_RENDER_URL", "http://127.0.0.1:1188/render_spoken")).strip()
        self.timeout_s = float(timeout_s)
        self.style_prompt_ja = (style_prompt_ja or "").strip()
        self.last_emotion: str = "neutral"

    def translate(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            self.last_emotion = "neutral"
            return ""

        payload = {"text": t, "mode": "spoken_short"}
        if self.style_prompt_ja:
            payload["style_prompt_ja"] = self.style_prompt_ja

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            obj = json.loads(raw) if raw else {}
            if isinstance(obj, dict):
                self.last_emotion = (obj.get("emotion") or "neutral").strip() or "neutral"
                out = (obj.get("data") or "").strip()
                return out
            self.last_emotion = "neutral"
            return ""
        except Exception as e:
            logger.warning(f"BridgeSpeechEngine render failed: {e}")
            self.last_emotion = "neutral"
            return ""

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"text": t}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            obj = json.loads(raw) if raw else {}
            out = obj.get("data") if isinstance(obj, dict) else ""
            return (out or "").strip()
        except Exception as e:
            logger.warning(f"BridgeSpeechEngine translate failed: {e}")
            return ""


def _load_speech_style_prompt(context: "ServiceContext") -> str:
    """
    Load per-character Japanese speech style prompt from model_dict.json.

    Priority:
    1) env MODEL_DICT_PATH
    2) project_root/model_dict.json (cwd)
    3) fallback: empty string

    Selection key:
    - context.character_config.live2d_model_name if present
    - else context.character_config.conf_name
    - else context.character_config.character_name
    """
    import os
    import json
    from pathlib import Path

    name_key = ""
    try:
        name_key = getattr(context.character_config, "live2d_model_name", "") or ""
        if not name_key:
            name_key = getattr(context.character_config, "conf_name", "") or ""
        if not name_key:
            name_key = getattr(context.character_config, "character_name", "") or ""
    except Exception:
        name_key = ""

    candidates = []
    env_path = os.getenv("MODEL_DICT_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    # Common project-root relative locations
    candidates.append(Path.cwd() / "model_dict.json")
    candidates.append(Path(__file__).resolve().parents[2] / "model_dict.json")  # .../src/open_llm_vtuber -> project
    candidates.append(Path(__file__).resolve().parents[1] / "model_dict.json")

    model_items = None
    for p in candidates:
        try:
            if p.exists():
                model_items = json.loads(p.read_text(encoding="utf-8"))
                break
        except Exception:
            continue

    if not isinstance(model_items, list):
        return ""

    # Find by name
    for item in model_items:
        if not isinstance(item, dict):
            continue
        if (item.get("name") or "").strip() == name_key:
            return (item.get("speech_style_prompt_ja") or "").strip()

    # Fallback: first item with speech_style_prompt_ja
    for item in model_items:
        if isinstance(item, dict) and item.get("speech_style_prompt_ja"):
            return str(item.get("speech_style_prompt_ja")).strip()

    return ""


# Import necessary types from agent outputs
from ..agent.output_types import SentenceOutput, AudioOutput


def _compact_event_text(value: Any, max_len: int = 240) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = str(value)
    compact = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip(" ，、。,.!?！？；;:：") + "…"


def _store_tool_status_event(
    *,
    context: ServiceContext,
    output_item: Dict[str, Any],
    skip_history: bool,
) -> None:
    if skip_history or not context.history_uid:
        return

    status = str(output_item.get("status") or "info").strip().lower()
    if status == "running":
        return

    tool_name = str(output_item.get("tool_name") or "tool").strip() or "tool"
    content_preview = _compact_event_text(output_item.get("content"), max_len=180)
    if status == "completed":
        summary = f"{tool_name} 已完成"
    elif status == "error":
        summary = f"{tool_name} 發生錯誤"
        if content_preview:
            summary = f"{summary}：{content_preview}"
    elif status == "blocked":
        summary = f"{tool_name} 被限制層擋下"
        if content_preview:
            summary = f"{summary}：{content_preview}"
    else:
        summary = f"{tool_name} 狀態：{status}"

    store_history_event(
        conf_uid=context.character_config.conf_uid,
        history_uid=context.history_uid,
        event_type="tool_call",
        status=status,
        title=f"工具：{tool_name}",
        summary=summary,
        detail={
            "tool_id": output_item.get("tool_id"),
            "tool_name": tool_name,
            "status": status,
            "content_preview": content_preview,
        },
    )


def _memory_event_summary(memory_notes: List[str]) -> str:
    upserts = sum(1 for note in memory_notes if note == "upsert")
    disabled = sum(
        int(note.split(":", 1)[1])
        for note in memory_notes
        if note.startswith("disabled:") and note.split(":", 1)[1].isdigit()
    )
    parts: list[str] = []
    if upserts:
        parts.append(f"新增或更新 {upserts} 條角色記憶")
    if disabled:
        parts.append(f"停用 {disabled} 條角色記憶")
    return "，".join(parts) or "角色記憶已更新"


async def process_single_conversation(
    context: ServiceContext,
    websocket_send: WebSocketSend,
    client_uid: str,
    user_input: Union[str, np.ndarray],
    images: Optional[List[Dict[str, Any]]] = None,
    session_emoji: str = np.random.choice(EMOJI_LIST),
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Process a single-user conversation turn

    Args:
        context: Service context containing all configurations and engines
        websocket_send: WebSocket send function
        client_uid: Client unique identifier
        user_input: Text or audio input from user
        images: Optional list of image data
        session_emoji: Emoji identifier for the conversation
        metadata: Optional metadata for special processing flags

    Returns:
        str: Complete response text
    """
    # Create TTSTaskManager for this conversation
    tts_manager = TTSTaskManager()
    full_response = ""  # Initialize full_response here

    # Ensure translate_engine is always available for legacy/plain-text path.
    # Route-A (structured) will mainly use tts_ja directly and rarely needs this.
    translate_engine_to_use = BridgeSpeechEngine(style_prompt_ja=_load_speech_style_prompt(context))

    try:
        # Send initial signals
        await send_conversation_start_signals(websocket_send)
        logger.info(f"New Conversation Chain {session_emoji} started!")

        # Process user input
        input_text = await process_user_input(
            user_input, context.asr_engine, websocket_send
        )

        # Create batch input
        batch_input = create_batch_input(
            input_text=input_text,
            images=images,
            from_name=context.character_config.human_name,
            metadata=metadata,
        )

        # Store user message (check if we should skip storing to history)
        skip_history = metadata and metadata.get("skip_history", False)
        if context.history_uid and not skip_history:
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="human",
                content=input_text,
                name=context.character_config.human_name,
            )

        if skip_history:
            logger.debug("Skipping storing user input to history (proactive speak)")

        logger.info(f"User input: {input_text}")
        if images:
            logger.info(f"With {len(images)} images")

        try:
            # agent.chat yields Union[SentenceOutput, Dict[str, Any]]
            agent_output_stream = context.agent_engine.chat(batch_input)

            async for output_item in agent_output_stream:
                if (
                    isinstance(output_item, dict)
                    and output_item.get("type") == "tool_call_status"
                ):
                    _store_tool_status_event(
                        context=context,
                        output_item=output_item,
                        skip_history=bool(skip_history),
                    )
                    # Handle tool status event: send WebSocket message
                    output_item["name"] = context.character_config.character_name
                    logger.debug(f"Sending tool status update: {output_item}")

                    await websocket_send(json.dumps(output_item))

                elif isinstance(output_item, (SentenceOutput, AudioOutput)):
                    # Handle SentenceOutput or AudioOutput
                    response_part = await process_agent_output(
                        output=output_item,
                        character_config=context.character_config,
                        live2d_model=context.live2d_model,
                        tts_engine=context.tts_engine,
                        websocket_send=websocket_send,  # Pass websocket_send for audio/tts messages
                        tts_manager=tts_manager,
                        translate_engine=translate_engine_to_use,
                    )
                    # Ensure response_part is treated as a string before concatenation
                    response_part_str = (
                        str(response_part) if response_part is not None else ""
                    )
                    full_response += response_part_str  # Accumulate text response
                else:
                    logger.warning(
                        f"Received unexpected item type from agent chat stream: {type(output_item)}"
                    )
                    logger.debug(f"Unexpected item content: {output_item}")

        except Exception as e:
            logger.exception(
                f"Error processing agent response stream: {e}"
            )  # Log with stack trace
            await websocket_send(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error processing agent response: {str(e)}",
                    }
                )
            )
            # full_response will contain partial response before error
        # --- End processing agent response ---

        # Wait for any pending TTS tasks
        if tts_manager.task_list:
            await asyncio.gather(*tts_manager.task_list)
            await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        await finalize_conversation_turn(
            tts_manager=tts_manager,
            websocket_send=websocket_send,
            client_uid=client_uid,
        )

        if context.history_uid and full_response:  # Check full_response before storing
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="ai",
                content=full_response,
                name=context.character_config.character_name,
                avatar=context.character_config.avatar,
            )
            logger.info(f"AI response: {full_response}")

        if context.history_uid and not skip_history and input_text:
            memory_changed, memory_notes = process_character_memory_turn(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                user_text=input_text,
                assistant_text=full_response,
            )
            if memory_changed:
                logger.info(f"Character memory updated: {memory_notes}")
                store_history_event(
                    conf_uid=context.character_config.conf_uid,
                    history_uid=context.history_uid,
                    event_type="memory_update",
                    status="ok",
                    title="角色記憶已更新",
                    summary=_memory_event_summary(memory_notes),
                    detail={"notes": memory_notes},
                )
                await context.refresh_system_prompt()
            elif "skipped-sensitive" in memory_notes:
                store_history_event(
                    conf_uid=context.character_config.conf_uid,
                    history_uid=context.history_uid,
                    event_type="memory_skipped",
                    status="skipped",
                    title="角色記憶未寫入",
                    summary="這次輸入看起來包含敏感資料，因此沒有寫入長期記憶。",
                    detail={"notes": memory_notes},
                )

        return full_response  # Return accumulated full_response

    except asyncio.CancelledError:
        logger.info(f"🤡👍 Conversation {session_emoji} cancelled because interrupted.")
        raise
    except Exception as e:
        logger.error(f"Error in conversation chain: {e}")
        await websocket_send(
            json.dumps({"type": "error", "message": f"Conversation error: {str(e)}"})
        )
        raise
    finally:
        cleanup_conversation(tts_manager, session_emoji)
