from __future__ import annotations

import re
from typing import Any


PronunciationEntry = dict[str, Any]


def _as_clean_text(value: Any, max_len: int = 120) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len].strip()


def _add_entry(
    entries: list[PronunciationEntry],
    *,
    surface: Any,
    reading: Any,
    aliases: Any = None,
    category: Any = "",
    note: Any = "",
) -> None:
    clean_surface = _as_clean_text(surface)
    clean_reading = _as_clean_text(reading)
    if not clean_surface or not clean_reading:
        return
    if clean_surface == clean_reading:
        return

    clean_aliases: list[str] = []
    if isinstance(aliases, (list, tuple)):
        for alias in aliases:
            clean_alias = _as_clean_text(alias)
            if clean_alias and clean_alias != clean_surface:
                clean_aliases.append(clean_alias)

    entries.append(
        {
            "surface": clean_surface,
            "reading": clean_reading,
            "aliases": clean_aliases,
            "category": _as_clean_text(category, max_len=40),
            "note": _as_clean_text(note, max_len=160),
        }
    )


def normalize_pronunciation_entries(raw: Any) -> list[PronunciationEntry]:
    """Normalize pronunciation config into [{surface, reading, aliases, ...}]."""
    entries: list[PronunciationEntry] = []
    if not raw:
        return entries

    if isinstance(raw, dict):
        if "surface" in raw and "reading" in raw:
            _add_entry(
                entries,
                surface=raw.get("surface"),
                reading=raw.get("reading"),
                aliases=raw.get("aliases"),
                category=raw.get("category"),
                note=raw.get("note"),
            )
            return entries

        for key, value in raw.items():
            if key in {"version", "entries", "global", "characters", "projects"}:
                continue
            if isinstance(value, str):
                _add_entry(entries, surface=key, reading=value)
            elif isinstance(value, dict):
                _add_entry(
                    entries,
                    surface=value.get("surface") or key,
                    reading=value.get("reading"),
                    aliases=value.get("aliases"),
                    category=value.get("category"),
                    note=value.get("note"),
                )
        return entries

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                entries.extend(normalize_pronunciation_entries(item))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                _add_entry(entries, surface=item[0], reading=item[1])
        return entries

    return entries


def collect_pronunciation_entries(
    raw: Any,
    *,
    character_keys: list[str] | tuple[str, ...] = (),
    project_id: str = "",
) -> list[PronunciationEntry]:
    """Collect global + matching character/project pronunciation entries."""
    if not isinstance(raw, dict):
        return normalize_pronunciation_entries(raw)

    entries: list[PronunciationEntry] = []
    entries.extend(normalize_pronunciation_entries(raw.get("global")))
    entries.extend(normalize_pronunciation_entries(raw.get("entries")))

    normalized_character_keys = {str(key or "").strip().lower() for key in character_keys if str(key or "").strip()}
    characters = raw.get("characters")
    if isinstance(characters, dict):
        for key, value in characters.items():
            if str(key or "").strip().lower() in normalized_character_keys:
                entries.extend(normalize_pronunciation_entries(value))

    projects = raw.get("projects")
    clean_project_id = str(project_id or "").strip()
    if isinstance(projects, dict) and clean_project_id:
        entries.extend(normalize_pronunciation_entries(projects.get(clean_project_id)))

    return entries


def merge_pronunciation_entries(*entry_groups: list[PronunciationEntry]) -> list[PronunciationEntry]:
    merged: list[PronunciationEntry] = []
    seen: set[str] = set()
    for group in entry_groups:
        for entry in normalize_pronunciation_entries(group):
            surface = _as_clean_text(entry.get("surface"))
            reading = _as_clean_text(entry.get("reading"))
            if not surface or not reading:
                continue
            key = surface.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return merged


def _iter_surfaces(entry: PronunciationEntry) -> list[str]:
    surfaces = [_as_clean_text(entry.get("surface"))]
    aliases = entry.get("aliases")
    if isinstance(aliases, list):
        surfaces.extend(_as_clean_text(alias) for alias in aliases)
    return [surface for surface in surfaces if surface]


def _surface_pattern(surface: str) -> re.Pattern:
    escaped = re.escape(surface)
    if re.fullmatch(r"[A-Za-z0-9_.+\-#/]+", surface):
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)
    return re.compile(escaped)


def contains_pronunciation_surface(text: str, entries: list[PronunciationEntry] | None) -> bool:
    if not text or not entries:
        return False
    return any(_surface_pattern(surface).search(text) for entry in entries for surface in _iter_surfaces(entry))


def apply_pronunciation(
    text: str,
    entries: list[PronunciationEntry] | None,
) -> tuple[str, list[str]]:
    """Apply known readings to final TTS text and return hit surfaces."""
    if not text or not entries:
        return text or "", []

    result = str(text)
    hits: list[str] = []
    replacements: list[tuple[str, str]] = []
    for entry in entries:
        reading = _as_clean_text(entry.get("reading"))
        if not reading:
            continue
        for surface in _iter_surfaces(entry):
            if surface and surface != reading:
                replacements.append((surface, reading))

    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    for surface, reading in replacements:
        pattern = _surface_pattern(surface)
        result, count = pattern.subn(reading, result)
        if count:
            hits.append(surface)

    return result, hits


def format_pronunciation_prompt(entries: list[PronunciationEntry] | None, max_entries: int = 40) -> str:
    if not entries:
        return ""
    lines: list[str] = []
    for entry in entries[:max_entries]:
        surface = _as_clean_text(entry.get("surface"))
        reading = _as_clean_text(entry.get("reading"))
        if surface and reading:
            lines.append(f"- {surface} => {reading}")
    return "\n".join(lines)
