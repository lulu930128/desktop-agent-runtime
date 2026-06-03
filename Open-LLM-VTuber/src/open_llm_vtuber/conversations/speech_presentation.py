from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


SPEECH_ROUTE_SILENT_DISPLAY = "silent_display"
SPEECH_ROUTE_RENDER_THEN_TTS = "render_then_tts"
SPEECH_PLAN_SOURCE = "source"
SPEECH_PLAN_FIXED_JA = "fixed_ja"
SPEECH_PLAN_SKIP = "skip"
SPEECH_POLICY_CODE_JA = "コードは画面に表示しました。"
SPEECH_POLICY_TABLE_JA = "表にまとめて画面に表示しました。"
SPEECH_POLICY_URL_JA = "参考リンクは画面に表示しています。"
SPEECH_POLICY_ERROR_JA = "システムでエラーが出ました。詳細は画面に表示しています。"
SPEECH_POLICY_STOCK_NUMBERS_JA = "詳しい数字は画面に出しています。"
SPEECH_POLICY_OPTIONS_JA = "選択肢は画面に表示しています。"
SPEECH_POLICY_DETAIL_ITEMS_JA = "詳しい項目は画面に表示しています。"


def _clip_text(text: str, max_len: int | None) -> str:
    value = str(text or "")
    if max_len is None or len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "..."


@dataclass(frozen=True)
class SpeechPolicyConfig:
    """Runtime knobs for speech routing.

    The hard safety decisions stay in code. A future YAML layer should only
    populate this config and pronunciation/profile dictionaries.
    """

    response_type: str = "chat"
    allow_tts: bool = True
    max_spoken_segments: int = 3


@dataclass(frozen=True)
class SpeechPlanItem:
    kind: str
    text: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": str(self.kind or ""),
            "text": str(self.text or "").strip(),
            "reason": str(self.reason or ""),
        }


def speech_plan_item(kind: str, text: str = "", reason: str = "") -> dict[str, str]:
    return SpeechPlanItem(kind=kind, text=text, reason=reason).to_dict()


def _is_question(text: str) -> bool:
    value = str(text or "").strip()
    return value.endswith(("?", "？"))


def _is_list_intro(text: str) -> bool:
    value = str(text or "").strip()
    return value.endswith((":", "："))


def _looks_like_inline_detail_items(text: str) -> bool:
    value = str(text or "")
    if "：" in value:
        _, detail = value.split("：", 1)
    elif ":" in value:
        _, detail = value.split(":", 1)
    else:
        return False
    separators = sum(detail.count(mark) for mark in ("、", "，", ",", "/", "／"))
    detail_keywords = (
        "營收",
        "毛利",
        "EPS",
        "資本支出",
        "股價",
        "市值",
        "財報",
        "製程",
        "產能",
        "技術節點",
        "指標",
    )
    return separators >= 3 and any(keyword in detail for keyword in detail_keywords)


def _trim_inline_detail_items(text: str) -> str:
    value = str(text or "").strip()
    if "：" in value:
        head, _detail = value.split("：", 1)
    elif ":" in value:
        head, _detail = value.split(":", 1)
    else:
        return value
    head = head.strip()
    if not head:
        return ""
    if "並列出每年" in head:
        head = head.split("並列出每年", 1)[0].rstrip("，,、；; ")
    return f"{head}。" if not head.endswith(("。", "？", "！", "?", "!")) else head


def _extract_inline_detail_followup(text: str) -> str:
    value = str(text or "")
    if "：" in value:
        _head, detail = value.split("：", 1)
    elif ":" in value:
        _head, detail = value.split(":", 1)
    else:
        return ""

    matches = list(
        re.finditer(
            r"(?:^|[；;。])\s*((?:或|還是|要|是否|需不需要|要不要|你要)[^？?]{1,80}[？?])",
            detail,
        )
    )
    if not matches:
        return ""
    return str(matches[-1].group(1) or "").strip()


