import asyncio
import re
import copy
from typing import Optional, Union, Any, List, Dict
import numpy as np
import json
from loguru import logger

# =========================
# Protocol-2 helpers (tags / zh display / ja tts)
# =========================
_EMO_TAG_RE = re.compile(r"\[(?:neutral|joy|happy|sad|angry|surprised|fear|disgust)\]", re.IGNORECASE)

# =========================
# Route-A: structured event stream (JSON + sentinel)
# =========================
_EOM_SENTINEL = "<<<EOM>>>"

_EMOTION_CANON = {
    "happy": "joy",
    "joy": "joy",
    "smile": "joy",
    "sad": "sadness",
    "sadness": "sadness",
    "angry": "anger",
    "anger": "anger",
    "surprised": "surprise",
    "surprise": "surprise",
    "fear": "fear",
    "disgust": "disgust",
    "neutral": "neutral",
    "smirk": "smirk",
}

def _canonicalize_emotion(tag: str) -> str:
    if not tag:
        return ""
    t = str(tag).strip().lower()
    return _EMOTION_CANON.get(t, t)

class _StructuredEventDecoder:
    """Incremental decoder for Route-A streamed events.
    Accepts arbitrary string chunks; extracts JSON objects delimited by the sentinel.
    """
    def __init__(self, eom_sentinel: str = _EOM_SENTINEL) -> None:
        self._buf = ""
        self._sentinel = eom_sentinel

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        self._buf += chunk

    def pop_events(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        if self._sentinel not in self._buf:
            return events
        parts = self._buf.split(self._sentinel)
        # keep remainder (after last sentinel) in buffer
        self._buf = parts[-1]
        for part in parts[:-1]:
            s = (part or "").strip()
            if not s:
                continue
            # Strip code fences if any
            s = re.sub(r"^```(?:json)?\s*", "", s.strip(), flags=re.IGNORECASE)
            s = re.sub(r"```\s*$", "", s.strip())
            obj = self._try_parse_json(s)
            if isinstance(obj, dict):
                events.append(obj)
            else:
                logger.warning(f"Route-A decode failed; dropping segment: {s[:120]!r}")
        return events

    @staticmethod
    def _try_parse_json(s: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(s)
        except Exception:
            # Try best-effort: slice from first { to last }
            try:
                start = s.find("{")
                end = s.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(s[start:end+1])
            except Exception:
                return None
        return None

def _extract_emotion_tags(text: str) -> (list, str):
    """Extract [joy]-style tags and return (tags, cleaned_text). Keeps tag order."""
    if not isinstance(text, str) or not text:
        return [], "" if text is None else str(text)
    tags = [m.group(0)[1:-1].lower() for m in _EMO_TAG_RE.finditer(text)]
    cleaned = _EMO_TAG_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return tags, cleaned

def _looks_like_chinese(text: str) -> bool:
    # Very light heuristic for "likely Chinese" (used only to protect Japanese TTS).
    if not text:
        return False
    # common Chinese particles / function words
    zh_markers = ["的", "了", "嗎", "吧", "在", "這", "那", "也", "很", "不", "我", "你", "他", "她", "它", "們"]
    return any(m in text for m in zh_markers)

def _contains_kana(text: str) -> bool:
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x309F or 0x30A0 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0xFF66 <= o <= 0xFF9F:
            return True
    return False

def _is_safe_japanese_tts(text: str) -> bool:
    """Return True if text is likely acceptable Japanese for TTS.

    IMPORTANT: We must avoid sending Chinese (even if it contains a tiny bit of kana like "ゆきゆき")
    into a Japanese TTS engine. The earlier heuristic ("contains any kana") was too permissive.

    This function uses a conservative rule:
    - If it strongly looks like Chinese AND kana proportion is low -> unsafe.
    - Otherwise, if it contains kana -> likely Japanese -> safe.
    - Else, accept kanji-only texts only when they don't look like Chinese.
    """
    if not text:
        return False

    s = text.strip()
    if not s:
        return False

    # Count kana vs. CJK-ish characters to reject "mostly Chinese with a bit of kana".
    kana = 0
    cjk = 0
    for ch in s:
        o = ord(ch)
        if 0x3040 <= o <= 0x309F or 0x30A0 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0xFF66 <= o <= 0xFF9F:
            kana += 1
        elif 0x4E00 <= o <= 0x9FFF:  # CJK Unified Ideographs
            cjk += 1

    denom = max(kana + cjk, 1)
    kana_ratio = kana / denom

    # If it looks like Chinese and kana ratio is very low, treat as unsafe.
    if _looks_like_chinese(s) and kana_ratio < 0.25:
        return False

    if kana > 0:
        return True

    # allow kanji-only short proper nouns; reject if it looks clearly Chinese
    return not _looks_like_chinese(s)


_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s，。！？、；;）)\]】>」』]+")
_PAREN_URL_RE = re.compile(r"[（(]\s*(?:https?://|www\.)[^\s）)]+[）)]", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:[\\/][^\s，。！？、；;]+")
_POSIX_PATH_RE = re.compile(r"(?<!\w)/(?:[\w.-]+/)+[\w.-]+")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]{1,80})\]\((?:https?://|www\.)[^)]+\)")
_INLINE_CODE_RE = re.compile(r"`([^`]{1,80})`")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>\n]{1,80}>")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"\d")
_DATA_SYMBOL_RE = re.compile(r"[{}\[\]<>\\/=|_$`~^]")


def _count_matches(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text or ""))


