"""Source-bound semantic candidates for completed user turns. No external model calls."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
import json
import re
from .memory_semantics import local_encoder

PROTOTYPES = {
    "preference": (
        "I prefer tea over coffee.",
        "我平常都喝無糖茶。",
        "I dislike noisy offices.",
    ),
    "experience": (
        "Yesterday I went to a museum.",
        "我上週搬到了新公寓。",
        "I took a pottery class last weekend.",
    ),
    "goal": (
        "I want to learn a new language.",
        "我的目標是完成今年的馬拉松。",
        "I plan to learn woodworking.",
    ),
    "other": (
        "What would happen if I moved?",
        "Can you run this tool?",
        "幫我修改設定。",
        "The stock price changed.",
    ),
}


def read_policy(repository, character, project):
    path = repository.root() / "formation-policy.json"
    if not path.is_file():
        return None
    policy = json.loads(path.read_bytes())
    if policy.get("version") != 2 or policy.get("mode") != "scoped_auto":
        return None
    for rule in policy.get("rules", []):
        if (
            rule.get("source") == "user_statement"
            and rule.get("character_id") == character
            and rule.get("project_id") == project
            and rule.get("scope") in {"character", "global_user", "project"}
            and isinstance(rule.get("categories"), list)
            and set(rule["categories"]) <= PROTOTYPES.keys() - {"other"}
            and (rule["scope"] != "project" or project)
        ):
            return rule
    return None


def configure_policy(
    repository, character, project, *, categories, scope, expected_digest
):
    """One native user decision, bound to actor, project, and previous grant revision."""
    from .character_memory_repository import store_lock
    from .character_memory_lifecycle import review_digest
    from .chat_history_manager import _write_history
    import uuid

    if (
        not character
        or scope not in {"character", "global_user", "project"}
        or scope == "project"
        and not project
        or not isinstance(categories, list)
        or any(c not in {"preference", "experience", "goal"} for c in categories)
    ):
        raise ValueError("Invalid memory formation selection")
    path = repository.root() / "formation-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with store_lock(path):
        previous = read_policy(repository, character, project)
        if (review_digest(previous) if previous else "") != expected_digest:
            raise ValueError("Memory formation policy changed since review")
        policy = (
            json.loads(path.read_bytes())
            if path.exists()
            else {"version": 2, "mode": "scoped_auto", "rules": []}
        )
        if policy.get("version") != 2 or not isinstance(policy.get("rules"), list):
            raise ValueError("Unknown memory formation policy version")
        rules = [
            r
            for r in policy["rules"]
            if (r.get("character_id"), r.get("project_id")) != (character, project)
        ]
        if categories:
            rules.append(
                dict(
                    character_id=character,
                    project_id=project,
                    scope=scope,
                    source="user_statement",
                    categories=sorted(set(categories)),
                    revision=uuid.uuid4().hex,
                )
            )
        policy.update(mode="scoped_auto" if rules else "manual", rules=rules)
        _write_history(path, policy)


@lru_cache(maxsize=1)
def _prototypes(encoder):
    phrases = [
        (category, phrase)
        for category, examples in PROTOTYPES.items()
        for phrase in examples
    ]
    return [category for category, _ in phrases], encoder.encode(
        [phrase for _, phrase in phrases]
    )


def semantic_spans(text, rule, *, history, turn, observed):
    # Keep quoted/conditional context together to avoid converting a subordinate
    # claim into an independent fact. Long monologues may contain multiple facts.
    if re.search(
        r'[「」『』"“”]|如果|假如|假設|もし|\b(if|suppose|would|said|pretend)\b',
        text,
        re.I,
    ):
        return []
    spans = [text] if len(text) <= 260 else re.split(r"(?<=[。！？.!?])\s*|\n+", text)
    found = []
    offset = 0
    for span in spans:
        start = text.find(span, offset)
        offset = start + len(span)
        candidate = semantic_candidate(
            span.strip(), rule, history=history, turn=turn, observed=observed
        )
        if candidate:
            candidate["evidence"]["character_span"] = [start, offset]
            if len(spans) > 1 and candidate["subject"] == "experience":
                candidate["key"] = f"{turn}:{start}"
            found.append(candidate)
    return found


def semantic_candidate(text, rule, *, history, turn, observed):
    if not turn or not history or not observed or len(text) > 260:
        return None
    if not re.search(r"我|私|僕|\b(?:I|my)\b", text, re.I):
        return None
    if re.search(
        r"[?？「」『』\"\n]|如果|假設|據說|你說|請|幫我|系統|指令|執行|假如|としたら|もし|\b(if|suppose|would|said|please|execute|ignore|system|pretend)\b",
        text,
        re.I,
    ):
        return None
    encoder = local_encoder()
    if not encoder:
        return None
    labels, matrix = _prototypes(encoder)
    scores = matrix @ encoder.encode([text])[0]
    best = int(scores.argmax())
    category = labels[best]
    allowed = rule["categories"] if rule else {"preference", "experience", "goal"}
    if category not in allowed or scores[best] < 0.46:
        return None
    event_date = ""
    for word, days in (
        ("昨天", -1),
        ("昨日", -1),
        ("yesterday", -1),
        ("明天", 1),
        ("明日", 1),
        ("tomorrow", 1),
        ("今天", 0),
        ("今日", 0),
        ("today", 0),
    ):
        if word in text.lower():
            event_date = (
                datetime.fromisoformat(observed).date() + timedelta(days=days)
            ).isoformat()
            break
    facet = ""
    if category == "preference" and re.search(
        r"平常|平時|習慣|改喝|首選|usually|go-to|default|instead|now prefer|普段|いつも",
        text,
        re.I,
    ):
        if re.search(r"喝|飲み|飲む|茶|咖啡|coffee|tea|drink", text, re.I):
            facet = "usual_beverage"
    unique_key = (
        turn if category == "experience" else hashlib.sha256(text.encode()).hexdigest()
    )
    return {
        "content": text,
        "source": "user_statement",
        "status": "active" if rule else "pending_confirmation",
        "memory_type": "preference" if category == "preference" else "fact",
        "subject": category,
        "key": facet or unique_key,
        "scope_level": rule["scope"] if rule else "character",
        "confidence": float(scores[best]),
        "evidence": {
            "formation": "semantic-v1",
            "model": encoder.revision,
            "category": category,
            "event_date": event_date,
            "verification_status": "user_reported",
            "rule_digest": hashlib.sha256(
                json.dumps(rule, sort_keys=True).encode()
            ).hexdigest()
            if rule
            else "",
        },
    }
