import asyncio
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import io
import re
import copy
import struct
import tarfile
from typing import Optional, Union, Any, List, Dict
import zipfile
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
from ..agent.input_types import (
    BatchInput,
    FileData,
    TextData,
    ImageData,
    TextSource,
    ImageSource,
)
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
    files: Optional[List[Dict[str, Any]]] = None,
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
        files=[
            FileData(
                name=str(file.get("name") or "uploaded-file"),
                data=str(file.get("data") or ""),
                mime_type=str(file.get("mime_type") or file.get("type") or ""),
                kind=str(file.get("kind") or "") or None,
            )
            for file in (files or [])
            if isinstance(file, dict)
        ]
        if files
        else None,
        metadata=metadata,
    )


def _decode_data_url(data: str) -> tuple[str, bytes]:
    raw = str(data or "").strip()
    if not raw:
        return "", b""

    match = re.match(r"^data:([^;,]+)?(?:;[^,]*)?,(.*)$", raw, re.DOTALL)
    if match:
        mime_type = (match.group(1) or "").strip()
        payload = match.group(2) or ""
    else:
        mime_type = ""
        payload = raw

    try:
        return mime_type, base64.b64decode(payload, validate=False)
    except Exception:
        return mime_type, b""


def _audio_bytes_to_float32(data: bytes, mime_type: str = "") -> np.ndarray:
    if not data:
        return np.array([], dtype=np.float32)

    try:
        from pydub import AudioSegment

        fmt = ""
        if "/" in mime_type:
            fmt = mime_type.split("/", 1)[1].split(";", 1)[0].lower()
            if fmt == "mpeg":
                fmt = "mp3"
            elif fmt == "x-wav":
                fmt = "wav"

        audio = AudioSegment.from_file(io.BytesIO(data), format=fmt or None)
        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        samples = np.frombuffer(audio.raw_data, dtype=np.int16).astype(np.float32)
        return samples / 32768.0
    except Exception as exc:
        logger.warning(f"Audio attachment decode failed: {exc}")
        return np.array([], dtype=np.float32)


MAX_TEXT_ATTACHMENT_CHARS = 12000
MAX_ARCHIVE_ENTRIES = 80
MAX_ARCHIVE_TEXT_FILES = 8
MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024
MAX_ARCHIVE_MEMBER_TEXT_CHARS = 1800
MAX_BINARY_STRING_SCAN_BYTES = 4 * 1024 * 1024
MAX_BINARY_STRINGS = 80

TEXT_ATTACHMENT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".tsv",
    ".log",
    ".env",
    ".gitignore",
    ".xml",
}

CODE_ATTACHMENT_EXTENSIONS = {
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".scss",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".java",
    ".go",
    ".rs",
    ".php",
    ".rb",
    ".lua",
    ".sql",
    ".swift",
    ".kt",
    ".kts",
    ".dart",
    ".vue",
    ".svelte",
    ".r",
    ".pl",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
}

ARCHIVE_ATTACHMENT_EXTENSIONS = {".zip", ".tar", ".tgz", ".tar.gz", ".gz"}
BINARY_ATTACHMENT_EXTENSIONS = {".exe", ".dll", ".bin", ".dat"}
ARCHIVE_ATTACHMENT_MIME_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
}
BINARY_ATTACHMENT_MIME_TYPES = {
    "application/octet-stream",
    "application/vnd.microsoft.portable-executable",
    "application/x-msdownload",
    "application/x-dosexec",
}

PE_MACHINE_TYPES = {
    0x014C: "x86",
    0x0200: "Intel Itanium",
    0x8664: "x64",
    0x01C0: "ARM",
    0x01C4: "ARMv7",
    0xAA64: "ARM64",
}

PE_SUBSYSTEM_TYPES = {
    1: "Native",
    2: "Windows GUI",
    3: "Windows CUI",
    7: "POSIX CUI",
    9: "Windows CE GUI",
    10: "EFI application",
    11: "EFI boot service driver",
    12: "EFI runtime driver",
    14: "Xbox",
}


def _file_extension(name: str) -> str:
    lower_name = str(name or "").lower()
    if lower_name.endswith(".tar.gz"):
        return ".tar.gz"
    dot_index = lower_name.rfind(".")
    return lower_name[dot_index:] if dot_index >= 0 else ""


