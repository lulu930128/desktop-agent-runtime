from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, parseaddr
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("kuro-mail")

OPEN_LLM_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = Path(
    os.path.expandvars(
        os.path.expanduser(
            os.getenv("KURO_GMAIL_PRIVATE_DIR", str(OPEN_LLM_ROOT / "private" / "gmail"))
        )
    )
).resolve()
DEFAULT_CLIENT_FILE = PRIVATE_DIR / "gmail_oauth_client.json"
DEFAULT_TOKEN_FILE = PRIVATE_DIR / ("gmail_token.dpapi" if os.name == "nt" else "gmail_token.json")
PENDING_SESSION_FILE = PRIVATE_DIR / "gmail_auth_session.json"
DEFAULT_PREFERENCES_FILE = PRIVATE_DIR / "mail_preferences.json"
DEFAULT_RULES_FILE = PRIVATE_DIR / "mail_rules.json"

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:53682/oauth2callback"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
GMAIL_API_ROOT = "https://gmail.googleapis.com/gmail/v1/users/me"
HTTP_TIMEOUT = 25.0
DEFAULT_PET_CONTROL_URL = "http://127.0.0.1:23567"
MAX_MAIL_RESULTS = 500
DEFAULT_MAIL_PREFERENCES: dict[str, Any] = {
    "version": 1,
    "autoRefresh": True,
    "intervalSeconds": 900,
    "maxResults": 12,
    "newerThanDays": 7,
    "unreadOnly": True,
    "extraQuery": "",
    "focusSenders": [],
    "focusDomains": [],
    "focusKeywords": [],
    "ignoreSenders": [],
    "ignoreDomains": [],
    "ignoreKeywords": [],
}
DEFAULT_MAIL_RULES: list[dict[str, Any]] = [
    {
        "id": "kgi-settlement-shortfall",
        "name": "凱基交割缺款通知",
        "type": "required_event",
        "enabled": True,
        "if": {
            "all": [
                {"field": "senderDomain", "op": "endsWith", "value": "kgieworld.com.tw"},
                {
                    "field": "text",
                    "op": "containsAny",
                    "value": ["缺款通知", "缺款金額", "入足額款項", "交割專戶"],
                },
            ],
            "none": [
                {
                    "field": "subject",
                    "op": "containsAny",
                    "value": ["每日帳單", "本日對帳單", "轉單通知"],
                }
            ],
        },
        "then": {
            "priority": "critical",
            "category": "finance.settlement_shortfall",
            "score": 130,
            "fetchFullBody": True,
            "tags": ["必做", "缺款", "凱基"],
            "extract": [
                {"key": "amount", "label": "缺款金額", "pattern": r"缺款金額\s*([0-9,]+)"},
                {"key": "debitDate", "label": "扣款日期", "pattern": r"於\s*(\d{1,2}/\d{1,2})\s*扣款"},
                {
                    "key": "deadline",
                    "label": "入金期限",
                    "pattern": r"請於\s*(\d{1,2}/\d{1,2}\s*\d{1,2}:\d{2})\s*前",
                },
                {"key": "account", "label": "入金帳號", "pattern": r"入金帳號\s*([0-9A-Za-z()\-\s]+)"},
            ],
        },
    },
    {
        "id": "kgi-routine-statement",
        "name": "凱基例行帳務通知",
        "type": "mute",
        "enabled": True,
        "if": {
            "all": [
                {"field": "senderDomain", "op": "endsWith", "value": "kgieworld.com.tw"},
                {
                    "field": "text",
                    "op": "containsAny",
                    "value": ["每日帳單", "本日對帳單", "轉單通知", "扣抵交易"],
                },
            ],
            "none": [
                {"field": "text", "op": "containsAny", "value": ["缺款通知", "缺款金額", "入足額款項"]}
            ],
        },
        "then": {
            "category": "finance.routine_statement",
            "scorePenalty": 90,
            "tags": ["例行通知", "凱基"],
        },
    },
    {
        "id": "payment-or-security-action",
        "name": "付款或帳號安全處理",
        "type": "required_event",
        "enabled": True,
        "if": {
            "any": [
                {
                    "field": "text",
                    "op": "containsAny",
                    "value": ["付款失敗", "扣款失敗", "payment failed", "failed payment"],
                },
                {
                    "field": "text",
                    "op": "containsAny",
                    "value": ["security alert", "verification code", "two-factor authentication", "2FA"],
                },
            ]
        },
        "then": {
            "priority": "high",
            "category": "account_or_payment.action",
            "score": 95,
            "fetchFullBody": False,
            "tags": ["必做", "帳號/付款"],
        },
    },
]


class MailConfigError(RuntimeError):
    pass


class MailAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str
    redirect_uris: list[str]
    source: str


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _error_response(error: Exception | str, *, error_type: str = "mail_error") -> str:
    return _json_response(
        {
            "ok": False,
            "error_type": error_type,
            "error": str(error),
        }
    )


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _now_ts() -> int:
    return int(time.time())


def _iso_from_ts(timestamp: int | float | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).astimezone().isoformat()


def _local_date_key() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _ensure_private_dir() -> None:
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)


