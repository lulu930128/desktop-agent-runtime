import os

import chardet
from loguru import logger

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
PROMPT_DIR = CURRENT_DIR
PERSONA_PROMPT_DIR = os.path.join(PROMPT_DIR, "persona")
UTIL_PROMPT_DIR = os.path.join(PROMPT_DIR, "utils")


def _load_file_content(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii"]
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError:
            continue

    try:
        with open(file_path, "rb") as handle:
            raw_data = handle.read()
        detected = chardet.detect(raw_data)
        detected_encoding = detected["encoding"]
        if detected_encoding:
            return raw_data.decode(detected_encoding)
    except Exception as exc:
        logger.error(f"Error detecting encoding for {file_path}: {exc}")

    raise UnicodeError(f"Failed to decode {file_path} with any encoding")


def _resolve_path(path_value: str) -> str:
    path_value = (path_value or "").strip()
    if not path_value:
        raise ValueError("Prompt path cannot be empty")
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(ROOT_DIR, path_value)


def load_path(path_value: str) -> str:
    try:
        return _load_file_content(_resolve_path(path_value))
    except Exception as exc:
        logger.error(f"Error loading prompt path {path_value}: {exc}")
        raise


def load_persona(persona_name: str) -> str:
    persona_file_path = os.path.join(PERSONA_PROMPT_DIR, f"{persona_name}.txt")
    try:
        return _load_file_content(persona_file_path)
    except Exception as exc:
        logger.error(f"Error loading persona {persona_name}: {exc}")
        raise


def load_util(util_name: str) -> str:
    util_file_path = os.path.join(UTIL_PROMPT_DIR, f"{util_name}.txt")
    try:
        return _load_file_content(util_file_path)
    except Exception as exc:
        logger.error(f"Error loading util {util_name}: {exc}")
        raise
