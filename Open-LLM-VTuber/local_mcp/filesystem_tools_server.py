from __future__ import annotations

import string
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Iterable

from mcp.server.fastmcp import FastMCP


REPO_ROOT = Path(__file__).resolve().parents[2]
OPEN_LLM_ROOT = Path(__file__).resolve().parents[1]
OPEN_LLM_SRC = OPEN_LLM_ROOT / "src"
if str(OPEN_LLM_SRC) not in sys.path:
    sys.path.insert(0, str(OPEN_LLM_SRC))

try:
    from open_llm_vtuber.conversation_history_index import (
        search_past_conversations as _search_past_conversations,
    )
except Exception:
    _search_past_conversations = None
DEFAULT_ROOTS: dict[str, Path] = {
    "workspace": REPO_ROOT,
    "open_llm": OPEN_LLM_ROOT,
    "projects": REPO_ROOT / "projects",
    "characters": OPEN_LLM_ROOT / "characters",
    "prompts": REPO_ROOT / "projects",
}
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".css",
    ".scss",
    ".toml",
    ".ini",
    ".cfg",
    ".xml",
    ".csv",
    ".log",
    ".bat",
    ".ps1",
    ".vbs",
    ".sh",
}

mcp = FastMCP("kuro-filesystem")


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def _iter_allowed_roots() -> Iterable[tuple[str, Path]]:
    yielded: set[str] = set()

    for alias, path in DEFAULT_ROOTS.items():
        if path.exists():
            resolved = path.resolve()
            yielded.add(str(resolved).lower())
            yield alias, resolved

    for drive_letter in string.ascii_uppercase:
        drive_root = Path(f"{drive_letter}:/")
        if not drive_root.exists():
            continue
        resolved = drive_root.resolve()
        normalized = str(resolved).lower()
        if normalized in yielded:
            continue
        yield f"drive_{drive_letter.lower()}", resolved


def _matches_windows_abs(raw_path: str) -> bool:
    if len(raw_path) < 3:
        return False
    return raw_path[1] == ":" and raw_path[2] in ("\\", "/")


def _resolve_input_path(raw_path: str) -> tuple[Path, str]:
    raw_path = (raw_path or "").strip()
    root_map = {alias: path for alias, path in _iter_allowed_roots()}

    if not raw_path:
        return root_map["workspace"], "workspace"

    if not _matches_windows_abs(raw_path) and ":" in raw_path:
        alias, rest = raw_path.split(":", 1)
        alias = alias.strip()
        if alias in root_map:
            return (root_map[alias] / rest.lstrip("\\/")).resolve(), alias

    path = Path(raw_path)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (root_map["workspace"] / path).resolve()

    for alias, root in root_map.items():
        if resolved == root or resolved.is_relative_to(root):
            return resolved, alias

    raise ValueError(
        "Path is outside allowed read-only roots. "
        "Use list_allowed_roots to see what this tool can access."
    )