def _safe_display_name(name: str, fallback: str = "uploaded-file") -> str:
    normalized = str(name or fallback).replace("\\", "/").split("/")[-1].strip()
    return normalized[:160] or fallback


def format_uploaded_file_display_text(
    input_text: str,
    files: Optional[List[Dict[str, Any]]],
) -> str:
    """Build the user-visible message without exposing internal file analysis."""
    base_text = str(input_text or "").strip()
    if not files:
        return base_text

    file_names = [
        _safe_display_name(file.get("name") or f"file-{index}", f"file-{index}")
        for index, file in enumerate(files, start=1)
        if isinstance(file, dict)
    ]
    if not file_names:
        return base_text

    attachment_text = "附件：" + "、".join(file_names)
    return "\n".join(part for part in [base_text, attachment_text] if part)


def _format_byte_size(size: int) -> str:
    value = max(0, int(size or 0))
    if value >= 1024 * 1024:
        return f"{value / 1024 / 1024:.2f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value} B"


def _truncate_text(text: str, limit: int) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    normalized = normalized.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "\n...[truncated]"


def _text_control_ratio(text: str) -> float:
    sample = str(text or "")[:4000]
    if not sample:
        return 0.0
    controls = sum(1 for char in sample if ord(char) < 32 and char not in "\n\r\t")
    return controls / max(1, len(sample))


