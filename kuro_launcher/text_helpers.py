import datetime
import json
from pathlib import Path
from typing import Optional


def resolve_repo_path(repo_root: Path, raw_path: str) -> Optional[Path]:
    raw_path = (raw_path or "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (repo_root / candidate).resolve()


def read_text_maybe(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return ""
    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "cp936", "ascii"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def pretty_path(path: Optional[Path], root: Path) -> str:
    if path is None:
        return "(未設定)"
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except Exception:
        return str(path)


def normalize_token(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def compact_history_text(content: str, max_len: int = 72) -> str:
    if not isinstance(content, str):
        return ""
    compact = " ".join(content.replace("\r", " ").replace("\n", " ").split())
    compact = compact.strip(" \t\r\n\"'`")
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip(" .,!?;:") + "..."


def derive_history_title(content: str) -> str:
    return compact_history_text(content, max_len=28)


def format_history_timestamp(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(raw)
        return dt.strftime("%m/%d %H:%M")
    except ValueError:
        return raw[:16]


def is_assistant_history_role(role: str) -> bool:
    return (role or "").strip().lower() in {"ai", "assistant"}


def history_event_detail(event: dict) -> dict:
    detail = event.get("detail")
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str) and detail.strip():
        try:
            parsed = json.loads(detail)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def history_tool_name(event: dict) -> str:
    detail = history_event_detail(event)
    tool_name = str(detail.get("tool_name") or "").strip()
    if tool_name:
        return tool_name

    title = str(event.get("title") or "").strip()
    for prefix in ("工具：", "工具:", "Tool：", "Tool:"):
        if title.startswith(prefix):
            tool_name = title[len(prefix) :].strip()
            if tool_name:
                return tool_name

    summary = str(event.get("summary") or "").strip()
    if summary:
        first = summary.split()[0].strip("：:，,")
        if first:
            return first
    return "tool"


def format_history_tool_event_inline(event: dict) -> str:
    status = str(event.get("status") or "").strip().lower()
    tool_name = history_tool_name(event)
    tool_key = tool_name.lower()
    is_search_tool = (
        "search" in tool_key
        or tool_key in {"smart_search_web", "search_web", "fetch_content"}
    )
    subject = "搜尋" if is_search_tool else "工具"
    status_text = {
        "completed": "完成",
        "ok": "完成",
        "error": "錯誤",
        "blocked": "被擋下",
        "skipped": "略過",
    }.get(status, status or "狀態")
    return f"{subject}{status_text} · {tool_name}"


def format_history_tool_events_inline(events: list[dict]) -> str:
    labels = [
        format_history_tool_event_inline(event)
        for event in events
        if isinstance(event, dict)
    ]
    return "　".join(label for label in labels if label)