def _compact_speech_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s+([，。！？、；：,.!?;:])", r"\1", text)
    text = re.sub(r"([（「『【])\s+", r"\1", text)
    return text.strip(" \t\r\n-•*+|")


def _is_trivial_speech_text(text: str) -> bool:
    core = re.sub(r"[\s\d\-–—•·.,!?，。！？'\"』」）】\[\]（）:：;；]+", "", text or "")
    return len(core) == 0


def _looks_like_display_only_line(text: str) -> bool:
    """Detect lines that should remain visible but not be sent to speech rendering."""
    s = (text or "").strip()
    if not s:
        return True

    cjk = _count_matches(_CJK_RE, s)
    latin = _count_matches(_LATIN_RE, s)
    digits = _count_matches(_DIGIT_RE, s)
    symbols = _count_matches(_DATA_SYMBOL_RE, s)

    if _URL_RE.fullmatch(s) or _EMAIL_RE.fullmatch(s):
        return True
    if re.match(r"(?i)^\s*(url|uri|file|path|traceback|stack trace|snippet|matched queries)\s*:", s):
        return True
    if re.match(r"^\s*(?:```|[{[\]}]|</?\w+)", s) and cjk == 0:
        return True
    if re.match(r"^\s*\|?[-: ]{3,}\|", s):
        return True
    if cjk == 0 and (latin > 0 or digits > 0):
        return True
    if symbols >= 6 and cjk < 12:
        return True
    if len(s) > 80 and cjk < 8 and (latin + digits) > cjk * 3:
        return True
    return False


def _speech_line_is_useful(text: str) -> bool:
    s = _compact_speech_text(text)
    if not s or _is_trivial_speech_text(s):
        return False

    cjk = _count_matches(_CJK_RE, s)
    kana = sum(
        1
        for ch in s
        if 0x3040 <= ord(ch) <= 0x30FF or 0x31F0 <= ord(ch) <= 0x31FF
    )
    latin = _count_matches(_LATIN_RE, s)
    digits = _count_matches(_DIGIT_RE, s)

    if cjk + kana == 0:
        return False
    if latin > 24 and cjk < 10:
        return False
    if digits > 24 and cjk < 12:
        return False
    return True


def _sanitize_speech_line(text: str) -> str:
    """Remove visual-only fragments from a line while keeping speakable meaning."""
    if _looks_like_display_only_line(text):
        return ""

    s = text or ""
    s = _FENCED_CODE_RE.sub(" ", s)
    s = _MARKDOWN_LINK_RE.sub(r"\1", s)
    s = _PAREN_URL_RE.sub("", s)
    s = _URL_RE.sub(" ", s)
    s = _EMAIL_RE.sub(" ", s)
    s = _WINDOWS_PATH_RE.sub(" ", s)
    s = _POSIX_PATH_RE.sub(" ", s)
    s = _HTML_TAG_RE.sub(" ", s)
    s = _INLINE_CODE_RE.sub(r"\1", s)
    s = re.sub(r"\b[A-Za-z][A-Za-z0-9._/-]{12,}\b", " ", s)
    s = re.sub(r"(?i)(?:參考資料|資料來源|來源|網址|連結|url|uri|source|reference)\s*[:：]\s*(?=[，,。；;]|$)", " ", s)
    s = re.sub(r"[:：]\s*([，,。；;])", r"\1", s)
    s = re.sub(r"^\s*[，,、；;。]+", "", s)
    s = re.sub(r"[（(]\s*[）)]", " ", s)
    s = re.sub(r"^\s*[-•*+]\s*", "", s)
    s = _compact_speech_text(s)

    if not _speech_line_is_useful(s):
        return ""
    return s