def _decode_text_bytes(raw_bytes: bytes) -> tuple[bool, str, str]:
    if not raw_bytes:
        return True, "", "empty"

    sample = raw_bytes[:4096]
    encodings = ["utf-8-sig", "utf-16", "cp950", "gb18030", "shift_jis"]
    if len(sample) >= 8:
        odd_nulls = sum(1 for index in range(1, len(sample), 2) if sample[index] == 0)
        even_nulls = sum(1 for index in range(0, len(sample), 2) if sample[index] == 0)
        half_len = max(1, len(sample) // 2)
        if odd_nulls / half_len > 0.35 and even_nulls / half_len < 0.1:
            encodings.insert(0, "utf-16-le")

    for encoding in encodings:
        try:
            text = raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
        if _text_control_ratio(text) <= 0.08:
            return True, text, encoding

    printable_bytes = sum(
        1 for byte in sample if byte in (9, 10, 13) or 32 <= byte <= 126 or byte >= 128
    )
    if printable_bytes / max(1, len(sample)) >= 0.88:
        text = raw_bytes.decode("utf-8", errors="replace")
        return _text_control_ratio(text) <= 0.08, text, "utf-8-replace"

    return False, "", "binary"


def _classify_uploaded_file(
    file: Dict[str, Any],
    name: str,
    mime_type: str,
    raw_bytes: bytes,
) -> str:
    normalized_mime = str(mime_type or "").strip().lower()
    extension = _file_extension(name)
    if normalized_mime.startswith("image/"):
        return "image"
    if normalized_mime.startswith("audio/"):
        return "audio"
    if extension in CODE_ATTACHMENT_EXTENSIONS:
        return "code"
    if extension in TEXT_ATTACHMENT_EXTENSIONS or normalized_mime.startswith("text/"):
        return "text"
    if extension in ARCHIVE_ATTACHMENT_EXTENSIONS or normalized_mime in ARCHIVE_ATTACHMENT_MIME_TYPES:
        return "archive"
    if extension in BINARY_ATTACHMENT_EXTENSIONS or normalized_mime in BINARY_ATTACHMENT_MIME_TYPES:
        return "binary"
    if normalized_mime in {"application/json", "application/xml", "application/x-yaml", "application/toml"}:
        return "text"
    if raw_bytes.startswith(b"MZ") or raw_bytes.startswith(b"\x7fELF"):
        return "binary"

    explicit_kind = str(file.get("kind") or "").strip().lower()
    if explicit_kind in {"image", "audio", "text", "code", "archive", "binary"}:
        return explicit_kind

    is_text, _, _ = _decode_text_bytes(raw_bytes[: min(len(raw_bytes), MAX_ARCHIVE_MEMBER_BYTES)])
    return "text" if is_text else "binary"


def _is_audio_upload(file: Dict[str, Any]) -> bool:
    kind = str(file.get("kind") or "").strip().lower()
    mime_type = str(file.get("mime_type") or file.get("type") or "").strip().lower()
    return kind == "audio" or mime_type.startswith("audio/")


def _summarize_text_attachment(
    name: str,
    raw_bytes: bytes,
    kind: str,
    max_chars: int = MAX_TEXT_ATTACHMENT_CHARS,
) -> str:
    is_text, text, encoding = _decode_text_bytes(raw_bytes)
    header = [
        f"[File: {name}]",
        f"- kind: {kind}",
        f"- size: {_format_byte_size(len(raw_bytes))}",
    ]
    if not is_text:
        header.append("- result: binary-looking content; static binary summary is safer")
        return "\n".join(header)

    excerpt = _truncate_text(text, max_chars)
    line_count = text.count("\n") + (1 if text else 0)
    header.extend(
        [
            f"- encoding: {encoding}",
            f"- lines: {line_count}",
            "- excerpt:",
            excerpt or "[empty file]",
        ]
    )
    return "\n".join(header)


def _is_safe_archive_member(name: str) -> bool:
    normalized = str(name or "").replace("\\", "/")
    if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return False
    return all(part not in {"", ".", ".."} for part in normalized.split("/"))


def _archive_member_kind(name: str, raw_bytes: bytes) -> str:
    extension = _file_extension(name)
    if extension in CODE_ATTACHMENT_EXTENSIONS:
        return "code"
    if extension in TEXT_ATTACHMENT_EXTENSIONS:
        return "text"
    is_text, _, _ = _decode_text_bytes(raw_bytes)
    return "text" if is_text else "binary"


def _sample_archive_member_text(name: str, raw_bytes: bytes) -> Optional[str]:
    kind = _archive_member_kind(name, raw_bytes)
    if kind not in {"text", "code"}:
        return None
    is_text, text, encoding = _decode_text_bytes(raw_bytes)
    if not is_text:
        return None
    return "\n".join(
        [
            f"[Archive text sample: {name}]",
            f"- kind: {kind}",
            f"- encoding: {encoding}",
            "- excerpt:",
            _truncate_text(text, MAX_ARCHIVE_MEMBER_TEXT_CHARS) or "[empty file]",
        ]
    )


def _summarize_zip_archive(name: str, raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        entries = archive.infolist()
        entry_lines: List[str] = []
        text_samples: List[str] = []

        for info in entries[:MAX_ARCHIVE_ENTRIES]:
            suffix = "/" if info.is_dir() else ""
            entry_lines.append(f"  - {info.filename}{suffix} ({_format_byte_size(info.file_size)})")

        for info in entries:
            if len(text_samples) >= MAX_ARCHIVE_TEXT_FILES:
                break
            if info.is_dir() or not _is_safe_archive_member(info.filename):
                continue
            if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                continue
            try:
                with archive.open(info) as member:
                    member_bytes = member.read(MAX_ARCHIVE_MEMBER_BYTES + 1)
            except Exception:
                continue
            if len(member_bytes) > MAX_ARCHIVE_MEMBER_BYTES:
                continue
            sample = _sample_archive_member_text(info.filename, member_bytes)
            if sample:
                text_samples.append(sample)

    lines = [
        f"[Archive: {name}]",
        "- type: zip",
        f"- size: {_format_byte_size(len(raw_bytes))}",
        f"- entries: {len(entries)}",
        "- entry list:",
        *(entry_lines or ["  [empty archive]"]),
    ]
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        lines.append(f"  ...{len(entries) - MAX_ARCHIVE_ENTRIES} more entries")
    if text_samples:
        lines.extend(["- extracted text samples:", *text_samples])
    return "\n".join(lines)


def _summarize_tar_archive(name: str, raw_bytes: bytes) -> str:
    with tarfile.open(fileobj=io.BytesIO(raw_bytes), mode="r:*") as archive:
        members = archive.getmembers()
        entry_lines: List[str] = []
        text_samples: List[str] = []

        for member in members[:MAX_ARCHIVE_ENTRIES]:
            suffix = "/" if member.isdir() else ""
            entry_lines.append(f"  - {member.name}{suffix} ({_format_byte_size(member.size)})")

        for member in members:
            if len(text_samples) >= MAX_ARCHIVE_TEXT_FILES:
                break
            if not member.isfile() or not _is_safe_archive_member(member.name):
                continue
            if member.size > MAX_ARCHIVE_MEMBER_BYTES:
                continue
            try:
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                member_bytes = extracted.read(MAX_ARCHIVE_MEMBER_BYTES + 1)
            except Exception:
                continue
            if len(member_bytes) > MAX_ARCHIVE_MEMBER_BYTES:
                continue
            sample = _sample_archive_member_text(member.name, member_bytes)
            if sample:
                text_samples.append(sample)

    lines = [
        f"[Archive: {name}]",
        "- type: tar",
        f"- size: {_format_byte_size(len(raw_bytes))}",
        f"- entries: {len(members)}",
        "- entry list:",
        *(entry_lines or ["  [empty archive]"]),
    ]
    if len(members) > MAX_ARCHIVE_ENTRIES:
        lines.append(f"  ...{len(members) - MAX_ARCHIVE_ENTRIES} more entries")
    if text_samples:
        lines.extend(["- extracted text samples:", *text_samples])
    return "\n".join(lines)


def _summarize_gzip_member(name: str, raw_bytes: bytes) -> str:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes)) as archive:
            member_bytes = archive.read(MAX_ARCHIVE_MEMBER_BYTES + 1)
    except Exception as exc:
        return "\n".join(
            [
                f"[Archive: {name}]",
                "- type: gzip",
                f"- size: {_format_byte_size(len(raw_bytes))}",
                f"- result: unable to inspect gzip payload ({exc})",
            ]
        )

    truncated = len(member_bytes) > MAX_ARCHIVE_MEMBER_BYTES
    if truncated:
        member_bytes = member_bytes[:MAX_ARCHIVE_MEMBER_BYTES]
    inner_name = name[:-3] if name.lower().endswith(".gz") else f"{name}.content"
    sample = _sample_archive_member_text(inner_name, member_bytes)
    lines = [
        f"[Archive: {name}]",
        "- type: gzip",
        f"- compressed size: {_format_byte_size(len(raw_bytes))}",
        f"- sampled payload size: {_format_byte_size(len(member_bytes))}",
    ]
    if truncated:
        lines.append("- note: payload sample was truncated")
    if sample:
        lines.extend(["- extracted text sample:", sample])
    else:
        lines.append("- result: payload is not readable text in the sampled range")
    return "\n".join(lines)


