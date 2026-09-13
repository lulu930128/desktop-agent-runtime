"""Stable server-owned identities. Legacy owners are pinned, never discovered."""
import hashlib
import re
from urllib.parse import quote

LEGACY_OWNERS = {
    **dict.fromkeys(("get_current_time", "search_web", "smart_search_web", "advanced_search_web", "fetch_content"), "kuro-web"),
    **dict.fromkeys(("list_allowed_roots", "list_directory", "search_files", "read_text_file", "search_past_conversations"), "kuro-filesystem"),
    **dict.fromkeys(("mail.auth_status", "mail.auth_start", "mail.auth_finish", "mail.list_unread", "mail.search_recent", "mail.get_message_summary", "mail.get_message_detail", "mail.daily_brief", "mail.update_briefing"), "kuro-mail"),
    **dict.fromkeys(("omi.ask", "omi.ask_stream", "omi.read_refresh_status", "omi.read_taiwan_bars", "omi.read_taiwan_technical_series", "omi.read_taiwan_chart"), "omi-market"),
}


def canonical_id(server: str, name: str) -> str:
    if not isinstance(server, str) or not isinstance(name, str) or not server or not name:
        raise ValueError("Missing tool identity.")
    return f"{quote(server, safe='-_.')}::{quote(name, safe='-_.')}"


def legacy_canonical(name: str) -> str:
    owner = LEGACY_OWNERS.get(name)
    return canonical_id(owner, name) if owner else name


def legacy_name(name: str) -> str:
    for raw, owner in LEGACY_OWNERS.items():
        if canonical_id(owner, raw) == name:
            return raw
    return name


def provider_alias(identity: str) -> str:
    prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", identity)[:43]
    return f"{prefix}_{hashlib.sha256(identity.encode()).hexdigest()[:20]}"
