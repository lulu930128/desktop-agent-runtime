"""Privacy-bounded comparison of caller-supplied snapshots; no file/Electron IO."""
from collections import Counter
import hashlib
import hmac
from typing import Mapping

from .work_contracts import AttentionLevel, LEVEL_RANK, MAX_WORK_ITEMS, TodayView, identifier

MAX_IDENTITY_SAMPLES = 16
SAFE_SOURCE_LABELS = frozenset({"mail", "study", "calendar", "market", "news", "other"})


def compare_today_shadow(new: TodayView, legacy: Mapping, *, legacy_identity_map: Mapping[str, str],
                         hash_key: bytes, sample_limit: int = 8) -> dict:
    """Map legacy IDs to canonical dedup keys explicitly; never infer identity from text.

    HMAC key is caller-owned (use a per-comparison scope), never emitted. Unknown
    source labels collapse to 'other'. Counts refer to distinct canonical identities;
    repeated legacy identities select the highest attention level, then source label.
    """
    if not isinstance(new, TodayView) or not isinstance(legacy, Mapping):
        raise TypeError("Expected TodayView and legacy snapshot object.")
    if not isinstance(hash_key, bytes) or not 16 <= len(hash_key) <= 64:
        raise ValueError("hash_key must contain 16 to 64 bytes.")
    if type(sample_limit) is not int or not 0 <= sample_limit <= MAX_IDENTITY_SAMPLES:
        raise ValueError("Invalid sample_limit.")
    rows = legacy.get("items")
    if not isinstance(rows, (list, tuple)) or len(rows) > MAX_WORK_ITEMS:
        raise ValueError("Legacy items must be a bounded collection.")
    if not isinstance(legacy_identity_map, Mapping) or len(legacy_identity_map) > MAX_WORK_ITEMS:
        raise ValueError("Invalid bounded legacy identity mapping.")

    def source(value):
        return value if isinstance(value, str) and value in SAFE_SOURCE_LABELS else "other"

    new_items = {item.dedup_key: (item.level, source(item.source)) for item in new.items}
    old_items = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Legacy item must be an object.")
        legacy_id = row.get("id")
        if not isinstance(legacy_id, str) or not 1 <= len(legacy_id) <= 256 or legacy_id not in legacy_identity_map:
            raise ValueError("Every legacy item requires an explicit canonical identity mapping.")
        canonical = identifier("canonical identity", legacy_identity_map[legacy_id])
        try:
            level = AttentionLevel(row.get("level"))
        except (ValueError, TypeError):
            raise ValueError("Invalid legacy attention level.") from None
        entry = (level, source(row.get("source")))
        if canonical not in old_items or (LEVEL_RANK[level], entry[1]) < (LEVEL_RANK[old_items[canonical][0]], old_items[canonical][1]):
            old_items[canonical] = entry

    def counts(items):
        return {"byLevel": {level.value: sum(v[0] is level for v in items.values()) for level in AttentionLevel},
                "bySource": dict(sorted(Counter(v[1] for v in items.values()).items()))}

    def samples(identities):
        return sorted(hmac.new(hash_key, ("kuro.today.shadow.v1:" + identity).encode("utf-8"),
                               hashlib.sha256).hexdigest() for identity in identities)[:sample_limit]

    overlap = new_items.keys() & old_items.keys()
    new_only = new_items.keys() - old_items.keys()
    legacy_only = old_items.keys() - new_items.keys()
    changed = {key for key in overlap if new_items[key][0] != old_items[key][0]}
    transitions = Counter(f"{old_items[key][0].value}->{new_items[key][0].value}" for key in changed)
    return {"contract": "kuro.core.today-shadow.v1", "new": counts(new_items), "legacy": counts(old_items),
            "overlap": len(overlap), "newOnly": len(new_only), "legacyOnly": len(legacy_only),
            "levelChanged": len(changed), "levelTransitions": dict(sorted(transitions.items())),
            "identitySamples": {"overlap": samples(overlap), "newOnly": samples(new_only),
                                "legacyOnly": samples(legacy_only), "levelChanged": samples(changed)}}