def _summarize_archive_attachment(name: str, raw_bytes: bytes) -> str:
    try:
        if zipfile.is_zipfile(io.BytesIO(raw_bytes)):
            return _summarize_zip_archive(name, raw_bytes)
    except Exception:
        pass

    try:
        return _summarize_tar_archive(name, raw_bytes)
    except tarfile.TarError:
        if _file_extension(name) == ".gz":
            return _summarize_gzip_member(name, raw_bytes)
    except Exception as exc:
        logger.warning(f"Archive attachment analysis failed for {name}: {exc}")

    return "\n".join(
        [
            f"[Archive: {name}]",
            f"- size: {_format_byte_size(len(raw_bytes))}",
            "- result: unsupported or damaged archive; no files were extracted",
        ]
    )


def _unpack_from(fmt: str, raw_bytes: bytes, offset: int) -> tuple:
    size = struct.calcsize(fmt)
    if offset < 0 or offset + size > len(raw_bytes):
        raise ValueError("offset out of range")
    return struct.unpack_from(fmt, raw_bytes, offset)


def _read_c_string(raw_bytes: bytes, offset: int, max_len: int = 512) -> str:
    if offset < 0 or offset >= len(raw_bytes):
        return ""
    end = min(len(raw_bytes), offset + max_len)
    zero_index = raw_bytes.find(b"\x00", offset, end)
    if zero_index >= 0:
        end = zero_index
    return raw_bytes[offset:end].decode("ascii", errors="replace").strip()