def normalize_speech_plan_for_presentation(
    plan: list[dict[str, str]],
    *,
    max_spoken_segments: int = 3,
) -> list[dict[str, str]]:
    """Prune display-oriented detail into a compact, speakable presentation plan.

    This is not summarization of the visible answer. It only decides which blocks
    should reach the voice lane: normal conversational lines stay speakable,
    while option lists and dense detail lists stay on screen.
    """
    if not plan:
        return []

    items = [dict(item) for item in plan if dict(item).get("kind") != SPEECH_PLAN_SKIP]
    choice_count = sum(1 for item in items if item.get("reason") == "choice_item")
    has_choices = choice_count >= 2
    result: list[dict[str, str]] = []
    inserted_options_line = False
    inserted_detail_line = False

    for item in items:
        kind = item.get("kind", "")
        text = str(item.get("text") or "").strip()
        reason = item.get("reason", "")
        if not text:
            continue

        if has_choices and reason == "choice_item":
            if _is_question(text):
                result.append(speech_plan_item(SPEECH_PLAN_SOURCE, text, "source"))
                continue
            if not inserted_options_line:
                result.append(
                    speech_plan_item(
                        SPEECH_PLAN_FIXED_JA,
                        SPEECH_POLICY_OPTIONS_JA,
                        "choice_options_displayed",
                    )
                )
                inserted_options_line = True
            continue

        if kind == SPEECH_PLAN_SOURCE and _looks_like_inline_detail_items(text):
            trimmed = _trim_inline_detail_items(text)
            followup = _extract_inline_detail_followup(text)
            if trimmed:
                result.append(speech_plan_item(SPEECH_PLAN_SOURCE, trimmed, reason))
            if not inserted_detail_line:
                result.append(
                    speech_plan_item(
                        SPEECH_PLAN_FIXED_JA,
                        SPEECH_POLICY_DETAIL_ITEMS_JA,
                        "detail_items_displayed",
                    )
                )
                inserted_detail_line = True
            if followup:
                result.append(speech_plan_item(SPEECH_PLAN_SOURCE, followup, reason))
            continue

        result.append(speech_plan_item(kind, text, reason))

    if len(result) <= max_spoken_segments:
        return result

    # Keep natural dialogue shape: leading question/intro, one display notice, final question.
    priority: list[dict[str, str]] = []
    for item in result:
        if item.get("kind") == SPEECH_PLAN_SOURCE and _is_question(
            item.get("text", "")
        ):
            priority.append(item)
            break
    if not priority and result:
        priority.append(result[0])

    for item in result:
        if item.get("kind") == SPEECH_PLAN_FIXED_JA and item not in priority:
            priority.append(item)
            break

    final_question = next(
        (
            item
            for item in reversed(result)
            if item.get("kind") == SPEECH_PLAN_SOURCE
            and _is_question(item.get("text", ""))
            and item not in priority
        ),
        None,
    )
    if final_question is not None:
        priority.append(final_question)

    if len(priority) < max_spoken_segments:
        for item in result:
            if item in priority:
                continue
            if item.get("kind") == SPEECH_PLAN_SOURCE and _is_list_intro(
                item.get("text", "")
            ):
                priority.append(item)
                break

    return priority[:max_spoken_segments]


@dataclass
class SpeechSegment:
    source_text: str = ""
    rendered_text: str = ""
    spoken_text: str = ""
    guard_reason: str = "not_rendered"
    provider: str = ""
    pronunciation_hits: list[str] = field(default_factory=list)
    speech_repaired: bool = False
    route: str = SPEECH_ROUTE_SILENT_DISPLAY

    def to_dict(self, *, max_text_len: int | None = None) -> dict[str, Any]:
        return {
            "route": self.route,
            "source_text": _clip_text(self.source_text, max_text_len),
            "rendered_text": _clip_text(self.rendered_text, max_text_len),
            "spoken_text": _clip_text(self.spoken_text, max_text_len),
            "guard_reason": self.guard_reason,
            "provider": self.provider,
            "pronunciation_hits": list(self.pronunciation_hits),
            "speech_repaired": self.speech_repaired,
        }