def _trim_speech_source(text: str, max_chars: int = 420) -> str:
    text = _compact_speech_text(text)
    if len(text) <= max_chars:
        return text

    pieces = re.split(r"(?<=[。！？!?])\s*", text)
    kept: list[str] = []
    total = 0
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        next_total = total + len(piece)
        if kept and next_total > max_chars:
            break
        kept.append(piece)
        total = next_total

    if kept:
        return _compact_speech_text(" ".join(kept))
    return text[:max_chars].rstrip("，、；：,.!?！？ ") + "。"


def _build_speech_source(display_text: str, tts_text: str) -> str:
    """Build the Chinese source text that is safe to translate into spoken Japanese.

    The display lane keeps the original subtitle. This speech lane removes or skips
    visual-only material such as URLs, paths, code, logs, and dense data.
    """
    source = (tts_text or "").strip() or (display_text or "").strip()
    if not source:
        return ""

    _, source = _extract_emotion_tags(source)
    source = _FENCED_CODE_RE.sub(" ", source)

    parts: list[str] = []
    for raw_line in re.split(r"\r\n?|\n", source):
        line = _sanitize_speech_line(raw_line)
        if line:
            parts.append(line)

    if not parts:
        return ""
    return _trim_speech_source(" ".join(parts))


from ..message_handler import message_handler
from .types import WebSocketSend, BroadcastContext
from .tts_manager import TTSTaskManager
from ..agent.output_types import SentenceOutput, AudioOutput
from ..agent.input_types import BatchInput, TextData, ImageData, TextSource, ImageSource
from ..asr.asr_interface import ASRInterface
from ..live2d_model import Live2dModel
from ..tts.tts_interface import TTSInterface
from ..utils.stream_audio import prepare_audio_payload