def _pe_rva_to_offset(sections: List[Dict[str, int]], rva: int, size_of_headers: int) -> Optional[int]:
    if 0 <= rva < size_of_headers:
        return rva
    for section in sections:
        start = int(section.get("virtual_address") or 0)
        span = max(int(section.get("virtual_size") or 0), int(section.get("raw_size") or 0))
        if start <= rva < start + span:
            offset = int(section.get("raw_pointer") or 0) + (rva - start)
            return offset if 0 <= offset < 2**31 else None
    return None


def _parse_pe_imports(
    raw_bytes: bytes,
    sections: List[Dict[str, int]],
    import_rva: int,
    size_of_headers: int,
    is_pe64: bool,
) -> Dict[str, List[str]]:
    imports: Dict[str, List[str]] = {}
    if not import_rva:
        return imports

    descriptor_offset = _pe_rva_to_offset(sections, import_rva, size_of_headers)
    if descriptor_offset is None:
        return imports

    thunk_size = 8 if is_pe64 else 4
    ordinal_mask = 0x8000000000000000 if is_pe64 else 0x80000000

    for descriptor_index in range(64):
        offset = descriptor_offset + descriptor_index * 20
        try:
            original_thunk, _, _, name_rva, first_thunk = _unpack_from("<IIIII", raw_bytes, offset)
        except ValueError:
            break
        if not any([original_thunk, name_rva, first_thunk]):
            break

        name_offset = _pe_rva_to_offset(sections, name_rva, size_of_headers)
        dll_name = _read_c_string(raw_bytes, name_offset or -1, 256) or f"dll_{descriptor_index}"
        thunk_rva = original_thunk or first_thunk
        thunk_offset = _pe_rva_to_offset(sections, thunk_rva, size_of_headers)
        functions: List[str] = []
        if thunk_offset is not None:
            for function_index in range(80):
                try:
                    if is_pe64:
                        (thunk_value,) = _unpack_from("<Q", raw_bytes, thunk_offset + function_index * thunk_size)
                    else:
                        (thunk_value,) = _unpack_from("<I", raw_bytes, thunk_offset + function_index * thunk_size)
                except ValueError:
                    break
                if thunk_value == 0:
                    break
                if thunk_value & ordinal_mask:
                    functions.append(f"ordinal:{thunk_value & 0xFFFF}")
                    continue
                hint_name_offset = _pe_rva_to_offset(sections, int(thunk_value), size_of_headers)
                function_name = _read_c_string(raw_bytes, (hint_name_offset or -2) + 2, 256)
                if function_name:
                    functions.append(function_name)
                if len(functions) >= 40:
                    break
        imports[dll_name] = functions
    return imports


