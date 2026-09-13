"""Safe copies for evidence consumers; never use these to send tool arguments."""
import json
import re

REDACTED = "[redacted]"
_KEY = re.compile(r"^(?:authorization|cookie|set-cookie|password|passwd|pwd|secret|api[-_]?key|access[-_]?token|refresh[-_]?token|id[-_]?token|token|code[-_]?verifier|client[-_]?secret|signed[-_]?url)$", re.I)
_TEXT = re.compile(r"(?:\b(?:authorization|cookie|token|access[_-]?token|refresh[_-]?token|api[_-]?key|password|client[_-]?secret|code[_-]?verifier)\b[\"']?\s*[=:]|[?&](?:code|state|token|sig|signature|key)=|\bBearer\s+|\bsk-[A-Za-z0-9_-]{12,})", re.I)
_MASKED_FIELD = re.compile(r'''["']?(?:authorization|cookie|token|access[_-]?token|refresh[_-]?token|api[_-]?key|password|client[_-]?secret|code[_-]?verifier)["']?\s*[=:]\s*["']\[redacted\]["']''', re.I)


def secret_values(value, depth=0) -> set[str]:
    if depth > 32:
        return set()
    if isinstance(value, dict):
        found = set()
        for key, item in value.items():
            if (_KEY.match(str(key)) or ({"code", "state"} <= value.keys() and key in {"code", "state"})) and isinstance(item, str) and item:
                found.add(item)
            found.update(secret_values(item, depth+1))
        return found
    if isinstance(value, list):
        return set().union(*(secret_values(item, depth+1) for item in value))
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return secret_values(decoded, depth+1) if not isinstance(decoded, str) else set()
        except (ValueError, TypeError, RecursionError):
            return set()
    return set()


def project(value, *, secrets=(), depth=0):
    if depth > 32:
        return "[depth limit]"
    if isinstance(value, dict):
        return {str(k): REDACTED if (_KEY.match(str(k)) or ({"code", "state"} <= value.keys() and k in {"code", "state"})) and isinstance(v, str) else
                project(v, secrets=secrets, depth=depth+1) for k, v in value.items() if k not in {"_meta", "metadata"}}
    if isinstance(value, (list, tuple)):
        return [project(v, secrets=secrets, depth=depth+1) for v in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError, RecursionError):
            decoded = None
        if isinstance(decoded, (dict, list)):
            return json.dumps(project(decoded, secrets=secrets, depth=depth+1), ensure_ascii=False)
        # A second projection must preserve already-redacted structured blocks.
        # Only exact quoted placeholders are excluded from detection.
        if _TEXT.search(_MASKED_FIELD.sub("", value)):
            return "[sensitive content omitted]"
        for secret in secrets:
            if secret:
                value = value.replace(secret, REDACTED)
        return value
    if value is None or type(value) in (int, float, bool):
        return value
    return "[unsupported content]"


def safe_text(value: str, *, limit=128*1024, secrets=()) -> str:
    text = project(value, secrets=secrets)
    encoded = str(text).encode('utf-8')
    if len(encoded) > limit:
        return encoded[:max(0,limit-64)].decode('utf-8', errors='ignore') + '\n[truncated; evidence incomplete]'
    return str(text)


def argument_summary(arguments) -> str:
    # No values or attacker-chosen argument keys in operational diagnostics.
    return f"Arguments: {len(arguments)} fields" if isinstance(arguments, dict) else "Invalid arguments"