def _display_path(path: Path) -> str:
    try:
        return path.resolve().as_posix()
    except Exception:
        return str(path)


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def _format_dir_entry(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix() if path != root else "."
    if path.is_dir():
        return f"[DIR]  {relative}"
    size = path.stat().st_size if path.exists() else 0
    return f"[FILE] {relative} ({size} bytes)"


def _looks_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data:
        return True
    sample = data[:1024]
    text_bytes = sum(
        1
        for b in sample
        if b in (9, 10, 13) or 32 <= b <= 126 or b >= 128
    )
    return text_bytes / len(sample) < 0.75


def _read_text_with_fallback(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if _looks_binary(raw):
        raise ValueError("Binary file is not readable as text.")

    encodings = ["utf-8", "utf-8-sig", "cp950", "gb18030"]
    for encoding in encodings:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


@mcp.tool(
    name="list_allowed_roots",
    description="List the folders this read-only filesystem tool is allowed to access.",
)
def list_allowed_roots() -> str:
    lines = ["Allowed read-only roots:"]
    for alias, path in _iter_allowed_roots():
        lines.append(f"- {alias}: {_display_path(path)}")
    return "\n".join(lines)


@mcp.tool(
    name="list_directory",
    description=(
        "List files and folders inside an allowed directory. "
        "Supports alias paths like workspace:, open_llm:, projects:, characters:."
    ),
)
def list_directory(
    path: str = "",
    recursive: bool = False,
    max_entries: int = 200,
    include_hidden: bool = False,
) -> str:
    target, root_alias = _resolve_input_path(path)
    if not target.exists():
        return f"Directory error: path does not exist: {_display_path(target)}"
    if not target.is_dir():
        return f"Directory error: path is not a directory: {_display_path(target)}"

    max_entries = max(1, min(int(max_entries or 200), 500))
    items = target.rglob("*") if recursive else target.iterdir()
    rows: list[str] = []

    sorted_items = sorted(
        (item for item in items if include_hidden or not _is_hidden(item)),
        key=lambda p: (not p.is_dir(), p.as_posix().lower()),
    )
    for item in sorted_items[:max_entries]:
        rows.append(_format_dir_entry(target, item))

    lines = [
        f"Root alias: {root_alias}",
        f"Directory: {_display_path(target)}",
        f"Recursive: {recursive}",
        f"Returned entries: {len(rows)}",
        "",
    ]
    if rows:
        lines.extend(rows)
    else:
        lines.append("(empty)")

    if len(sorted_items) > max_entries:
        lines.append("")
        lines.append(f"... truncated at {max_entries} entries")
    return "\n".join(lines)


@mcp.tool(
    name="read_text_file",
    description=(
        "Read a text file from an allowed root. Returns file path, detected encoding, and truncated content."
    ),
)
def read_text_file(path: str, max_chars: int = 12000) -> str:
    target, root_alias = _resolve_input_path(path)
    if not target.exists():
        return f"Read error: file does not exist: {_display_path(target)}"
    if not target.is_file():
        return f"Read error: path is not a file: {_display_path(target)}"

    max_chars = max(200, min(int(max_chars or 12000), 50000))
    try:
        text, encoding = _read_text_with_fallback(target)
    except Exception as exc:
        return f"Read error: {exc}"

    trimmed = text[:max_chars]
    if len(text) > max_chars:
        trimmed += "\n... [truncated]"

    return "\n".join(
        [
            f"Root alias: {root_alias}",
            f"File: {_display_path(target)}",
            f"Encoding: {encoding}",
            f"Content:",
            trimmed,
        ]
    )


@mcp.tool(
    name="search_files",
    description=(
        "Search text inside files under an allowed root. "
        "Uses ripgrep when available and falls back to a slower Python scan."
    ),
)
def search_files(
    query: str,
    path: str = "",
    glob: str = "",
    max_results: int = 50,
) -> str:
    query = _normalize(query)
    if not query:
        return "Search error: query is empty."

    target, root_alias = _resolve_input_path(path)
    if not target.exists():
        return f"Search error: path does not exist: {_display_path(target)}"
    if not target.is_dir():
        return f"Search error: path is not a directory: {_display_path(target)}"

    max_results = max(1, min(int(max_results or 50), 200))
    rg = shutil.which("rg")
    if rg:
        cmd = [
            rg,
            "--line-number",
            "--with-filename",
            "--color",
            "never",
            "--smart-case",
            "--fixed-strings",
            "--max-count",
            "3",
            query,
            str(target),
        ]
        if glob.strip():
            cmd.extend(["--glob", glob.strip()])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            output = [line for line in result.stdout.splitlines() if line.strip()]
            if output:
                trimmed = output[:max_results]
                lines = [
                    f"Root alias: {root_alias}",
                    f"Search root: {_display_path(target)}",
                    f"Query: {query}",
                    "",
                ]
                lines.extend(trimmed)
                if len(output) > max_results:
                    lines.append("")
                    lines.append(f"... truncated at {max_results} results")
                return "\n".join(lines)
            if result.returncode in (0, 1):
                return (
                    f"Root alias: {root_alias}\n"
                    f"Search root: {_display_path(target)}\n"
                    f"Query: {query}\n\n"
                    "No matches found."
                )
        except Exception:
            pass

    matches: list[str] = []
    for file_path in sorted(target.rglob("*")):
        if not file_path.is_file():
            continue
        if _is_hidden(file_path):
            continue
        if glob.strip() and not file_path.match(glob.strip()):
            continue
        if file_path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text, _ = _read_text_with_fallback(file_path)
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if query.lower() in line.lower():
                rel = file_path.relative_to(target).as_posix()
                matches.append(f"{rel}:{lineno}: {line.strip()}")
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    lines = [
        f"Root alias: {root_alias}",
        f"Search root: {_display_path(target)}",
        f"Query: {query}",
        "",
    ]
    if matches:
        lines.extend(matches)
    else:
        lines.append("No matches found.")
    return "\n".join(lines)


@mcp.tool(
    name="search_past_conversations",
    description=(
        "Search raw snippets from previous chat histories for the same character. "
        "Use this when the user asks what was discussed before, wants a prior "
        "decision, or needs details that may not have been promoted to long-term memory."
    ),
)
def search_past_conversations(
    query: str,
    conf_uid: str,
    exclude_history_uid: str = "",
    max_results: int = 5,
) -> str:
    query = _normalize(query)
    conf_uid = _normalize(conf_uid)
    if not query:
        return "Past conversation search error: query is empty."
    if not conf_uid:
        return "Past conversation search error: conf_uid is required."
    if _search_past_conversations is None:
        return "Past conversation search error: conversation history index is unavailable."

    try:
        hits = _search_past_conversations(
            conf_uid,
            query,
            exclude_history_uid=exclude_history_uid,
            include_current_history=False,
            max_snippets=max(1, min(int(max_results or 5), 12)),
            token_budget=1200,
        )
    except Exception as exc:
        return f"Past conversation search error: {exc}"

    lines = [
        "Past conversation search results:",
        f"conf_uid: {conf_uid}",
        f"query: {query}",
        "",
    ]
    if not hits:
        lines.append("No matching previous conversation snippets found.")
        return "\n".join(lines)

    for index, hit in enumerate(hits, start=1):
        source = f"{hit.get('history_uid', '')}#{hit.get('message_index', '')}"
        timestamp = str(hit.get("timestamp") or "")
        role = str(hit.get("role") or "")
        title = str(hit.get("title") or "")
        content = _normalize(str(hit.get("content") or ""))
        lines.append(f"{index}. source={source} role={role} time={timestamp}")
        if title:
            lines.append(f"   title: {title}")
        lines.append(f"   snippet: {content}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