def _parse_pe_summary(raw_bytes: bytes) -> List[str]:
    try:
        if len(raw_bytes) < 0x40 or raw_bytes[:2] != b"MZ":
            return []
        (pe_offset,) = _unpack_from("<I", raw_bytes, 0x3C)
        if pe_offset <= 0 or raw_bytes[pe_offset : pe_offset + 4] != b"PE\x00\x00":
            return ["- PE: invalid PE signature"]

        coff_offset = pe_offset + 4
        machine, section_count, timestamp, _, _, optional_size, characteristics = _unpack_from(
            "<HHIIIHH", raw_bytes, coff_offset
        )
        optional_offset = coff_offset + 20
        (magic,) = _unpack_from("<H", raw_bytes, optional_offset)
        is_pe64 = magic == 0x20B
        pe_format = "PE32+" if is_pe64 else "PE32" if magic == 0x10B else f"unknown optional magic 0x{magic:X}"
        (entry_point_rva,) = _unpack_from("<I", raw_bytes, optional_offset + 16)
        if is_pe64:
            (image_base,) = _unpack_from("<Q", raw_bytes, optional_offset + 24)
            data_directory_offset = optional_offset + 112
        else:
            (image_base,) = _unpack_from("<I", raw_bytes, optional_offset + 28)
            data_directory_offset = optional_offset + 96
        (size_of_headers,) = _unpack_from("<I", raw_bytes, optional_offset + 60)
        (subsystem,) = _unpack_from("<H", raw_bytes, optional_offset + 68)
        import_rva, import_size = _unpack_from("<II", raw_bytes, data_directory_offset + 8)

        sections: List[Dict[str, int]] = []
        section_offset = optional_offset + optional_size
        for index in range(section_count):
            current_offset = section_offset + index * 40
            (
                raw_name,
                virtual_size,
                virtual_address,
                raw_size,
                raw_pointer,
                _,
                _,
                _,
                _,
                section_characteristics,
            ) = _unpack_from("<8sIIIIIIHHI", raw_bytes, current_offset)
            section_name = raw_name.split(b"\x00", 1)[0].decode("ascii", errors="replace") or f"section_{index}"
            sections.append(
                {
                    "name": section_name,
                    "virtual_size": int(virtual_size),
                    "virtual_address": int(virtual_address),
                    "raw_size": int(raw_size),
                    "raw_pointer": int(raw_pointer),
                    "characteristics": int(section_characteristics),
                }
            )

        timestamp_text = "unknown"
        if timestamp:
            try:
                timestamp_text = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            except Exception:
                timestamp_text = f"raw:{timestamp}"

        lines = [
            f"- PE: {pe_format} {PE_MACHINE_TYPES.get(machine, hex(machine))}",
            f"- subsystem: {PE_SUBSYSTEM_TYPES.get(subsystem, str(subsystem))}",
            f"- timestamp: {timestamp_text}",
            f"- characteristics: 0x{characteristics:04X}",
            f"- entry point RVA: 0x{entry_point_rva:X}",
            f"- image base: 0x{image_base:X}",
            f"- sections: {section_count}",
        ]

        for section in sections[:12]:
            lines.append(
                "  - "
                f"{section['name']}: "
                f"VA 0x{section['virtual_address']:X}, "
                f"VSZ {_format_byte_size(section['virtual_size'])}, "
                f"RAW {_format_byte_size(section['raw_size'])}"
            )
        if section_count > 12:
            lines.append(f"  ...{section_count - 12} more sections")

        imports = _parse_pe_imports(raw_bytes, sections, import_rva, size_of_headers, is_pe64)
        if imports:
            lines.append(f"- import table: RVA 0x{import_rva:X}, size {_format_byte_size(import_size)}")
            for dll_name, functions in list(imports.items())[:18]:
                preview = ", ".join(functions[:18]) if functions else "[names unavailable]"
                if len(functions) > 18:
                    preview += f", ...{len(functions) - 18} more"
                lines.append(f"  - {dll_name}: {preview}")
            if len(imports) > 18:
                lines.append(f"  ...{len(imports) - 18} more DLLs")
        else:
            lines.append("- import table: not found or not parseable")
        return lines
    except Exception as exc:
        logger.warning(f"PE static analysis failed: {exc}")
        return ["- PE: parse failed"]


def _extract_printable_strings(raw_bytes: bytes) -> List[str]:
    sample = raw_bytes[:MAX_BINARY_STRING_SCAN_BYTES]
    candidates: List[str] = []
    for match in re.finditer(rb"[ -~]{4,}", sample):
        candidates.append(match.group(0).decode("ascii", errors="replace"))
    for match in re.finditer(rb"(?:[\x20-\x7E]\x00){4,}", sample):
        try:
            candidates.append(match.group(0).decode("utf-16-le", errors="replace"))
        except Exception:
            continue

    interesting_pattern = re.compile(
        r"(https?://|www\.|\.dll\b|\.exe\b|\.bat\b|\.ps1\b|cmd\.exe|powershell|"
        r"CreateProcess|LoadLibrary|GetProcAddress|Reg(Open|Set|Query)|HKEY_|HKLM|HKCU|"
        r"Software\\|AppData|Temp\\|C:\\|/bin/|/usr/)",
        re.IGNORECASE,
    )
    seen = set()
    interesting: List[str] = []
    fallback: List[str] = []
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate).strip()
        if len(cleaned) < 4 or cleaned in seen:
            continue
        seen.add(cleaned)
        target = interesting if interesting_pattern.search(cleaned) else fallback
        target.append(cleaned[:240])
        if len(interesting) >= MAX_BINARY_STRINGS:
            break

    result = interesting[:MAX_BINARY_STRINGS]
    if len(result) < min(30, MAX_BINARY_STRINGS):
        result.extend(fallback[: min(30, MAX_BINARY_STRINGS) - len(result)])
    return result[:MAX_BINARY_STRINGS]