@dataclass
class PresentationEnvelope:
    """Separated presentation lanes for one assistant response.

    raw_content: original model/tool text before display cleanup.
    display_text: text shown in the chat/subtitle UI.
    speech_source: sanitized source sent to the spoken renderer.
    spoken_text: final text allowed to reach the TTS engine.

    expression_hint is intentionally only a route placeholder for now; the
    existing emotion behavior remains unchanged until an expression mapper is
    introduced.
    """

    raw_content: str = ""
    display_text: str = ""
    response_type: str = "chat"
    speech_route: str = SPEECH_ROUTE_SILENT_DISPLAY
    speech_source: str = ""
    spoken_text: str = ""
    speech_guard_reason: str = "not_rendered"
    speech_segments: list[SpeechSegment] = field(default_factory=list)
    expression_hint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def append_display(self, *, raw_text: str, display_text: str) -> None:
        self.raw_content += str(raw_text or "")
        self.display_text += str(display_text or "")

    def set_speech_source(
        self,
        source_text: str,
        *,
        route: str,
        guard_reason: str,
    ) -> None:
        self.speech_source = str(source_text or "").strip()
        self.speech_route = route
        self.speech_guard_reason = guard_reason

    def attach_speech_result(
        self,
        *,
        rendered_text: str,
        spoken_text: str,
        guard_reason: str,
        provider: str = "",
        pronunciation_hits: list[str] | None = None,
        speech_repaired: bool = False,
    ) -> SpeechSegment:
        self.spoken_text = str(spoken_text or "").strip()
        self.speech_guard_reason = guard_reason or "unknown"
        if self.speech_source:
            self.speech_route = SPEECH_ROUTE_RENDER_THEN_TTS
        else:
            self.speech_route = SPEECH_ROUTE_SILENT_DISPLAY

        segment = SpeechSegment(
            source_text=self.speech_source,
            rendered_text=str(rendered_text or "").strip(),
            spoken_text=self.spoken_text,
            guard_reason=self.speech_guard_reason,
            provider=str(provider or ""),
            pronunciation_hits=list(pronunciation_hits or []),
            speech_repaired=bool(speech_repaired),
            route=self.speech_route,
        )
        self.speech_segments = [segment]
        return segment

    def to_log_dict(self, *, max_text_len: int | None = None) -> dict[str, Any]:
        return {
            "response_type": self.response_type,
            "speech_route": self.speech_route,
            "speech_guard_reason": self.speech_guard_reason,
            "raw_content": _clip_text(self.raw_content, max_text_len),
            "display_text": _clip_text(self.display_text, max_text_len),
            "speech_source": _clip_text(self.speech_source, max_text_len),
            "spoken_text": _clip_text(self.spoken_text, max_text_len),
            "expression_hint": self.expression_hint,
            "metadata": dict(self.metadata),
            "speech_segments": [
                segment.to_dict(max_text_len=max_text_len)
                for segment in self.speech_segments
            ],
        }


class SpeechPolicyEngine:
    """Small routing facade between display text, speech renderer, and TTS."""

    def __init__(self, config: SpeechPolicyConfig | None = None) -> None:
        self.config = config or SpeechPolicyConfig()

    def create_envelope(
        self, *, response_type: str | None = None
    ) -> PresentationEnvelope:
        return PresentationEnvelope(
            response_type=response_type or self.config.response_type
        )

    def set_source(self, envelope: PresentationEnvelope, source_text: str) -> None:
        source = str(source_text or "").strip()
        if not self.config.allow_tts:
            envelope.set_speech_source(
                "",
                route=SPEECH_ROUTE_SILENT_DISPLAY,
                guard_reason="tts_disabled",
            )
            return
        if not source:
            envelope.set_speech_source(
                "",
                route=SPEECH_ROUTE_SILENT_DISPLAY,
                guard_reason="empty_source",
            )
            return
        envelope.set_speech_source(
            source,
            route=SPEECH_ROUTE_RENDER_THEN_TTS,
            guard_reason="ready",
        )