# Convert class methods to standalone functions
def create_batch_input(
    input_text: str,
    images: Optional[List[Dict[str, Any]]],
    from_name: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> BatchInput:
    """Create batch input for agent processing"""
    return BatchInput(
        texts=[
            TextData(source=TextSource.INPUT, content=input_text, from_name=from_name)
        ],
        images=[
            ImageData(
                source=ImageSource(img["source"]),
                data=img["data"],
                mime_type=img["mime_type"],
            )
            for img in (images or [])
        ]
        if images
        else None,
        metadata=metadata,
    )


async def process_agent_output(
    output: Union[AudioOutput, SentenceOutput],
    character_config: Any,
    live2d_model: Live2dModel,
    tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
    translate_engine: Optional[Any] = None,
) -> str:
    """Process agent output with character information and optional translation"""
    output.display_text.name = character_config.character_name
    output.display_text.avatar = character_config.avatar

    full_response = ""
    try:
        if isinstance(output, SentenceOutput):
            full_response = await handle_sentence_output(
                output,
                live2d_model,
                tts_engine,
                websocket_send,
                tts_manager,
                translate_engine,
            )
        elif isinstance(output, AudioOutput):
            full_response = await handle_audio_output(output, websocket_send)
        else:
            logger.warning(f"Unknown output type: {type(output)}")
    except Exception as e:
        logger.error(f"Error processing agent output: {e}")
        await websocket_send(
            json.dumps(
                {"type": "error", "message": f"Error processing response: {str(e)}"}
            )
        )

    return full_response



async def handle_sentence_output(
    output: SentenceOutput,
    live2d_model: Live2dModel,
    tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
    translate_engine: Optional[Any] = None,
) -> str:
    """
    Dual-flow pipeline (recommended):

    - Subtitle lane: always Traditional Chinese (display_text.text), streamed to frontend as SILENT payloads.
    - Voice lane: one short spoken Japanese line rendered from a sanitized, speakable Chinese source.
    - Emotion lane: derived from translate_engine (bridge) if available; otherwise fallback to inline tags (legacy).

    This avoids long list/step content being spoken and greatly reduces playback queue / timeouts.
    """
    full_response = ""
    full_zh = ""
    speech_zh_parts: List[str] = []
    pending_tags: List[str] = []
    last_display = None
    last_actions = None

    async def _emit_emotion_from_key(key: str) -> None:
        k = _canonicalize_emotion(key)
        if not k:
            return
        try:
            await websocket_send(
                json.dumps({"type": "emotion", "emotion": k, "tags": [k]}, ensure_ascii=False)
            )
            logger.info(f"🎭 Emitted emotion tags: {[k]}")
        except Exception as e:
            logger.warning(f"Failed to emit emotion tags: {e}")

    async def _emit_emotion(tags_to_send: List[str]) -> None:
        if not tags_to_send:
            return
        canon_tags = [_canonicalize_emotion(t) for t in tags_to_send if t]
        canon_tags = [t for t in canon_tags if t]
        if not canon_tags:
            return
        try:
            await websocket_send(
                json.dumps({"type": "emotion", "emotion": canon_tags[-1], "tags": canon_tags}, ensure_ascii=False)
            )
            logger.info(f"🎭 Emitted emotion tags: {canon_tags}")
        except Exception as e:
            logger.warning(f"Failed to emit emotion tags: {e}")

    async def _render_spoken_ja(text_zh: str) -> str:
        """
        Call bridge-backed speech renderer if available.
        translate_engine.translate(text) should return Japanese; if engine exposes last_emotion, we use it.
        """
        if not text_zh:
            return ""
        if not translate_engine:
            return ""
        try:
            ja = await asyncio.to_thread(translate_engine.translate, text_zh)
            return (ja or "").strip()
        except Exception as e:
            logger.warning(f"Speech render failed: {e}")
            return ""

    # Stream subtitle updates as silent payloads
    async for display_text, tts_text, actions in output:
        raw_disp = getattr(display_text, "text", "") if display_text is not None else ""
        tags, clean_disp = _extract_emotion_tags(raw_disp)
        if tags:
            pending_tags.extend(tags)

        if clean_disp:
            full_response += clean_disp
            full_zh += clean_disp
            speech_source = _build_speech_source(clean_disp, str(tts_text or ""))
            if speech_source:
                speech_zh_parts.append(speech_source)
            last_display = display_text
            last_actions = actions
    # Send ONE silent subtitle payload (Chinese) to create/update the assistant bubble.
    # This avoids subtitle duplication caused by progressive append behavior in some frontends.
    if full_zh.strip():
        if last_display is not None:
            dt_show = copy.deepcopy(last_display)
        else:
            dt_show = copy.deepcopy(getattr(output, "display_text", None))
        if dt_show is not None:
            dt_show.text = full_zh.strip()
            await tts_manager.speak(
                tts_text="",
                display_text=dt_show,
                actions=last_actions,
                live2d_model=live2d_model,
                tts_engine=tts_engine,
                websocket_send=websocket_send,
            )



    # Final: render ONE short spoken Japanese line from the speech-source lane.
    # Keep display and speech intentionally separate: visual-only details stay visible
    # but do not get fed into Japanese TTS.
    full_zh_text = full_zh.strip()
    speech_zh_text = _trim_speech_source(" ".join(speech_zh_parts))
    if full_zh_text and not speech_zh_text:
        logger.info("Speech-source lane is empty after sanitizing; display-only response will stay silent.")

    spoken_ja = await _render_spoken_ja(speech_zh_text)
    if spoken_ja and spoken_ja.strip() == speech_zh_text:
        logger.warning("Speech renderer returned the original subtitle text; skip voice lane to avoid feeding zh text into ja TTS.")
        spoken_ja = ""
    emotion_key = getattr(translate_engine, "last_emotion", "") if translate_engine else ""

    # Prefer bridge-derived emotion; fallback to inline tags; else neutral
    if emotion_key:
        await _emit_emotion_from_key(emotion_key)
    elif pending_tags:
        await _emit_emotion(pending_tags)
    else:
        await _emit_emotion_from_key("neutral")

    if spoken_ja:
        # Speak one Japanese audio. Subtitle has already been updated via 'full-text', so avoid re-sending it here to prevent duplicates.
        if last_display is not None:
            dt2 = copy.deepcopy(last_display)
            dt2.text = ""
        else:
            dt2 = copy.deepcopy(getattr(output, "display_text", None))
            if dt2 is not None:
                dt2.text = ""

        await tts_manager.speak(
            tts_text=spoken_ja,
            display_text=dt2,
            actions=last_actions,
            live2d_model=live2d_model,
            tts_engine=tts_engine,
            websocket_send=websocket_send,
        )
    else:
        logger.warning("No spoken Japanese generated; skipping voice lane for this turn.")

    return full_response


async def handle_audio_output(
    output: AudioOutput,
    websocket_send: WebSocketSend,
) -> str:
    """Process and send AudioOutput directly to the client"""
    full_response = ""
    async for audio_path, display_text, transcript, actions in output:
        full_response += transcript
        audio_payload = prepare_audio_payload(
            audio_path=audio_path,
            display_text=display_text,
            actions=actions.to_dict() if actions else None,
        )
        await websocket_send(json.dumps(audio_payload))
    return full_response


async def send_conversation_start_signals(websocket_send: WebSocketSend) -> None:
    """Send initial conversation signals"""
    await websocket_send(
        json.dumps(
            {
                "type": "control",
                "text": "conversation-chain-start",
            }
        )
    )
    await websocket_send(json.dumps({"type": "full-text", "text": "Thinking..."}))


async def process_user_input(
    user_input: Union[str, np.ndarray],
    asr_engine: ASRInterface,
    websocket_send: WebSocketSend,
) -> str:
    """Process user input, converting audio to text if needed"""
    if isinstance(user_input, np.ndarray):
        logger.info("Transcribing audio input...")
        input_text = await asr_engine.async_transcribe_np(user_input)
        await websocket_send(
            json.dumps({"type": "user-input-transcription", "text": input_text})
        )
        return input_text
    return user_input


async def finalize_conversation_turn(
    tts_manager: TTSTaskManager,
    websocket_send: WebSocketSend,
    client_uid: str,
    broadcast_ctx: Optional[BroadcastContext] = None,
) -> None:
    """Finalize a conversation turn"""
    if tts_manager.task_list:
        await asyncio.gather(*tts_manager.task_list)
        await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        try:
            response = await asyncio.wait_for(
                message_handler.wait_for_response(client_uid, "frontend-playback-complete"),
                timeout=30,
            )
        except asyncio.TimeoutError:
            response = None
            logger.warning(f"Playback completion timeout for {client_uid}; forcing turn finalize.")

        if not response:
            logger.warning(f"No playback completion response from {client_uid}; continuing finalize.")

    await websocket_send(json.dumps({"type": "force-new-message"}))

    if broadcast_ctx and broadcast_ctx.broadcast_func:
        await broadcast_ctx.broadcast_func(
            broadcast_ctx.group_members,
            {"type": "force-new-message"},
            broadcast_ctx.current_client_uid,
        )

    await send_conversation_end_signal(websocket_send, broadcast_ctx)


async def send_conversation_end_signal(
    websocket_send: WebSocketSend,
    broadcast_ctx: Optional[BroadcastContext],
    session_emoji: str = "😊",
) -> None:
    """Send conversation chain end signal"""
    chain_end_msg = {
        "type": "control",
        "text": "conversation-chain-end",
    }

    await websocket_send(json.dumps(chain_end_msg))

    if broadcast_ctx and broadcast_ctx.broadcast_func and broadcast_ctx.group_members:
        await broadcast_ctx.broadcast_func(
            broadcast_ctx.group_members,
            chain_end_msg,
        )

    logger.info(f"😎👍✅ Conversation Chain {session_emoji} completed!")


def cleanup_conversation(tts_manager: TTSTaskManager, session_emoji: str) -> None:
    """Clean up conversation resources"""
    tts_manager.clear()
    logger.debug(f"🧹 Clearing up conversation {session_emoji}.")


EMOJI_LIST = [
    "🐶",
    "🐱",
    "🐭",
    "🐹",
    "🐰",
    "🦊",
    "🐻",
    "🐼",
    "🐨",
    "🐯",
    "🦁",
    "🐮",
    "🐷",
    "🐸",
    "🐵",
    "🐔",
    "🐧",
    "🐦",
    "🐤",
    "🐣",
    "🐥",
    "🦆",
    "🦅",
    "🦉",
    "🦇",
    "🐺",
    "🐗",
    "🐴",
    "🦄",
    "🐝",
    "🌵",
    "🎄",
    "🌲",
    "🌳",
    "🌴",
    "🌱",
    "🌿",
    "☘️",
    "🍀",
    "🍂",
    "🍁",
    "🍄",
    "🌾",
    "💐",
    "🌹",
    "🌸",
    "🌛",
    "🌍",
    "⭐️",
    "🔥",
    "🌈",
    "🌩",
    "⛄️",
    "🎃",
    "🎄",
    "🎉",
    "🎏",
    "🎗",
    "🀄️",
    "🎭",
    "🎨",
    "🧵",
    "🪡",
    "🧶",
    "🥽",
    "🥼",
    "🦺",
    "👔",
    "👕",
    "👜",
    "👑",
]