def _summarize_binary_attachment(name: str, raw_bytes: bytes, mime_type: str) -> str:
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    md5 = hashlib.md5(raw_bytes).hexdigest()
    magic = raw_bytes[:16].hex(" ")
    lines = [
        f"[Binary: {name}]",
        "- analysis: static only; the file was not executed",
        f"- mime: {mime_type or 'unknown'}",
        f"- size: {_format_byte_size(len(raw_bytes))}",
        f"- sha256: {sha256}",
        f"- md5: {md5}",
        f"- magic bytes: {magic or '[empty]'}",
    ]

    if raw_bytes.startswith(b"MZ"):
        lines.extend(_parse_pe_summary(raw_bytes))
    elif raw_bytes.startswith(b"\x7fELF"):
        lines.append("- format: ELF executable or shared object")

    strings = _extract_printable_strings(raw_bytes)
    if strings:
        lines.append("- notable strings:")
        lines.extend(f"  - {text}" for text in strings)
    else:
        lines.append("- notable strings: none found in sampled bytes")
    return "\n".join(lines)


async def transcribe_audio_files(
    files: Optional[List[Dict[str, Any]]],
    asr_engine: Optional[ASRInterface],
) -> List[str]:
    if not files or asr_engine is None:
        return []

    notes: List[str] = []
    audio_items = [
        file
        for file in files
        if isinstance(file, dict) and _is_audio_upload(file)
    ][:3]

    for index, file in enumerate(audio_items, start=1):
        name = str(file.get("name") or f"audio-{index}").strip() or f"audio-{index}"
        mime_hint = str(file.get("mime_type") or file.get("type") or "").strip()
        mime_type, raw_bytes = _decode_data_url(str(file.get("data") or ""))
        mime_type = mime_type or mime_hint
        if not raw_bytes:
            notes.append(f"- {name}: [音檔讀取失敗，沒有可用資料]")
            continue

        audio = _audio_bytes_to_float32(raw_bytes, mime_type)
        if audio.size == 0:
            notes.append(f"- {name}: [音檔格式暫時無法解析，建議使用 WAV/MP3]")
            continue

        try:
            text = (await asr_engine.async_transcribe_np(audio)).strip()
        except Exception as exc:
            logger.warning(f"Audio attachment transcription failed for {name}: {exc}")
            text = ""

        if text:
            notes.append(f"- {name}: {text}")
        else:
            notes.append(f"- {name}: [未辨識到清楚語音]")
    return notes


async def summarize_uploaded_files(
    files: Optional[List[Dict[str, Any]]],
    asr_engine: Optional[ASRInterface],
) -> List[str]:
    if not files:
        return []

    notes: List[str] = []
    audio_files = [file for file in files if isinstance(file, dict) and _is_audio_upload(file)]
    audio_notes = await transcribe_audio_files(files, asr_engine)
    if audio_notes:
        notes.append("[Audio file transcription]\n" + "\n".join(audio_notes))
    elif audio_files and asr_engine is None:
        names = ", ".join(_safe_display_name(file.get("name") or "audio") for file in audio_files[:3])
        notes.append(f"[Audio file transcription]\n- {names}: ASR engine is not available.")

    for index, file in enumerate(files, start=1):
        if not isinstance(file, dict) or _is_audio_upload(file):
            continue

        name = _safe_display_name(file.get("name") or f"file-{index}", f"file-{index}")
        mime_hint = str(file.get("mime_type") or file.get("type") or "").strip().lower()
        data_mime, raw_bytes = _decode_data_url(str(file.get("data") or ""))
        mime_type = mime_hint or data_mime
        if not raw_bytes:
            notes.append(
                "\n".join(
                    [
                        f"[File: {name}]",
                        f"- mime: {mime_type or 'unknown'}",
                        "- result: file payload could not be decoded",
                    ]
                )
            )
            continue

        kind = _classify_uploaded_file(file, name, mime_type, raw_bytes)
        if kind == "image":
            continue
        if kind in {"text", "code"}:
            notes.append(_summarize_text_attachment(name, raw_bytes, kind))
        elif kind == "archive":
            notes.append(_summarize_archive_attachment(name, raw_bytes))
        else:
            notes.append(_summarize_binary_attachment(name, raw_bytes, mime_type))

    return notes


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
