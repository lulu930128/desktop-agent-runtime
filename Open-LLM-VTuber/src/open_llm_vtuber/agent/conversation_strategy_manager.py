import json
import os
from pathlib import Path
from typing import Any

from loguru import logger


class ConversationStrategy:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data if isinstance(data, dict) else {}
        strategies = self.data.get("strategies")
        self.strategies = strategies if isinstance(strategies, dict) else {}

    @classmethod
    def load_default(cls) -> "ConversationStrategy":
        path = _default_strategy_path()
        if path and path.exists():
            try:
                return cls(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning(f"Failed to load conversation strategies from {path}: {exc}")
        return cls(
            {
                "version": 1,
                "strategies": {
                    "normal": {
                        "title": "Normal",
                        "description": "Balanced reasoning for everyday assistant work.",
                        "rules": [
                            "Lead with the answer or recommendation.",
                            "Include only the necessary supporting details.",
                        ],
                    }
                },
            }
        )

    def render(self, thinking_power: str) -> str:
        mode = normalize_thinking_power(thinking_power)
        strategy = self.strategies.get(mode)
        if not isinstance(strategy, dict):
            strategy = self.strategies.get("normal", {})

        title = str(strategy.get("title") or mode).strip()
        description = str(strategy.get("description") or "").strip()
        rules = strategy.get("rules") if isinstance(strategy.get("rules"), list) else []

        lines = [
            f"thinking_power: {mode}",
            f"strategy: {title}",
        ]
        if description:
            lines.append(f"description: {description}")
        if rules:
            lines.append("rules:")
            lines.extend(f"- {str(rule).strip()}" for rule in rules if str(rule).strip())
        lines.append("This controls reasoning style, not character identity.")
        return "\n".join(lines).strip()


def normalize_thinking_power(value: str) -> str:
    normalized = (value or "normal").strip().lower()
    aliases = {
        "quick": "fast",
        "light": "fast",
        "fast": "fast",
        "normal": "normal",
        "medium": "normal",
        "default": "normal",
        "deep": "deep",
        "depth": "deep",
        "high": "deep",
    }
    return aliases.get(normalized, "normal")


def _default_strategy_path() -> Path | None:
    env_path = os.getenv("KURO_CONVERSATION_STRATEGY_PATH", "").strip()
    if env_path:
        return Path(env_path)

    candidates = [
        Path.cwd() / "conversation_strategies.json",
        Path(__file__).resolve().parents[3] / "conversation_strategies.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]