def _path_from_env(name: str, fallback: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    return Path(os.path.expandvars(os.path.expanduser(raw))).resolve()


def _client_file() -> Path:
    return _path_from_env("KURO_GMAIL_OAUTH_CLIENT_FILE", DEFAULT_CLIENT_FILE)


def _token_file() -> Path:
    return _path_from_env("KURO_GMAIL_TOKEN_FILE", DEFAULT_TOKEN_FILE)


def _preferences_file() -> Path:
    return _path_from_env("KURO_GMAIL_PREFERENCES_FILE", DEFAULT_PREFERENCES_FILE)


def _rules_file() -> Path:
    return _path_from_env("KURO_GMAIL_RULES_FILE", DEFAULT_RULES_FILE)


def _redirect_uri(client: OAuthClient | None = None) -> str:
    env_value = os.getenv("KURO_GMAIL_REDIRECT_URI", "").strip()
    if env_value:
        return env_value
    if client and client.redirect_uris:
        return client.redirect_uris[0]
    return DEFAULT_REDIRECT_URI


def _load_oauth_client() -> OAuthClient:
    env_client_id = os.getenv("KURO_GMAIL_CLIENT_ID", "").strip()
    if env_client_id:
        return OAuthClient(
            client_id=env_client_id,
            client_secret=os.getenv("KURO_GMAIL_CLIENT_SECRET", "").strip(),
            auth_uri=os.getenv("KURO_GMAIL_AUTH_URI", AUTH_URI).strip() or AUTH_URI,
            token_uri=os.getenv("KURO_GMAIL_TOKEN_URI", TOKEN_URI).strip() or TOKEN_URI,
            redirect_uris=[os.getenv("KURO_GMAIL_REDIRECT_URI", "").strip()],
            source="environment",
        )

    path = _client_file()
    if not path.exists():
        raise MailConfigError(
            "Gmail OAuth client is not configured. Put the Google OAuth Desktop "
            f"client JSON at {path}, or set KURO_GMAIL_CLIENT_ID in the local environment."
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MailConfigError(f"Failed to read Gmail OAuth client file: {path}") from exc

    cfg = raw.get("installed") or raw.get("web") or raw
    client_id = str(cfg.get("client_id") or "").strip()
    if not client_id:
        raise MailConfigError(f"Gmail OAuth client file has no client_id: {path}")

    return OAuthClient(
        client_id=client_id,
        client_secret=str(cfg.get("client_secret") or "").strip(),
        auth_uri=str(cfg.get("auth_uri") or AUTH_URI).strip(),
        token_uri=str(cfg.get("token_uri") or TOKEN_URI).strip(),
        redirect_uris=[str(item).strip() for item in cfg.get("redirect_uris") or [] if str(item).strip()],
        source=str(path),
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _new_pkce_verifier() -> str:
    return _b64url(secrets.token_bytes(48))


def _pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    _ensure_private_dir()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_rule_text(value: Any, *, max_chars: int = 120) -> str:
    normalized = " ".join(str(value or "").strip().split())[:max_chars]
    _display, address = parseaddr(normalized)
    if address and ("<" in normalized or ">" in normalized):
        normalized = address
    if normalized.startswith("<") and normalized.endswith(">"):
        normalized = normalized[1:-1].strip()
    return normalized


def _normalize_text_list(value: Any, *, max_items: int = 80, max_chars: int = 120) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    output: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = _normalize_rule_text(item, max_chars=max_chars)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
        if len(output) >= max_items:
            break
    return output


def _normalize_mail_preferences(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    prefs = dict(DEFAULT_MAIL_PREFERENCES)
    prefs["autoRefresh"] = bool(source.get("autoRefresh", prefs["autoRefresh"]))
    prefs["intervalSeconds"] = _clamp_int(
        source.get("intervalSeconds", prefs["intervalSeconds"]),
        default=prefs["intervalSeconds"],
        minimum=300,
        maximum=86400,
    )
    prefs["maxResults"] = _clamp_int(
        source.get("maxResults", prefs["maxResults"]),
        default=prefs["maxResults"],
        minimum=1,
        maximum=MAX_MAIL_RESULTS,
    )
    prefs["newerThanDays"] = _clamp_int(
        source.get("newerThanDays", prefs["newerThanDays"]),
        default=prefs["newerThanDays"],
        minimum=1,
        maximum=365,
    )
    prefs["unreadOnly"] = bool(source.get("unreadOnly", prefs["unreadOnly"]))
    prefs["extraQuery"] = _compact_text(source.get("extraQuery", prefs["extraQuery"]), 240)
    for key in (
        "focusSenders",
        "focusDomains",
        "focusKeywords",
        "ignoreSenders",
        "ignoreDomains",
        "ignoreKeywords",
    ):
        prefs[key] = _normalize_text_list(source.get(key, prefs[key]))
    return prefs


def _load_mail_preferences() -> dict[str, Any]:
    path = _preferences_file()
    if not path.exists():
        return _normalize_mail_preferences()
    try:
        return _normalize_mail_preferences(_read_json_file(path))
    except Exception:
        return _normalize_mail_preferences()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _normalize_condition(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    field = _normalize_rule_text(raw.get("field", "text"), max_chars=48)
    op = _normalize_rule_text(raw.get("op", "contains"), max_chars=32)
    value = raw.get("value", "")
    if isinstance(value, list):
        normalized_value: Any = [_normalize_rule_text(item, max_chars=200) for item in value]
        normalized_value = [item for item in normalized_value if item]
    else:
        normalized_value = _normalize_rule_text(value, max_chars=500)
    if not field or not op or normalized_value in ("", []):
        return None
    return {"field": field, "op": op, "value": normalized_value}


def _normalize_rule(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    rule_id = _normalize_rule_text(raw.get("id"), max_chars=80)
    name = _normalize_rule_text(raw.get("name") or rule_id, max_chars=120)
    rule_type = _normalize_rule_text(raw.get("type", "required_event"), max_chars=32)
    if not rule_id or rule_type not in {"required_event", "mute"}:
        return None
    raw_if = raw.get("if") if isinstance(raw.get("if"), dict) else {}
    normalized_if: dict[str, list[dict[str, Any]]] = {}
    for group in ("all", "any", "none"):
        conditions = [_normalize_condition(item) for item in _as_list(raw_if.get(group, []))]
        normalized_if[group] = [item for item in conditions if item]
    then = raw.get("then") if isinstance(raw.get("then"), dict) else {}
    extract_rules = []
    for item in then.get("extract") or []:
        if not isinstance(item, dict):
            continue
        key = _normalize_rule_text(item.get("key"), max_chars=48)
        pattern = str(item.get("pattern") or "").strip()
        if key and pattern:
            extract_rules.append(
                {
                    "key": key,
                    "label": _normalize_rule_text(item.get("label") or key, max_chars=80),
                    "pattern": pattern[:500],
                }
            )
    return {
        "id": rule_id,
        "name": name,
        "type": rule_type,
        "enabled": bool(raw.get("enabled", True)),
        "if": normalized_if,
        "then": {
            "priority": _normalize_rule_text(then.get("priority", "high"), max_chars=24),
            "category": _normalize_rule_text(then.get("category", rule_type), max_chars=80),
            "score": _clamp_int(then.get("score"), default=100, minimum=-100, maximum=200),
            "scorePenalty": _clamp_int(then.get("scorePenalty"), default=80, minimum=0, maximum=200),
            "fetchFullBody": bool(then.get("fetchFullBody", False)),
            "tags": _normalize_text_list(then.get("tags", []), max_items=12, max_chars=40),
            "extract": extract_rules[:12],
        },
    }


def _normalize_mail_rules(raw: Any) -> list[dict[str, Any]]:
    source = raw.get("rules") if isinstance(raw, dict) else raw
    if not isinstance(source, list):
        source = DEFAULT_MAIL_RULES
    output = []
    seen: set[str] = set()
    for item in source:
        rule = _normalize_rule(item)
        if not rule or rule["id"] in seen:
            continue
        seen.add(rule["id"])
        output.append(rule)
    return output


def _load_mail_rules() -> list[dict[str, Any]]:
    path = _rules_file()
    if not path.exists():
        return _normalize_mail_rules(DEFAULT_MAIL_RULES)
    try:
        return _normalize_mail_rules(_read_json_file(path))
    except Exception:
        return _normalize_mail_rules(DEFAULT_MAIL_RULES)


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _bytes_to_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[Any]]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buffer


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise MailAuthError("DPAPI token encryption is only available on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _bytes_to_blob(data)
    out_blob = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Kuro Gmail OAuth token",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise MailAuthError("Windows DPAPI failed to encrypt the Gmail token.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise MailAuthError("DPAPI token decryption is only available on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _bytes_to_blob(data)
    out_blob = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise MailAuthError("Windows DPAPI failed to decrypt the Gmail token.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _save_token(token: dict[str, Any]) -> None:
    path = _token_file()
    _ensure_private_dir()
    payload = dict(token)
    payload["stored_at"] = _now_ts()
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if os.name == "nt" and path.suffix.lower() == ".dpapi":
        path.write_bytes(_dpapi_protect(data))
    else:
        path.write_bytes(data)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _load_token() -> dict[str, Any] | None:
    path = _token_file()
    if not path.exists():
        return None
    raw = path.read_bytes()
    if os.name == "nt" and path.suffix.lower() == ".dpapi":
        raw = _dpapi_unprotect(raw)
    return json.loads(raw.decode("utf-8"))


def _token_is_expiring(token: dict[str, Any], *, skew_seconds: int = 90) -> bool:
    expires_at = token.get("expires_at")
    if not expires_at:
        return True
    try:
        return int(expires_at) <= _now_ts() + skew_seconds
    except Exception:
        return True


def _token_request(client: OAuthClient, data: dict[str, str]) -> dict[str, Any]:
    request_data = dict(data)
    request_data["client_id"] = client.client_id
    if client.client_secret:
        request_data["client_secret"] = client.client_secret

    try:
        response = httpx.post(client.token_uri, data=request_data, timeout=HTTP_TIMEOUT)
    except Exception as exc:
        raise MailAuthError(f"Gmail OAuth token request failed: {exc}") from exc

    if response.status_code >= 400:
        try:
            body = response.json()
            detail = body.get("error_description") or body.get("error") or response.text
        except Exception:
            detail = response.text
        raise MailAuthError(f"Gmail OAuth token request failed ({response.status_code}): {detail}")

    token = response.json()
    expires_in = _clamp_int(token.get("expires_in"), default=3600, minimum=60, maximum=86400)
    token["expires_at"] = _now_ts() + expires_in
    token["scope"] = token.get("scope") or GMAIL_SCOPE
    return token


def _refresh_token(client: OAuthClient, token: dict[str, Any]) -> dict[str, Any]:
    refresh_token = str(token.get("refresh_token") or "").strip()
    if not refresh_token:
        raise MailAuthError("Gmail token has no refresh_token. Run mail.auth_start again.")
    refreshed = _token_request(
        client,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    merged = dict(token)
    merged.update(refreshed)
    merged["refresh_token"] = refresh_token
    _save_token(merged)
    return merged


def _access_token() -> str:
    client = _load_oauth_client()
    token = _load_token()
    if not token:
        raise MailAuthError("Gmail is not authorized. Run mail.auth_start first.")
    if _token_is_expiring(token):
        token = _refresh_token(client, token)
    access_token = str(token.get("access_token") or "").strip()
    if not access_token:
        raise MailAuthError("Gmail token has no access_token. Run mail.auth_start again.")
    return access_token


def _gmail_get(path: str, params: Any = None, *, retry: bool = True) -> dict[str, Any]:
    url = f"{GMAIL_API_ROOT}/{path.lstrip('/')}"
    token = _access_token()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = httpx.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
    except Exception as exc:
        raise MailAuthError(f"Gmail API request failed: {exc}") from exc

    if response.status_code == 401 and retry:
        client = _load_oauth_client()
        current_token = _load_token() or {}
        _refresh_token(client, current_token)
        return _gmail_get(path, params=params, retry=False)

    if response.status_code >= 400:
        try:
            body = response.json()
            detail = body.get("error", {}).get("message") or response.text
        except Exception:
            detail = response.text
        raise MailAuthError(f"Gmail API request failed ({response.status_code}): {detail}")

    return response.json()


def _gmail_profile() -> dict[str, Any]:
    profile = _gmail_get("profile")
    return {
        "emailAddress": profile.get("emailAddress", ""),
        "messagesTotal": profile.get("messagesTotal"),
        "threadsTotal": profile.get("threadsTotal"),
        "historyId": profile.get("historyId", ""),
    }


def _pet_control_base_url(value: str = "") -> str:
    raw_value = (value or os.getenv("KURO_PET_CONTROL_URL") or DEFAULT_PET_CONTROL_URL).strip()
    parsed = urlparse(raw_value)
    if parsed.scheme != "http":
        raise ValueError("pet_control_url must be an http loopback URL.")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("pet_control_url must point to localhost or loopback.")
    if not parsed.port:
        raise ValueError("pet_control_url must include the pet control server port.")
    return raw_value.rstrip("/")


def _post_briefing_snapshot(
    snapshot: dict[str, Any],
    *,
    pet_control_url: str = "",
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    base_url = _pet_control_base_url(pet_control_url)
    response = httpx.post(
        f"{base_url}/briefing/snapshot",
        json=snapshot,
        timeout=httpx.Timeout(timeout_seconds),
    )
    try:
        body = response.json()
    except Exception:
        body = {"ok": False, "error": response.text[:300]}

    if response.status_code >= 400 or not body.get("ok"):
        error = body.get("error") or body.get("message") or response.text[:300]
        raise RuntimeError(f"Briefing update failed ({response.status_code}): {error}")

    snapshot_data = (body.get("data") or {}).get("snapshot") or {}
    return {
        "status_code": response.status_code,
        "panel_ok": bool(body.get("ok")),
        "section_count": len(snapshot_data.get("sections") or []),
        "updated_at": snapshot_data.get("updatedAt", ""),
    }


def _get_briefing_snapshot(
    *,
    pet_control_url: str = "",
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    base_url = _pet_control_base_url(pet_control_url)
    response = httpx.get(
        f"{base_url}/briefing",
        timeout=httpx.Timeout(timeout_seconds),
    )
    try:
        body = response.json()
    except Exception:
        body = {"ok": False, "error": response.text[:300]}

    if response.status_code >= 400 or not body.get("ok"):
        error = body.get("error") or body.get("message") or response.text[:300]
        raise RuntimeError(f"Briefing read failed ({response.status_code}): {error}")
    snapshot = body.get("snapshot")
    if not isinstance(snapshot, dict):
        raise RuntimeError("Briefing response has no snapshot object.")
    return snapshot


def _mail_payload_from_briefing_snapshot(
    snapshot: dict[str, Any],
    *,
    max_results: int = 20,
) -> dict[str, Any]:
    mail = snapshot.get("mail") if isinstance(snapshot.get("mail"), dict) else {}
    if not mail:
        raise RuntimeError("Briefing snapshot has no mail data.")

    messages = list(mail.get("messages") or [])
    response_limit = _clamp_int(max_results, default=20, minimum=1, maximum=MAX_MAIL_RESULTS)
    priority_messages = [
        message
        for message in messages
        if message.get("requiredEvent") or message.get("attention")
    ]
    return {
        "ok": True,
        "source": "dashboard_snapshot",
        "dashboardUpdatedAt": snapshot.get("updatedAt", ""),
        "account": mail.get("account", ""),
        "query": mail.get("query", ""),
        "resultSizeEstimate": mail.get("resultEstimate", 0),
        "messageCount": len(messages),
        "counts": {
            "fetched": mail.get("fetchedCount", len(messages)),
            "unread": mail.get("unreadCount", 0),
            "requiredEvents": mail.get("requiredEventCount", 0),
            "highPriority": mail.get("highPriorityCount", 0),
            "mediumPriority": mail.get("mediumPriorityCount", 0),
            "muted": mail.get("mutedCount", 0),
            "ordinary": mail.get("ordinaryCount", 0),
            "gmailImportant": mail.get("gmailImportantCount", 0),
        },
        "messages": messages[:response_limit],
        "priorityMessages": priority_messages[:response_limit],
        "rules": mail.get("rules", {}),
        "preferences": mail.get("preferences", {}),
        "briefing_snapshot": snapshot,
        "privacy": mail.get(
            "privacy",
            {
                "bodyFetched": False,
                "attachmentsFetched": False,
                "mailboxModified": False,
            },
        ),
        "next_step": (
            "This payload is read from the same Kuro Briefing dashboard snapshot. "
            "Use counts and priorityMessages when answering dashboard mail questions."
        ),
    }


def _build_daily_brief_payload_from_preferences(
    *,
    include_spam_trash: bool = False,
) -> dict[str, Any]:
    preferences = _load_mail_preferences()
    return _build_daily_brief_payload(
        max_results=preferences.get("maxResults", DEFAULT_MAIL_PREFERENCES["maxResults"]),
        newer_than_days=preferences.get("newerThanDays", DEFAULT_MAIL_PREFERENCES["newerThanDays"]),
        unread_only=bool(preferences.get("unreadOnly", DEFAULT_MAIL_PREFERENCES["unreadOnly"])),
        include_spam_trash=include_spam_trash,
    )


def _list_message_ids(query: str, max_results: int, include_spam_trash: bool) -> dict[str, Any]:
    params = {
        "maxResults": max_results,
        "q": query,
        "includeSpamTrash": "true" if include_spam_trash else "false",
    }
    return _gmail_get("messages", params=params)


def _get_message(message_id: str) -> dict[str, Any]:
    safe_id = quote(message_id.strip(), safe="")
    params = [
        ("format", "metadata"),
        ("metadataHeaders", "From"),
        ("metadataHeaders", "To"),
        ("metadataHeaders", "Cc"),
        ("metadataHeaders", "Subject"),
        ("metadataHeaders", "Date"),
        ("metadataHeaders", "Reply-To"),
    ]
    return _gmail_get(f"messages/{safe_id}", params=params)


def _get_full_message(message_id: str) -> dict[str, Any]:
    safe_id = quote(message_id.strip(), safe="")
    return _gmail_get(f"messages/{safe_id}", params=[("format", "full")])


class _HtmlTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "p",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
        "ol",
    }
    _SKIP_TAGS = {"head", "script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.casefold()
        if tag_name in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag_name == "li":
            self._parts.append("\n- ")
            return
        if tag_name in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.casefold()
        if tag_name in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if not self._skip_depth and tag_name in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data and not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        lines: list[str] = []
        for line in "".join(self._parts).splitlines():
            normalized = " ".join(line.strip().split())
            if normalized:
                lines.append(normalized)
        return "\n".join(lines)


def _looks_like_html(value: str) -> bool:
    sample = (value or "").lstrip()[:8_000].casefold()
    if not sample:
        return False
    markers = (
        "<!doctype",
        "<html",
        "<body",
        "<table",
        "<tbody",
        "<tr",
        "<td",
        "<th",
        "<div",
        "<span",
        "<p",
        "<br",
        "<a ",
        "<img",
        "<style",
        "<head",
        "<!--",
    )
    if any(marker in sample for marker in markers):
        return True
    return bool(
        re.search(
            r"</?(?:html|body|table|tbody|tr|td|th|div|span|p|br|a|img|strong|b|em|ul|ol|li|h[1-6])(?:\s|>|/)",
            sample,
        )
    )


def _decode_message_body(data: Any) -> str:
    value = str(data or "").strip()
    if not value:
        return ""
    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _html_to_text(html_value: str) -> str:
    parser = _HtmlTextExtractor()
    try:
        parser.feed(html_value or "")
        return parser.text()
    except Exception:
        return _compact_text(html_value, 20_000)


def _collect_full_parts(
    part: dict[str, Any],
    *,
    text_parts: list[str],
    html_parts: list[str],
    attachments: list[dict[str, Any]],
) -> None:
    mime_type = str(part.get("mimeType") or "")
    filename = _compact_text(part.get("filename", ""), 180)
    body = part.get("body") or {}
    attachment_id = str(body.get("attachmentId") or "")
    body_size = _clamp_int(body.get("size"), default=0, minimum=0, maximum=2_000_000_000)

    if filename or attachment_id:
        attachments.append(
            {
                "filename": filename or "(unnamed attachment)",
                "mimeType": mime_type,
                "size": body_size,
                "attachmentId": attachment_id,
                "downloaded": False,
            }
        )

    decoded = _decode_message_body(body.get("data"))
    if decoded:
        if mime_type == "text/plain":
            text_parts.append(decoded)
        elif mime_type == "text/html":
            html_parts.append(decoded)

    for child in part.get("parts") or []:
        if isinstance(child, dict):
            _collect_full_parts(child, text_parts=text_parts, html_parts=html_parts, attachments=attachments)


def _body_text_from_parts(
    text_parts: list[str],
    html_parts: list[str],
    *,
    max_body_chars: int,
) -> tuple[str, str, bool]:
    body_text = "\n\n".join(part.strip() for part in text_parts if part.strip())
    body_source = "text/plain"
    if body_text and _looks_like_html(body_text):
        parsed_text = _html_to_text(body_text)
        if parsed_text:
            body_text = parsed_text
            body_source = "text/plain-html"
    elif not body_text and html_parts:
        body_text = _html_to_text("\n".join(html_parts))
        body_source = "text/html"
    body_text = body_text.strip()
    truncated = len(body_text) > max_body_chars
    if truncated:
        body_text = body_text[:max_body_chars].rstrip()
    return body_text, body_source if body_text else "", truncated


def _extract_message_detail_parts(
    raw: dict[str, Any],
    *,
    max_body_chars: int,
) -> dict[str, Any]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict[str, Any]] = []
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    _collect_full_parts(payload, text_parts=text_parts, html_parts=html_parts, attachments=attachments)
    body_text, body_source, truncated = _body_text_from_parts(
        text_parts,
        html_parts,
        max_body_chars=max_body_chars,
    )
    return {
        "bodyText": body_text,
        "bodySource": body_source,
        "bodyTruncated": truncated,
        "attachments": attachments,
    }


def _fetch_message_body_for_rules(message_id: str, *, max_body_chars: int = 12_000) -> str:
    raw = _get_full_message(message_id)
    return str(_extract_message_detail_parts(raw, max_body_chars=max_body_chars).get("bodyText") or "")


def _build_message_detail(message_id: str, *, max_body_chars: int = 20_000) -> dict[str, Any]:
    max_body_chars = _clamp_int(max_body_chars, default=20_000, minimum=1_000, maximum=80_000)
    raw = _get_full_message(message_id)
    normalized = _normalize_message(raw)
    preferences = _load_mail_preferences()
    parts = _extract_message_detail_parts(raw, max_body_chars=max_body_chars)
    rules = _load_mail_rules()
    rule_result = _evaluate_mail_rules(normalized, rules, body_text=str(parts.get("bodyText") or ""))
    scored = _score_message(normalized, preferences, rule_result)

    return {
        "ok": True,
        "message": {
            **_mail_message_summary(scored),
            "bodyText": parts["bodyText"],
            "bodySource": parts["bodySource"],
            "bodyTruncated": parts["bodyTruncated"],
            "attachments": parts["attachments"],
            "attachmentCount": len(parts["attachments"]),
            "privacy": {
                "fullBodyFetched": True,
                "attachmentsFetched": False,
                "mailboxModified": False,
            },
        },
    }


def _headers_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in payload.get("headers") or []:
        name = str(item.get("name") or "").strip().casefold()
        value = str(item.get("value") or "").strip()
        if name and value:
            output[name] = value
    return output


def _parsed_email_date(raw_value: str) -> str:
    if not raw_value:
        return ""
    try:
        parsed = parsedate_to_datetime(raw_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().isoformat()
    except Exception:
        return raw_value[:80]


def _message_time(message: dict[str, Any], headers: dict[str, str]) -> str:
    internal_date = str(message.get("internalDate") or "").strip()
    if internal_date.isdigit():
        return datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc).astimezone().isoformat()
    return _parsed_email_date(headers.get("date", ""))


def _compact_text(value: Any, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_chars]


def _sender_parts(raw_sender: str) -> tuple[str, str]:
    _display, address = parseaddr(raw_sender or "")
    email = _compact_text(address, 180).casefold()
    domain = email.rsplit("@", 1)[1] if "@" in email else ""
    return email, domain


def _matches_exact(value: str, patterns: list[str]) -> bool:
    normalized = value.casefold()
    return any(normalized == pattern.casefold() for pattern in patterns)


def _matches_domain(domain: str, patterns: list[str]) -> bool:
    normalized = domain.casefold()
    return any(
        normalized == pattern.casefold().lstrip("@")
        or normalized.endswith(f".{pattern.casefold().lstrip('@')}")
        for pattern in patterns
    )


def _matched_keywords(text_value: str, patterns: list[str]) -> list[str]:
    haystack = text_value.casefold()
    matches = []
    for pattern in patterns:
        needle = pattern.casefold()
        if needle and needle in haystack:
            matches.append(pattern)
    return matches


def _rule_text_value(message: dict[str, Any], field: str, body_text: str = "") -> str:
    normalized = field.casefold()
    if normalized in {"text", "all", "searchable"}:
        return " ".join(
            str(part or "")
            for part in (
                message.get("from"),
                message.get("senderEmail"),
                message.get("senderDomain"),
                message.get("subject"),
                message.get("snippet"),
                body_text,
            )
        )
    if normalized in {"body", "bodytext", "fullbody"}:
        return body_text
    if normalized == "labels":
        return " ".join(str(item) for item in message.get("labels") or [])
    return str(message.get(field) or message.get(normalized) or "")


def _condition_matches(message: dict[str, Any], condition: dict[str, Any], body_text: str = "") -> bool:
    haystack = _rule_text_value(message, str(condition.get("field") or "text"), body_text)
    op = str(condition.get("op") or "contains").casefold()
    values = condition.get("value")
    needles = [str(item) for item in values] if isinstance(values, list) else [str(values or "")]
    haystack_folded = haystack.casefold()

    if op in {"exists", "present"}:
        return bool(haystack.strip())
    if op in {"equals", "eq", "is"}:
        return any(haystack_folded == needle.casefold() for needle in needles)
    if op in {"contains", "includes"}:
        return any(needle.casefold() in haystack_folded for needle in needles if needle)
    if op in {"containsany", "contains_any", "any"}:
        return any(needle.casefold() in haystack_folded for needle in needles if needle)
    if op in {"startswith", "starts_with"}:
        return any(haystack_folded.startswith(needle.casefold()) for needle in needles if needle)
    if op in {"endswith", "ends_with", "domainmatches"}:
        return any(
            haystack_folded == needle.casefold().lstrip("@")
            or haystack_folded.endswith(f".{needle.casefold().lstrip('@')}")
            or haystack_folded.endswith(needle.casefold())
            for needle in needles
            if needle
        )
    if op == "regex":
        for needle in needles:
            try:
                if needle and re.search(needle, haystack, flags=re.IGNORECASE):
                    return True
            except re.error:
                continue
        return False
    return False


def _rule_matches(message: dict[str, Any], rule: dict[str, Any], body_text: str = "") -> bool:
    conditions = rule.get("if") if isinstance(rule.get("if"), dict) else {}
    all_conditions = conditions.get("all") or []
    any_conditions = conditions.get("any") or []
    none_conditions = conditions.get("none") or []
    if all_conditions and not all(_condition_matches(message, item, body_text) for item in all_conditions):
        return False
    if any_conditions and not any(_condition_matches(message, item, body_text) for item in any_conditions):
        return False
    if none_conditions and any(_condition_matches(message, item, body_text) for item in none_conditions):
        return False
    return bool(all_conditions or any_conditions)


def _extract_rule_values(text_value: str, extract_rules: list[dict[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in extract_rules:
        key = str(item.get("key") or "").strip()
        pattern = str(item.get("pattern") or "").strip()
        if not key or not pattern:
            continue
        try:
            match = re.search(pattern, text_value, flags=re.IGNORECASE)
        except re.error:
            continue
        if match:
            value = match.group(1) if match.groups() else match.group(0)
            output[key] = _compact_text(value, 160)
    return output


def _event_from_rule(rule: dict[str, Any], body_text: str = "") -> dict[str, Any]:
    then = rule.get("then") if isinstance(rule.get("then"), dict) else {}
    return {
        "id": rule.get("id", ""),
        "ruleId": rule.get("id", ""),
        "name": rule.get("name", ""),
        "category": then.get("category", ""),
        "priority": then.get("priority", "high"),
        "score": int(then.get("score") or 100),
        "fetchFullBody": bool(then.get("fetchFullBody")),
        "tags": list(then.get("tags") or []),
        "extracted": _extract_rule_values(body_text, then.get("extract") or []) if body_text else {},
    }


def _evaluate_mail_rules(
    message: dict[str, Any],
    rules: list[dict[str, Any]],
    *,
    body_text: str = "",
) -> dict[str, Any]:
    required_events: list[dict[str, Any]] = []
    mute_rules: list[dict[str, Any]] = []
    for rule in rules:
        if not rule.get("enabled", True) or not _rule_matches(message, rule, body_text):
            continue
        if rule.get("type") == "required_event":
            required_events.append(_event_from_rule(rule, body_text))
        elif rule.get("type") == "mute":
            then = rule.get("then") if isinstance(rule.get("then"), dict) else {}
            mute_rules.append(
                {
                    "id": rule.get("id", ""),
                    "ruleId": rule.get("id", ""),
                    "name": rule.get("name", ""),
                    "category": then.get("category", ""),
                    "scorePenalty": int(then.get("scorePenalty") or 80),
                    "tags": list(then.get("tags") or []),
                }
            )
    return {
        "requiredEvents": required_events,
        "muteRules": mute_rules,
        "needsFullBody": any(event.get("fetchFullBody") for event in required_events),
    }


def _score_message(
    message: dict[str, Any],
    preferences: dict[str, Any],
    rule_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    labels = [str(item) for item in message.get("labels") or []]
    sender_email = str(message.get("senderEmail") or "").casefold()
    sender_domain = str(message.get("senderDomain") or "").casefold()
    rule_payload = rule_result if isinstance(rule_result, dict) else {}
    required_events = list(rule_payload.get("requiredEvents") or [])
    mute_rules = list(rule_payload.get("muteRules") or [])
    searchable_text = " ".join(
        [
            str(message.get("from") or ""),
            str(message.get("subject") or ""),
            str(message.get("snippet") or ""),
        ]
    )

    score = 0
    reasons: list[str] = []
    if message.get("unread"):
        score += 20
        reasons.append("unread")
    if message.get("important"):
        score += 35
        reasons.append("gmail-important")
    if _matches_exact(sender_email, preferences.get("focusSenders", [])):
        score += 60
        reasons.append("focus-sender")
    if _matches_domain(sender_domain, preferences.get("focusDomains", [])):
        score += 50
        reasons.append("focus-domain")
    for keyword in _matched_keywords(searchable_text, preferences.get("focusKeywords", []))[:3]:
        score += 25
        reasons.append(f"keyword:{keyword}")
    if _matches_exact(sender_email, preferences.get("ignoreSenders", [])):
        score -= 80
        reasons.append("ignored-sender")
    if _matches_domain(sender_domain, preferences.get("ignoreDomains", [])):
        score -= 70
        reasons.append("ignored-domain")
    for keyword in _matched_keywords(searchable_text, preferences.get("ignoreKeywords", []))[:3]:
        score -= 35
        reasons.append(f"ignored:{keyword}")
    for mute_rule in mute_rules:
        score -= int(mute_rule.get("scorePenalty") or 80)
        reasons.append(f"muted:{mute_rule.get('name') or mute_rule.get('id')}")
    if "CATEGORY_PROMOTIONS" in labels:
        score -= 20
        reasons.append("promotions")
    if "CATEGORY_SOCIAL" in labels:
        score -= 10
        reasons.append("social")

    if required_events:
        top_event = required_events[0]
        score = max(score, int(top_event.get("score") or 100))
        reasons.insert(0, "required-event")
        priority = str(top_event.get("priority") or "high").casefold()
        level = "critical" if priority == "critical" else "high"
    elif mute_rules:
        level = "muted"
    elif score >= 70:
        level = "high"
    elif score >= 35:
        level = "medium"
    else:
        level = "low"

    enriched = dict(message)
    enriched["priorityScore"] = max(-100, min(score, 200))
    enriched["priorityLevel"] = level
    enriched["priorityReasons"] = reasons[:6]
    enriched["attention"] = level in {"critical", "high", "medium"}
    enriched["requiredEvent"] = bool(required_events)
    enriched["events"] = required_events[:4]
    enriched["event"] = required_events[0] if required_events else None
    enriched["muted"] = bool(mute_rules) and not required_events
    enriched["muteRules"] = mute_rules[:4]
    return enriched


def _message_sort_key(message: dict[str, Any]) -> tuple[int, int, int, int, str]:
    required = 1 if message.get("requiredEvent") else 0
    unmuted = 0 if message.get("muted") else 1
    unread = 1 if message.get("unread") else 0
    return (
        required,
        unmuted,
        int(message.get("priorityScore") or 0),
        unread,
        str(message.get("date") or ""),
    )


def _normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    headers = _headers_from_payload(message.get("payload") or {})
    labels = [str(item) for item in message.get("labelIds") or []]
    sender_email, sender_domain = _sender_parts(headers.get("from", ""))
    return {
        "id": str(message.get("id") or ""),
        "threadId": str(message.get("threadId") or ""),
        "from": _compact_text(headers.get("from", ""), 180),
        "senderEmail": sender_email,
        "senderDomain": sender_domain,
        "to": _compact_text(headers.get("to", ""), 180),
        "subject": _compact_text(headers.get("subject", "(no subject)"), 220) or "(no subject)",
        "date": _message_time(message, headers),
        "snippet": _compact_text(message.get("snippet", ""), 320),
        "labels": labels,
        "unread": "UNREAD" in labels,
        "important": "IMPORTANT" in labels,
        "bodyFetched": False,
        "attachmentsFetched": False,
    }


def _fetch_messages(query: str, max_results: int, include_spam_trash: bool) -> tuple[list[dict[str, Any]], int]:
    listing = _list_message_ids(query, max_results, include_spam_trash)
    ids = [str(item.get("id") or "") for item in listing.get("messages") or []]
    messages: list[dict[str, Any]] = []
    for message_id in ids:
        if not message_id:
            continue
        messages.append(_normalize_message(_get_message(message_id)))
    estimate = _clamp_int(listing.get("resultSizeEstimate"), default=len(messages), minimum=0, maximum=1_000_000)
    return messages, estimate


def _classify_messages(
    messages: list[dict[str, Any]],
    *,
    preferences: dict[str, Any],
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for message in messages:
        working = dict(message)
        rule_result = _evaluate_mail_rules(working, rules)
        if rule_result.get("needsFullBody"):
            try:
                body_text = _fetch_message_body_for_rules(str(working.get("id") or ""))
            except Exception as exc:
                body_text = ""
                working["ruleBodyFetchError"] = _compact_text(str(exc), 180)
            if body_text:
                working["bodyFetchedForRules"] = True
                rule_result = _evaluate_mail_rules(working, rules, body_text=body_text)
        output.append(_score_message(working, preferences, rule_result))
    return output


def _message_item_text(message: dict[str, Any]) -> str:
    sender = message.get("from") or "Unknown sender"
    subject = message.get("subject") or "(no subject)"
    return _compact_text(f"{subject} - {sender}", 220)


def _message_meta(message: dict[str, Any]) -> str:
    parts = []
    if message.get("requiredEvent"):
        event = message.get("event") if isinstance(message.get("event"), dict) else {}
        parts.append(f"必做：{event.get('name') or '固定事件'}")
    priority_level = str(message.get("priorityLevel") or "")
    if priority_level and priority_level != "low":
        parts.append(
            {
                "critical": "關鍵",
                "high": "高優先",
                "medium": "中優先",
                "muted": "降噪",
            }.get(priority_level, priority_level)
        )
    if message.get("unread"):
        parts.append("未讀")
    if message.get("important"):
        parts.append("Gmail 重要")
    if message.get("date"):
        parts.append(str(message["date"])[:16])
    return " / ".join(parts)[:64]


def _mail_message_summary(message: dict[str, Any]) -> dict[str, Any]:
    event = message.get("event") if isinstance(message.get("event"), dict) else None
    return {
        "id": message.get("id", ""),
        "threadId": message.get("threadId", ""),
        "from": message.get("from", ""),
        "senderEmail": message.get("senderEmail", ""),
        "senderDomain": message.get("senderDomain", ""),
        "subject": message.get("subject", ""),
        "date": message.get("date", ""),
        "snippet": message.get("snippet", ""),
        "unread": bool(message.get("unread")),
        "gmailImportant": bool(message.get("important")),
        "priorityScore": int(message.get("priorityScore") or 0),
        "priorityLevel": message.get("priorityLevel", "low"),
        "priorityReasons": list(message.get("priorityReasons") or []),
        "attention": bool(message.get("attention")),
        "requiredEvent": bool(message.get("requiredEvent")),
        "event": event,
        "events": list(message.get("events") or []),
        "muted": bool(message.get("muted")),
        "muteRules": list(message.get("muteRules") or []),
        "bodyFetched": False,
        "attachmentsFetched": False,
    }


def _mail_rules_summary(rules: list[dict[str, Any]]) -> dict[str, Any]:
    enabled = [rule for rule in rules if rule.get("enabled", True)]
    return {
        "totalCount": len(rules),
        "enabledCount": len(enabled),
        "requiredEventCount": sum(1 for rule in enabled if rule.get("type") == "required_event"),
        "muteCount": sum(1 for rule in enabled if rule.get("type") == "mute"),
        "rulesFile": str(_rules_file()),
    }


def _mail_preferences_summary(preferences: dict[str, Any]) -> dict[str, Any]:
    return {
        "autoRefresh": bool(preferences.get("autoRefresh")),
        "intervalSeconds": preferences.get("intervalSeconds"),
        "maxResults": preferences.get("maxResults"),
        "newerThanDays": preferences.get("newerThanDays"),
        "unreadOnly": bool(preferences.get("unreadOnly")),
        "extraQuery": preferences.get("extraQuery", ""),
        "focusRuleCount": sum(
            len(preferences.get(key, []))
            for key in ("focusSenders", "focusDomains", "focusKeywords")
        ),
        "ignoreRuleCount": sum(
            len(preferences.get(key, []))
            for key in ("ignoreSenders", "ignoreDomains", "ignoreKeywords")
        ),
    }


def _build_briefing_snapshot(
    *,
    messages: list[dict[str, Any]],
    result_estimate: int,
    account: str,
    query: str,
    preferences: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat()
    unread_count = sum(1 for message in messages if message.get("unread"))
    gmail_important_count = sum(1 for message in messages if message.get("important"))
    required_event_count = sum(1 for message in messages if message.get("requiredEvent"))
    muted_count = sum(1 for message in messages if message.get("muted"))
    high_priority_count = sum(1 for message in messages if message.get("priorityLevel") in {"critical", "high"})
    medium_priority_count = sum(1 for message in messages if message.get("priorityLevel") == "medium")
    attention_count = sum(1 for message in messages if message.get("requiredEvent") or message.get("attention"))
    event_messages = [message for message in messages if message.get("requiredEvent")]
    priority_messages = event_messages + [
        message for message in messages if message.get("attention") and not message.get("requiredEvent")
    ]
    top_items = [
        {
            "text": _message_item_text(message),
            "meta": _message_meta(message),
            "source": "gmail",
        }
        for message in (priority_messages or messages)[:5]
    ]
    if not top_items:
        top_items = [{"text": "目前查詢條件沒有符合的 Gmail 信件。", "meta": "空"}]
    task_items = [
        {
            "text": _message_item_text(message),
            "meta": _message_meta(message),
            "source": "gmail",
        }
        for message in event_messages[:8]
    ]
    if not task_items:
        task_items = [{"text": "目前沒有固定事件命中的待處理信件。", "meta": "空"}]

    return {
        "schemaVersion": 1,
        "date": _local_date_key(),
        "title": "\u4eca\u65e5\u7c21\u5831",
        "updatedAt": now,
        "sections": [
            {
                "key": "overview",
                "label": "\u4eca\u65e5\u5927\u7db1",
                "icon": "T",
                "count": attention_count,
                "subtitle": "\u4eca\u65e5\u90f5\u4ef6\u8207\u512a\u5148\u9805",
                "accent": "",
                "modules": [
                    {
                        "id": "gmail-priority",
                        "title": "\u512a\u5148\u8655\u7406",
                        "tag": "Gmail",
                        "value": str(attention_count),
                        "unit": "items",
                        "wide": True,
                        "items": top_items[:3],
                    },
                    {
                        "id": "gmail-status",
                        "title": "\u5de5\u5177\u72c0\u614b",
                        "tag": "Sources",
                        "value": "1",
                        "unit": "online",
                        "items": [
                            {
                                "text": f"Gmail 已連線：{account or '未知帳號'}",
                                "meta": "已連線",
                            }
                        ],
                    },
                ],
            },
            {
                "key": "tasks",
                "label": "\u5f85\u8655\u7406",
                "icon": "A",
                "count": required_event_count,
                "subtitle": "固定規則命中的必做事件",
                "accent": "accent-yellow",
                "modules": [
                    {
                        "id": "mail-required-events",
                        "title": "必做事件",
                        "tag": "Rules",
                        "value": str(required_event_count),
                        "unit": "items",
                        "wide": True,
                        "items": task_items,
                    }
                ],
            },
            {
                "key": "mail",
                "label": "Mail",
                "icon": "M",
                "count": result_estimate,
                "subtitle": "Gmail 信件摘要（唯讀）",
                "accent": "accent-cyan",
                "modules": [
                    {
                        "id": "gmail-unread",
                        "title": "\u672a\u8b80\u8207\u8fd1\u671f\u4fe1\u4ef6",
                        "tag": "Gmail",
                        "value": str(result_estimate),
                        "unit": "符合條件",
                        "wide": True,
                        "items": top_items,
                    },
                    {
                        "id": "gmail-counts",
                        "title": "\u4fe1\u4ef6\u72c0\u614b",
                        "tag": "唯讀",
                        "value": str(unread_count),
                        "unit": "未讀",
                        "items": [
                            {"text": f"高優先信件：{high_priority_count}", "meta": "評分"},
                            {"text": f"Gmail 重要標記：{gmail_important_count}", "meta": "資料"},
                            {"text": f"查詢條件：{query}", "meta": "Gmail 搜尋"},
                        ],
                    },
                ],
            },
            {
                "key": "messages",
                "label": "Messages",
                "icon": "D",
                "count": 0,
                "subtitle": "\u8a0a\u606f\u8207\u793e\u7fa4\u6458\u8981",
                "accent": "accent-green",
                "modules": [],
            },
            {
                "key": "stocks",
                "label": "Stocks",
                "icon": "S",
                "count": 0,
                "subtitle": "\u5e02\u5834\u8207 watchlist \u6a21\u7d44",
                "accent": "accent-red",
                "modules": [],
            },
            {
                "key": "news",
                "label": "News",
                "icon": "N",
                "count": 0,
                "subtitle": "\u65b0\u805e\u8207\u4e16\u754c\u8a0a\u865f",
                "accent": "",
                "modules": [],
            },
            {
                "key": "calendar",
                "label": "Calendar",
                "icon": "C",
                "count": 0,
                "subtitle": "\u884c\u7a0b\u8207\u6642\u9593\u7bc0\u9ede",
                "accent": "accent-yellow",
                "modules": [],
            },
            {
                "key": "notes",
                "label": "Notes",
                "icon": "R",
                "count": 0,
                "subtitle": "\u5099\u5fd8\u8207\u7814\u7a76\u7b46\u8a18",
                "accent": "accent-green",
                "modules": [],
            },
        ],
        "sourceStatus": [
            {
                "id": "gmail",
                "label": "Gmail",
                "status": "connected",
                "updatedAt": now,
                "message": f"已抓取 {len(messages)} 封信。沒有讀取完整內文或附件。",
            }
        ],
        "mail": {
            "account": account,
            "query": query,
            "resultEstimate": result_estimate,
            "fetchedCount": len(messages),
            "unreadCount": unread_count,
            "requiredEventCount": required_event_count,
            "mutedCount": muted_count,
            "ordinaryCount": max(0, len(messages) - required_event_count - muted_count),
            "highPriorityCount": high_priority_count,
            "mediumPriorityCount": medium_priority_count,
            "gmailImportantCount": gmail_important_count,
            "messages": [_mail_message_summary(message) for message in messages],
            "preferences": _mail_preferences_summary(preferences),
            "rules": _mail_rules_summary(rules),
            "privacy": {
                "bodyFetched": any(message.get("bodyFetchedForRules") for message in messages),
                "attachmentsFetched": False,
                "mailboxModified": False,
            },
        },
    }


def _build_daily_brief_payload(
    *,
    max_results: int = 8,
    newer_than_days: int = 3,
    unread_only: bool = True,
    include_spam_trash: bool = False,
) -> dict[str, Any]:
    preferences = _load_mail_preferences()
    rules = _load_mail_rules()
    max_results = _clamp_int(max_results, default=8, minimum=1, maximum=MAX_MAIL_RESULTS)
    newer_than_days = _clamp_int(newer_than_days, default=3, minimum=1, maximum=30)
    query_parts = ["in:inbox", f"newer_than:{newer_than_days}d"]
    if unread_only:
        query_parts.append("is:unread")
    extra_query = str(preferences.get("extraQuery") or "").strip()
    if extra_query:
        query_parts.append(f"({extra_query})")
    query = " ".join(query_parts)
    messages, estimate = _fetch_messages(query, max_results, include_spam_trash)
    messages = _classify_messages(messages, preferences=preferences, rules=rules)
    messages = sorted(
        messages,
        key=_message_sort_key,
        reverse=True,
    )
    profile = _gmail_profile()
    account = str(profile.get("emailAddress") or "")
    snapshot = _build_briefing_snapshot(
        messages=messages,
        result_estimate=estimate,
        account=account,
        query=query,
        preferences=preferences,
        rules=rules,
    )
    return {
        "ok": True,
        "account": account,
        "query": query,
        "resultSizeEstimate": estimate,
        "messages": messages,
        "rules": _mail_rules_summary(rules),
        "briefing_snapshot": snapshot,
        "privacy": {
            "bodyFetched": False,
            "attachmentsFetched": False,
            "mailboxModified": False,
        },
    }


@mcp.tool(
    name="mail.auth_status",
    description="Check Gmail read-only OAuth setup and token status without exposing token values.",
)
def mail_auth_status(check_profile: bool = False) -> str:
    try:
        configured = True
        config_error = ""
        client_source = ""
        try:
            client_source = _load_oauth_client().source
        except Exception as exc:
            configured = False
            config_error = str(exc)

        token = None
        token_error = ""
        try:
            token = _load_token()
        except Exception as exc:
            token_error = str(exc)

        pending = PENDING_SESSION_FILE.exists()
        profile = None
        if check_profile and configured and token:
            profile = _gmail_profile()

        payload = {
            "ok": True,
            "configured": configured,
            "client_source": client_source,
            "config_error": config_error,
            "authenticated": bool(token and token.get("refresh_token")),
            "token_file": str(_token_file()),
            "token_encrypted_with_dpapi": os.name == "nt" and _token_file().suffix.lower() == ".dpapi",
            "token_error": token_error,
            "expires_at": _iso_from_ts(token.get("expires_at")) if token else "",
            "scope": token.get("scope") if token else "",
            "pending_auth_session": pending,
            "profile": profile,
            "next_step": (
                "Run mail.auth_start, open the returned URL, then pass the full redirected URL to mail.auth_finish."
                if not token
                else "Gmail read-only auth is available."
            ),
        }
        return _json_response(payload)
    except Exception as exc:
        return _error_response(exc, error_type="mail_auth_status_failed")


@mcp.tool(
    name="mail.auth_start",
    description=(
        "Start Gmail read-only OAuth. Returns a browser URL. After Google redirects to "
        "the local callback URL, copy the full browser address into mail.auth_finish."
    ),
)
def mail_auth_start(force_consent: bool = True) -> str:
    try:
        client = _load_oauth_client()
        verifier = _new_pkce_verifier()
        state = secrets.token_urlsafe(24)
        redirect_uri = _redirect_uri(client)
        session = {
            "created_at": _now_ts(),
            "state": state,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "scope": GMAIL_SCOPE,
            "client_source": client.source,
        }
        _write_json_file(PENDING_SESSION_FILE, session)
        params = {
            "client_id": client.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GMAIL_SCOPE,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "state": state,
        }
        if force_consent:
            params["prompt"] = "consent"
        auth_url = f"{client.auth_uri}?{urlencode(params)}"
        return _json_response(
            {
                "ok": True,
                "auth_url": auth_url,
                "redirect_uri": redirect_uri,
                "scope": GMAIL_SCOPE,
                "state": state,
                "expires_in_minutes": 30,
                "next_step": (
                    "Open auth_url in your browser. After Google redirects to the local "
                    "callback URL, copy the full address bar URL and call mail.auth_finish."
                ),
            }
        )
    except Exception as exc:
        return _error_response(exc, error_type="mail_auth_start_failed")


@mcp.tool(
    name="mail.auth_finish",
    description="Finish Gmail OAuth using the full redirected URL from the browser address bar.",
)
def mail_auth_finish(authorization_response: str = "", code: str = "", state: str = "") -> str:
    try:
        if not PENDING_SESSION_FILE.exists():
            raise MailAuthError("No pending Gmail auth session. Run mail.auth_start first.")
        session = _read_json_file(PENDING_SESSION_FILE)
        if _now_ts() - int(session.get("created_at") or 0) > 30 * 60:
            raise MailAuthError("Pending Gmail auth session expired. Run mail.auth_start again.")

        response_code = code.strip()
        response_state = state.strip()
        if authorization_response.strip():
            parsed = urlparse(authorization_response.strip())
            params = parse_qs(parsed.query)
            if "error" in params:
                raise MailAuthError(params.get("error_description", params["error"])[0])
            response_code = params.get("code", [""])[0].strip()
            response_state = params.get("state", [""])[0].strip()

        if not response_code:
            raise MailAuthError("No OAuth code found. Pass authorization_response as the full redirected URL.")
        if response_state != str(session.get("state") or ""):
            raise MailAuthError("OAuth state did not match the pending Gmail auth session.")

        client = _load_oauth_client()
        token = _token_request(
            client,
            {
                "grant_type": "authorization_code",
                "code": response_code,
                "code_verifier": str(session.get("code_verifier") or ""),
                "redirect_uri": str(session.get("redirect_uri") or _redirect_uri(client)),
            },
        )
        if not token.get("refresh_token"):
            existing = _load_token() or {}
            if existing.get("refresh_token"):
                token["refresh_token"] = existing["refresh_token"]
            else:
                raise MailAuthError(
                    "Google did not return a refresh_token. Run mail.auth_start with force_consent=true, "
                    "or revoke the old app grant in Google Account permissions and try again."
                )

        _save_token(token)
        try:
            PENDING_SESSION_FILE.unlink()
        except FileNotFoundError:
            pass

        profile = _gmail_profile()
        return _json_response(
            {
                "ok": True,
                "authenticated": True,
                "scope": token.get("scope", GMAIL_SCOPE),
                "expires_at": _iso_from_ts(token.get("expires_at")),
                "profile": profile,
                "token_file": str(_token_file()),
                "token_encrypted_with_dpapi": os.name == "nt" and _token_file().suffix.lower() == ".dpapi",
                "next_step": "Gmail read-only MCP is ready. Try mail.daily_brief or mail.list_unread.",
            }
        )
    except Exception as exc:
        return _error_response(exc, error_type="mail_auth_finish_failed")


@mcp.tool(
    name="mail.list_unread",
    description="List recent unread Gmail messages using metadata and snippets only. Does not mark mail as read.",
)
def mail_list_unread(max_results: int = 10, newer_than_days: int = 14, include_spam_trash: bool = False) -> str:
    try:
        max_results = _clamp_int(max_results, default=10, minimum=1, maximum=MAX_MAIL_RESULTS)
        newer_than_days = _clamp_int(newer_than_days, default=14, minimum=1, maximum=365)
        query = f"in:inbox is:unread newer_than:{newer_than_days}d"
        messages, estimate = _fetch_messages(query, max_results, include_spam_trash)
        return _json_response(
            {
                "ok": True,
                "query": query,
                "resultSizeEstimate": estimate,
                "messages": messages,
                "privacy": {
                    "bodyFetched": False,
                    "attachmentsFetched": False,
                    "mailboxModified": False,
                },
            }
        )
    except Exception as exc:
        return _error_response(exc, error_type="mail_list_unread_failed")


@mcp.tool(
    name="mail.search_recent",
    description="Search recent Gmail messages with Gmail query syntax. Returns metadata/snippets only.",
)
def mail_search_recent(
    query: str = "",
    max_results: int = 10,
    newer_than_days: int = 30,
    include_spam_trash: bool = False,
) -> str:
    try:
        max_results = _clamp_int(max_results, default=10, minimum=1, maximum=MAX_MAIL_RESULTS)
        newer_than_days = _clamp_int(newer_than_days, default=30, minimum=1, maximum=365)
        user_query = " ".join((query or "").split())
        full_query = f"newer_than:{newer_than_days}d"
        if user_query:
            full_query = f"{full_query} ({user_query})"
        messages, estimate = _fetch_messages(full_query, max_results, include_spam_trash)
        return _json_response(
            {
                "ok": True,
                "query": full_query,
                "resultSizeEstimate": estimate,
                "messages": messages,
                "privacy": {
                    "bodyFetched": False,
                    "attachmentsFetched": False,
                    "mailboxModified": False,
                },
            }
        )
    except Exception as exc:
        return _error_response(exc, error_type="mail_search_recent_failed")


@mcp.tool(
    name="mail.get_message_summary",
    description="Read one Gmail message metadata/snippet by message id. Does not fetch the full body or attachments.",
)
def mail_get_message_summary(message_id: str) -> str:
    try:
        message_id = (message_id or "").strip()
        if not message_id:
            raise ValueError("message_id is required.")
        message = _normalize_message(_get_message(message_id))
        return _json_response(
            {
                "ok": True,
                "message": message,
                "privacy": {
                    "bodyFetched": False,
                    "attachmentsFetched": False,
                    "mailboxModified": False,
                },
            }
        )
    except Exception as exc:
        return _error_response(exc, error_type="mail_get_message_summary_failed")


@mcp.tool(
    name="mail.get_message_detail",
    description=(
        "Fetch one Gmail message body on demand. It lists attachment metadata "
        "but does not download attachment content or modify the mailbox."
    ),
)
def mail_get_message_detail(message_id: str, max_body_chars: int = 20_000) -> str:
    try:
        message_id = (message_id or "").strip()
        if not message_id:
            raise ValueError("message_id is required.")
        return _json_response(_build_message_detail(message_id, max_body_chars=max_body_chars))
    except Exception as exc:
        return _error_response(exc, error_type="mail_get_message_detail_failed")


@mcp.tool(
    name="mail.daily_brief",
    description=(
        "Read the current Gmail summary from the same Kuro Briefing dashboard snapshot. "
        "Use this first for mail priority, required-event, or dashboard mail questions so answers match the panel."
    ),
)
def mail_daily_brief(
    max_results: int = 20,
    newer_than_days: int = 0,
    unread_only: bool = True,
    include_spam_trash: bool = False,
    pet_control_url: str = "",
) -> str:
    try:
        try:
            snapshot = _get_briefing_snapshot(pet_control_url=pet_control_url)
            payload = _mail_payload_from_briefing_snapshot(
                snapshot,
                max_results=max_results,
            )
        except Exception as dashboard_error:
            payload = _build_daily_brief_payload_from_preferences(
                include_spam_trash=include_spam_trash,
            )
            payload["source"] = "live_gmail_preferences_fallback"
            payload["dashboard_error"] = _compact_text(str(dashboard_error), 180)
            payload["next_step"] = (
                "Dashboard snapshot was not available, so this was fetched live using the saved Mail settings."
            )
        return _json_response(payload)
    except Exception as exc:
        return _error_response(exc, error_type="mail_daily_brief_failed")


@mcp.tool(
    name="mail.update_briefing",
    description=(
        "Fetch a Gmail read-only daily brief and update the local Kuro Briefing panel. "
        "Returns only safe update status; it does not expose message contents."
    ),
)
def mail_update_briefing(
    max_results: int = 0,
    newer_than_days: int = 0,
    unread_only: bool = True,
    pet_control_url: str = "",
    include_spam_trash: bool = False,
    use_saved_settings: bool = True,
) -> str:
    try:
        preferences = _load_mail_preferences()
        requested_max_results = _clamp_int(max_results, default=0, minimum=0, maximum=MAX_MAIL_RESULTS)
        requested_newer_than_days = _clamp_int(newer_than_days, default=0, minimum=0, maximum=365)
        effective_max_results = (
            requested_max_results
            if not use_saved_settings and requested_max_results > 0
            else preferences.get("maxResults", DEFAULT_MAIL_PREFERENCES["maxResults"])
        )
        effective_newer_than_days = (
            requested_newer_than_days
            if not use_saved_settings and requested_newer_than_days > 0
            else preferences.get("newerThanDays", DEFAULT_MAIL_PREFERENCES["newerThanDays"])
        )
        effective_unread_only = (
            bool(unread_only)
            if not use_saved_settings
            else bool(preferences.get("unreadOnly", DEFAULT_MAIL_PREFERENCES["unreadOnly"]))
        )
        payload = _build_daily_brief_payload(
            max_results=effective_max_results,
            newer_than_days=effective_newer_than_days,
            unread_only=effective_unread_only,
            include_spam_trash=include_spam_trash,
        )
        post_result = _post_briefing_snapshot(
            payload["briefing_snapshot"],
            pet_control_url=pet_control_url,
        )
        return _json_response(
            {
                "ok": True,
                "account": payload.get("account", ""),
                "query": payload.get("query", ""),
                "resultSizeEstimate": payload.get("resultSizeEstimate", 0),
                "messageCount": len(payload.get("messages") or []),
                "briefing": post_result,
                "privacy": payload.get("privacy", {}),
            }
        )
    except Exception as exc:
        return _error_response(exc, error_type="mail_update_briefing_failed")


if __name__ == "__main__":
    mcp.run()
