from typing import Union, List, Dict, Any, Optional
import asyncio
import json
import time
import uuid
from loguru import logger
import numpy as np

from .conversation_utils import (
    create_batch_input,
    process_agent_output,
    send_conversation_start_signals,
    process_user_input,
    format_uploaded_file_display_text,
    summarize_uploaded_files,
    finalize_conversation_turn,
    cleanup_conversation,
    flush_deferred_sentence_speech,
    queue_generated_speech,
    EMOJI_LIST,
)
from .types import WebSocketSend
from .tts_manager import TTSTaskManager
from ..chat_event_manager import store_history_event
from ..chat_history_manager import store_message
from ..mcpp.privacy import project, safe_text
from ..character_memory_manager import finish_pending_turns, formation_policy_digest
from ..mcpp.market_preflight import (
    build_omi_evidence_snapshot,
    format_omi_evidence_for_history,
)
from ..service_context import ServiceContext

# =========================
# Default translation engine (Bridge)
# Ensures legacy/plain-text path can still translate zh->ja to avoid Chinese being spoken.
# Uses local bridge service: POST /translate {text: "..."} -> {code:200,data:"..."}
# =========================
import os
from pathlib import Path
import urllib.request
import urllib.error
from ..speech_pronunciation import (
    PronunciationEntry,
    collect_pronunciation_entries,
    merge_pronunciation_entries,
    normalize_pronunciation_entries,
)


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

    def __init__(
        self,
        style_prompt_ja: str = "",
        endpoint: str | None = None,
        translate_endpoint: str | None = None,
        timeout_s: float = 30.0,
        pronunciation_entries: list[PronunciationEntry] | None = None,
    ) -> None:
        self.endpoint = (
            endpoint
            or os.getenv("BRIDGE_RENDER_URL", "http://127.0.0.1:1188/render_spoken")
        ).strip()
        self.translate_endpoint = (
            translate_endpoint
            or os.getenv("BRIDGE_TRANSLATE_URL", "")
            or self.endpoint.rsplit("/", 1)[0] + "/translate"
        ).strip()
        configured_timeout = (os.getenv("BRIDGE_RENDER_TIMEOUT_S", "") or "").strip()
        try:
            self.timeout_s = (
                float(configured_timeout) if configured_timeout else float(timeout_s)
            )
        except ValueError:
            logger.warning(
                f"Invalid BRIDGE_RENDER_TIMEOUT_S={configured_timeout!r}; using {timeout_s}s."
            )
            self.timeout_s = float(timeout_s)
        configured_translate_fallback_max = (
            os.getenv("BRIDGE_TRANSLATE_FALLBACK_MAX_SOURCE_CHARS", "") or ""
        ).strip()
        try:
            self.translate_fallback_max_source_chars = (
                int(configured_translate_fallback_max)
                if configured_translate_fallback_max
                else 120
            )
        except ValueError:
            logger.warning(
                f"Invalid BRIDGE_TRANSLATE_FALLBACK_MAX_SOURCE_CHARS={configured_translate_fallback_max!r}; using 120."
            )
            self.translate_fallback_max_source_chars = 120
        self.style_prompt_ja = (style_prompt_ja or "").strip()
        self.pronunciation_entries = normalize_pronunciation_entries(
            pronunciation_entries or []
        )
        self.last_emotion: str = "neutral"
        self.last_provider: str = ""
        self.last_pronunciation_hits: list[str] = []
        self.last_speech_repaired: bool = False
        self.request_count = 0

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        obj = json.loads(raw) if raw else {}
        return obj if isinstance(obj, dict) else {}

    def _translate_only(self, text: str) -> str:
        obj = self._post_json(self.translate_endpoint, {"text": text})
        out = (obj.get("data") or "").strip()
        if out:
            self.last_emotion = "neutral"
            self.last_provider = (obj.get("provider") or "bridge:translate").strip()
            self.last_pronunciation_hits = []
            self.last_speech_repaired = False
        return out

    def translate(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            self.last_emotion = "neutral"
            return ""

        if self.request_count >= 1:
            logger.warning("Legacy speech renderer turn budget exhausted; keeping remaining speech silent.")
            return ""
        self.request_count += 1

        payload = {"text": t, "mode": "spoken_short"}
        if self.style_prompt_ja:
            payload["style_prompt_ja"] = self.style_prompt_ja
        if self.pronunciation_entries:
            payload["pronunciation"] = self.pronunciation_entries

        try:
            obj = self._post_json(self.endpoint, payload)
            if isinstance(obj, dict):
                self.last_emotion = (
                    obj.get("emotion") or "neutral"
                ).strip() or "neutral"
                self.last_provider = (obj.get("provider") or "").strip()
                hits = obj.get("pronunciation_hits")
                self.last_pronunciation_hits = (
                    [str(item) for item in hits] if isinstance(hits, list) else []
                )
                self.last_speech_repaired = bool(obj.get("speech_repaired"))
                out = (obj.get("data") or "").strip()
                if (
                    not out
                    and self.translate_endpoint
                    and len(t) <= self.translate_fallback_max_source_chars
                ):
                    try:
                        out = self._translate_only(t)
                    except Exception as fallback_exc:
                        logger.warning(
                            f"BridgeSpeechEngine translate-only fallback failed: {fallback_exc}"
                        )
                return out
            self.last_emotion = "neutral"
            self.last_provider = ""
            self.last_pronunciation_hits = []
            self.last_speech_repaired = False
            return ""
        except Exception as e:
            logger.warning('BridgeSpeechEngine render failed; payload details omitted.')
            self.last_emotion = "neutral"
            self.last_provider = ""
            self.last_pronunciation_hits = []
            self.last_speech_repaired = False
            return ""


def _open_llm_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _repo_root() -> Path:
    return _open_llm_root().parent


def _character_keys(context: "ServiceContext") -> list[str]:
    keys: list[str] = []
    for attr in ("live2d_model_name", "conf_uid", "conf_name", "character_name"):
        try:
            value = str(getattr(context.character_config, attr, "") or "").strip()
        except Exception:
            value = ""
        if value and value not in keys:
            keys.append(value)
    return keys


def _model_dict_candidates() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.getenv("MODEL_DICT_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / "model_dict.json")
    candidates.append(_open_llm_root() / "model_dict.json")
    candidates.append(_repo_root() / "model_dict.json")
    return candidates


def _read_json_file(path: Path) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning('Failed to read JSON file; payload details omitted.')
    return None


def _load_model_dict_items() -> list[dict[str, Any]]:
    for path in _model_dict_candidates():
        try:
            payload = _read_json_file(path)
        except Exception:
            continue
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    return []


def _find_model_dict_item(context: "ServiceContext") -> dict[str, Any] | None:
    character_keys = {key.strip() for key in _character_keys(context)}
    model_items = _load_model_dict_items()
    for item in model_items:
        if str(item.get("name") or "").strip() in character_keys:
            return item
    return None


def _load_speech_style_prompt(context: "ServiceContext") -> str:
    """Load per-character Japanese speech style prompt from model_dict.json."""
    item = _find_model_dict_item(context)
    if item and item.get("speech_style_prompt_ja"):
        return str(item.get("speech_style_prompt_ja")).strip()
    for fallback in _load_model_dict_items():
        if fallback.get("speech_style_prompt_ja"):
            return str(fallback.get("speech_style_prompt_ja")).strip()
    return ""


def _load_tts_pronunciation_entries(
    context: "ServiceContext",
) -> list[PronunciationEntry]:
    project_id = str(
        getattr(context.character_config, "active_project_id", "") or ""
    ).strip()
    character_keys = _character_keys(context)
    open_llm_root = _open_llm_root()
    repo_root = _repo_root()

    entry_groups: list[list[PronunciationEntry]] = []

    env_paths = [
        item.strip()
        for item in os.getenv("KURO_TTS_PRONUNCIATION_PATH", "").split(os.pathsep)
        if item.strip()
    ]
    candidate_paths = [Path(item) for item in env_paths]
    candidate_paths.extend(
        [
            open_llm_root / "tts_pronunciation.json",
            repo_root / "tts_pronunciation.json",
        ]
    )
    if project_id:
        candidate_paths.append(
            repo_root / "projects" / project_id / "tts_pronunciation.json"
        )

    for path in candidate_paths:
        payload = _read_json_file(path)
        if payload:
            entry_groups.append(
                collect_pronunciation_entries(
                    payload,
                    character_keys=character_keys,
                    project_id=project_id,
                )
            )

    model_item = _find_model_dict_item(context)
    if model_item:
        entry_groups.append(
            collect_pronunciation_entries(
                model_item.get("pronunciation") or model_item.get("tts_pronunciation"),
                character_keys=character_keys,
                project_id=project_id,
            )
        )

    return merge_pronunciation_entries(*entry_groups)


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
    if status == "completed" and tool_name == "omi-search::omi_ask":
        evidence = output_item.get("omi_evidence") or build_omi_evidence_snapshot(str(output_item.get("content") or ""))
        if evidence:
            store_history_event(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                event_type="omi_evidence",
                status=status,
                title="OMI 證據",
                summary=format_omi_evidence_for_history(evidence, max_len=360),
                detail=evidence,
                compact_detail=False,
            )
            return

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
    upserts = sum(
        1 for note in memory_notes if note == "upsert" or note.startswith("upsert:")
    )
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
    files: Optional[List[Dict[str, Any]]] = None,
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
        files: Optional list of uploaded file data
        session_emoji: Emoji identifier for the conversation
        metadata: Optional metadata for special processing flags

    Returns:
        str: Complete response text
    """
    # Create TTSTaskManager for this conversation
    tts_manager = TTSTaskManager()
    speech_request_id = getattr(websocket_send, "request_id", None)
    if isinstance(speech_request_id, str):
        tts_manager.speech_metrics["request_id"] = speech_request_id
    turn_id = uuid.uuid4().hex
    project_id = getattr(context.character_config, "active_project_id", "") or ""
    user_receipt = {}
    history_failed = False
    grant = ""
    full_response = ""  # Initialize full_response here
    speech_lane = None
    speech_tool_status = {}
    response_complete = False
    try:
        from kuro_launcher.config import read_chat_speech_settings
        settings_path = Path(os.environ.get("KURO_LAUNCHER_SETTINGS_FILE") or _repo_root() / "kuro_launcher.settings.yaml")
        chat_speech = read_chat_speech_settings(settings_path)["settings"]
        settings_available = True
    except (ImportError, OSError, ValueError):
        logger.warning("Chat speech settings unavailable; preserving display with silent speech.")
        chat_speech = {"locale": "ja-JP", "policy": "summary", "route": "dual_lane"}
        settings_available = False

    # Ensure translate_engine is always available for legacy/plain-text path.
    # Route-A (structured) will mainly use tts_ja directly and rarely needs this.
    pronunciation_entries = _load_tts_pronunciation_entries(context)
    if pronunciation_entries:
        logger.info(f"Loaded {len(pronunciation_entries)} TTS pronunciation entries.")
    translate_engine_to_use = BridgeSpeechEngine(
        style_prompt_ja=_load_speech_style_prompt(context),
        pronunciation_entries=pronunciation_entries,
    )

    try:
        # Send initial signals
        await send_conversation_start_signals(websocket_send)
        logger.info(f"New Conversation Chain {session_emoji} started!")

        # Process user input
        display_input_text = await process_user_input(
            user_input, context.asr_engine, websocket_send
        )
        from .speech_recovery import requested_reading
        reading_policy = requested_reading(display_input_text)
        if reading_policy:
            chat_speech = dict(chat_speech, policy=reading_policy)
        input_text = display_input_text
        file_notes = await summarize_uploaded_files(files, context.asr_engine)
        if file_notes:
            input_text = "\n\n".join(
                part
                for part in [
                    input_text,
                    "[Uploaded file analysis]\n" + "\n\n".join(file_notes),
                ]
                if part
            )
        visible_input_text = format_uploaded_file_display_text(
            display_input_text, files
        )

        # Create batch input
        batch_input = create_batch_input(
            input_text=input_text,
            images=images,
            files=files,
            from_name=context.character_config.human_name,
            metadata={**(metadata or {}), "chat_speech": chat_speech, "memory_turn_id": turn_id, "memory_project_id": project_id},
        )

        # Store user message (check if we should skip storing to history)
        skip_history = metadata and metadata.get("skip_history", False)
        if context.history_uid and not skip_history:
            try:
                grant = formation_policy_digest(context.character_config.conf_uid,project_id)
            except (ValueError,OSError):
                logger.warning("Memory policy unavailable; automatic formation disabled for this turn")
            try:
                user_receipt = await asyncio.to_thread(store_message,
                    conf_uid=context.character_config.conf_uid,
                    history_uid=context.history_uid,
                    role="human",
                    content=visible_input_text, turn_id=turn_id, completion="received", project_id=project_id,
                    name=context.character_config.human_name,
                )
            except (OSError,ValueError) as exc:
                history_failed = True
                logger.warning("User turn persistence unavailable ({})",type(exc).__name__)

        if skip_history:
            logger.debug("Skipping storing user input to history (proactive speak)")

        logger.info('User input; payload details omitted.')
        if file_notes:
            logger.debug(
                f"Uploaded file analysis added to agent input: {len(file_notes)} section(s)"
            )
        if images:
            logger.info(f"With {len(images)} images")
        if files:
            logger.info(f"With {len(files)} uploaded files")

        try:
            # agent.chat yields Union[SentenceOutput, Dict[str, Any]]
            agent_output_stream = context.agent_engine.chat(batch_input)

            async for output_item in agent_output_stream:
                if isinstance(output_item, dict) and output_item.get("type") == "speech_lane":
                    speech_lane = output_item  # Internal only, never WS/history/memory.
                elif (
                    isinstance(output_item, dict)
                    and output_item.get("type") == "tool_call_status"
                ):
                    output_item = project(output_item)
                    name = str(output_item.get("tool_name") or "")
                    status = str(output_item.get("execution_status") or output_item.get("status") or "")
                    if name and status not in {"", "running", "pending"}:
                        speech_tool_status[output_item.get("tool_id") or name] = (name, status)
                    _store_tool_status_event(
                        context=context,
                        output_item=output_item,
                        skip_history=bool(skip_history),
                    )
                    # Handle tool status event: send WebSocket message
                    output_item["name"] = context.character_config.character_name
                    output_item["content"] = safe_text(str(output_item.get("content") or ""), limit=2048)
                    logger.debug('Sending tool status update; payload details omitted.')

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
                        defer_sentence_voice=isinstance(output_item, SentenceOutput),
                    )
                    # Ensure response_part is treated as a string before concatenation
                    response_part_str = (
                        str(response_part) if response_part is not None else ""
                    )
                    full_response += response_part_str  # Accumulate text response
                else:
                    logger.warning('Received unexpected item type from agent chat stream; payload details omitted.')
                    logger.debug('Unexpected item content; payload details omitted.')

            response_complete = True
            tts_manager.speech_metrics["llm_complete_at"] = time.monotonic()

        except Exception as e:
            logger.error('Error processing agent response stream; payload details omitted.')  # Log with stack trace
            await websocket_send(
                json.dumps(
                    {
                        "type": "error",
                        "message": "Error processing agent response; details omitted.",
                    }
                )
            )
            # full_response will contain partial response before error
        # --- End processing agent response ---

        if context.history_uid and full_response and not skip_history and not history_failed:
            try:
                await asyncio.to_thread(store_message,
                    conf_uid=context.character_config.conf_uid,
                    history_uid=context.history_uid,
                    role="ai",
                    content=full_response, turn_id=turn_id, project_id=project_id,
                    completion="complete" if response_complete else "interrupted", formation_rule=grant,
                    name=context.character_config.character_name,
                    avatar=context.character_config.avatar,
                )
            except (OSError,ValueError) as exc:
                history_failed = True
                logger.warning("Assistant turn persistence unavailable ({})",type(exc).__name__)
            logger.info('AI response; payload details omitted.')

        if chat_speech["route"] == "legacy_bridge" and response_complete and settings_available:
            # Explicit rollback only; dual-lane never invokes this second LLM.
            await flush_deferred_sentence_speech(
                live2d_model=context.live2d_model, tts_engine=context.tts_engine,
                websocket_send=websocket_send, tts_manager=tts_manager,
                translate_engine=translate_engine_to_use)
            tts_manager.speech_metrics.update(route="legacy_bridge", bridge_requests=translate_engine_to_use.request_count)
        else:
            if response_complete and settings_available and context.tts_engine is not None and speech_lane is not None:
                from .speech_recovery import recover_speech_lane
                speech_lane = await recover_speech_lane(
                    speech_lane, display=full_response, settings=chat_speech,
                    agent=context.agent_engine, metrics=tts_manager.speech_metrics, send=websocket_send,
                    style=_load_speech_style_prompt(context), evidence=list(speech_tool_status.values()))
            await queue_generated_speech(
                lane=speech_lane if response_complete and settings_available else None,
                settings=chat_speech, tts_manager=tts_manager, tts_engine=context.tts_engine,
                live2d_model=context.live2d_model, websocket_send=websocket_send,
                pronunciation_entries=pronunciation_entries,
                completed_display=full_response if response_complete and settings_available else "")
        logger.info("speech_timing {}", json.dumps(tts_manager.speech_metrics, sort_keys=True))

        await finalize_conversation_turn(
            tts_manager=tts_manager,
            websocket_send=websocket_send,
            client_uid=client_uid,
        )

        if history_failed:
            await websocket_send(json.dumps({"type":"error","message":"本輪歷史保存失敗。回覆可在目前對話查看，此輪未加入長期記憶。"}))
        if response_complete and full_response and context.history_uid and not skip_history and visible_input_text and not history_failed:
            try:
                memory_changed, memory_notes = await asyncio.to_thread(
                    finish_pending_turns,context.character_config.conf_uid,context.history_uid,turn_id,
                    dict(user_text=visible_input_text, assistant_text=full_response, project_id=project_id,
                         **(user_receipt or {})))
            except Exception as exc:
                memory_changed, memory_notes = False, ["formation-deferred"]
                logger.warning("Memory formation deferred ({})", type(exc).__name__)
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
                try:
                    await context.refresh_system_prompt()
                except Exception as exc:
                    logger.warning("Saved memory prompt refresh deferred ({})",type(exc).__name__)
            if "formation-deferred" in memory_notes:
                store_history_event(conf_uid=context.character_config.conf_uid, history_uid=context.history_uid,
                                    event_type="memory_deferred", status="pending", title="記憶待重新處理",
                                    summary="下次完成對話時重試。", detail={"turn_id":turn_id})
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
        logger.error('Error in conversation chain; payload details omitted.')
        await websocket_send(
            json.dumps({"type": "error", "message": "Conversation error; details omitted."})
        )
        raise
    finally:
        cleanup_conversation(tts_manager, session_emoji)
