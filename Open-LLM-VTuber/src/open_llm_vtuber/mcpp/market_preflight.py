from __future__ import annotations

import json
from typing import Any


OMI_ASK_CONTRACT_VERSION = "omi.ai.ask.v2"


def should_autorun_omi(route: Any) -> bool:
    """Return true when routing has identified OMI as the market data source."""
    if route is None:
        return False

    tool_names = getattr(route, "tool_names", None) or []
    if "omi.ask" not in tool_names:
        return False

    intent = getattr(route, "intent", None)
    return bool(getattr(intent, "needs_market_intelligence", False))


def build_autonomous_omi_args(
    *,
    current_text: str,
    route_text: str,
    last_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only OMI question envelope without doing market parsing in Kuro."""
    conversation_context: dict[str, Any] = {
        "route_text": str(route_text or "").strip(),
    }
    if last_resolution:
        conversation_context["last_resolution"] = last_resolution

    return {
        "contract_version": OMI_ASK_CONTRACT_VERSION,
        "question": _compose_question(
            current_text=current_text,
            route_text=route_text,
        ),
        "target": {"type": "auto"},
        "mode": "auto",
        "caller_profile": "kuro_readonly",
        "allow_llm": True,
        "allow_write": False,
        "allow_external_fetch": True,
        "tool_budget": {
            "max_calls": 5,
            "max_external_fetches": 3,
            "max_total_seconds": 25,
        },
        "conversation_context": conversation_context,
    }


def _compose_question(*, current_text: str, route_text: str) -> str:
    current_text = str(current_text or "").strip()
    route_text = str(route_text or "").strip()
    if current_text and current_text not in route_text:
        question = f"Current user request:\n{current_text}\n\nRecent conversation context:\n{route_text}"
    else:
        question = route_text or current_text

    question = question.strip()
    if len(question) > 3900:
        question = question[-3900:]
    return question


def parse_omi_response_text(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(str(text or ""))
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _compact_text(value: Any, max_len: int = 900) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            value = str(value)
    compact = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip(" ，、。,.!?！？；;:：") + "…"


def _compact_list(values: Any, *, max_items: int = 8, max_len: int = 160) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values[:max_items]:
        text = _compact_text(item, max_len=max_len)
        if text:
            output.append(text)
    return output


def _compact_mapping(
    value: Any,
    keys: tuple[str, ...],
    *,
    max_len: int = 180,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, Any] = {}
    for key in keys:
        item = value.get(key)
        if item is None or item == "":
            continue
        if isinstance(item, (int, float, bool)):
            output[key] = item
        elif isinstance(item, dict):
            output[key] = _compact_mapping(
                item,
                ("type", "id", "label", "market", "name", "status", "date", "as_of"),
                max_len=max_len,
            )
        elif isinstance(item, list):
            output[key] = _compact_list(item, max_items=6, max_len=max_len)
        else:
            output[key] = _compact_text(item, max_len=max_len)
    return output


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _extract_result_data(parsed: dict[str, Any]) -> dict[str, Any]:
    result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return data


def _extract_human_answer_text(
    *,
    parsed: dict[str, Any],
    analysis: dict[str, Any],
    result_data: dict[str, Any],
) -> str:
    human_answer = analysis.get("human_answer")
    if isinstance(human_answer, dict):
        text = str(human_answer.get("text") or "").strip()
        if text:
            return _compact_text(text, max_len=1200)
        lines = human_answer.get("lines")
        if isinstance(lines, list):
            return _compact_text("\n".join(str(line) for line in lines), max_len=1200)

    overview = result_data.get("overview") if isinstance(result_data.get("overview"), dict) else {}
    human_answer = overview.get("human_answer") if isinstance(overview.get("human_answer"), dict) else {}
    text = str(human_answer.get("text") or "").strip()
    if text:
        return _compact_text(text, max_len=1200)
    lines = human_answer.get("lines")
    if isinstance(lines, list):
        return _compact_text("\n".join(str(line) for line in lines), max_len=1200)

    for key in ("human_answer", "answer", "display", "summary"):
        text = str(parsed.get(key) or analysis.get(key) or "").strip()
        if text:
            return _compact_text(text, max_len=1200)
    return ""


def _extract_as_of(
    *,
    parsed: dict[str, Any],
    analysis: dict[str, Any],
    result_data: dict[str, Any],
) -> str:
    freshness = parsed.get("freshness") if isinstance(parsed.get("freshness"), dict) else {}
    overview = result_data.get("overview") if isinstance(result_data.get("overview"), dict) else {}
    candidates = [
        parsed.get("as_of"),
        analysis.get("as_of"),
        overview.get("as_of"),
        freshness.get("as_of"),
        result_data.get("as_of"),
    ]
    for candidate in candidates:
        text = _compact_text(candidate, max_len=80)
        if text:
            return text
    return ""


def build_omi_evidence_snapshot(text: str) -> dict[str, Any] | None:
    parsed = parse_omi_response_text(text)
    if not parsed or parsed.get("contract_version") != OMI_ASK_CONTRACT_VERSION:
        return None

    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    mode = parsed.get("mode") if isinstance(parsed.get("mode"), dict) else {}
    resolution = parsed.get("resolution") if isinstance(parsed.get("resolution"), dict) else {}
    target = _first_mapping(
        resolution.get("target") if isinstance(resolution.get("target"), dict) else {},
        parsed.get("target") if isinstance(parsed.get("target"), dict) else {},
    )
    result_data = _extract_result_data(parsed)
    tool_runs = parsed.get("tool_runs") if isinstance(parsed.get("tool_runs"), list) else []

    evidence = {
        "kind": "omi_evidence",
        "contract_version": OMI_ASK_CONTRACT_VERSION,
        "question": _compact_text(parsed.get("question"), max_len=420),
        "target": _compact_mapping(
            target,
            ("type", "id", "label", "market", "name"),
            max_len=120,
        ),
        "mode": _compact_mapping(mode, ("requested", "effective"), max_len=80),
        "action": _compact_text(parsed.get("action"), max_len=120),
        "report_level": _compact_text(parsed.get("report_level"), max_len=80),
        "answer_ready": bool(parsed.get("answer_ready")),
        "as_of": _extract_as_of(parsed=parsed, analysis=analysis, result_data=result_data),
        "resolution": _compact_mapping(
            resolution,
            ("confidence", "assumption", "target"),
            max_len=180,
        ),
        "analysis": _compact_mapping(
            analysis,
            (
                "kind",
                "display",
                "selected_horizon",
                "horizon_label",
                "selected_timeframe",
                "selected_score",
                "score_display",
                "selected_title",
                "selected_summary",
                "selected_confidence",
                "stance",
                "confidence",
                "as_of",
            ),
            max_len=240,
        ),
        "human_answer": _extract_human_answer_text(
            parsed=parsed,
            analysis=analysis,
            result_data=result_data,
        ),
        "missing": _compact_list(parsed.get("missing"), max_items=12, max_len=120),
        "warnings": _compact_list(parsed.get("warnings"), max_items=8, max_len=180),
        "tool_runs": [
            _compact_mapping(
                run,
                ("tool", "status", "error", "as_of", "message"),
                max_len=180,
            )
            for run in tool_runs[:12]
            if isinstance(run, dict)
        ],
        "source_refs": [
            _compact_mapping(
                ref,
                ("label", "kind", "table", "date", "as_of"),
                max_len=160,
            )
            for ref in (
                parsed.get("source_refs")
                if isinstance(parsed.get("source_refs"), list)
                else []
            )[:8]
            if isinstance(ref, dict)
        ],
    }

    return {
        key: value
        for key, value in evidence.items()
        if value not in ("", [], {}, None)
    }


def format_omi_evidence_for_history(evidence: dict[str, Any], *, max_len: int = 720) -> str:
    if not isinstance(evidence, dict) or evidence.get("kind") != "omi_evidence":
        return ""

    target = _format_target(evidence.get("target"))
    mode = evidence.get("mode") if isinstance(evidence.get("mode"), dict) else {}
    analysis = evidence.get("analysis") if isinstance(evidence.get("analysis"), dict) else {}
    resolution = evidence.get("resolution") if isinstance(evidence.get("resolution"), dict) else {}
    mode_text = mode.get("effective") or mode.get("requested") or evidence.get("report_level") or "unknown"
    parts = [f"OMI evidence: {target}"]
    if evidence.get("as_of"):
        parts.append(f"as_of={evidence.get('as_of')}")
    parts.append(f"mode={mode_text}")
    if resolution.get("confidence"):
        parts.append(f"confidence={resolution.get('confidence')}")
    if analysis.get("display"):
        parts.append(str(analysis.get("display")))
    elif analysis.get("selected_summary"):
        parts.append(str(analysis.get("selected_summary")))
    if evidence.get("human_answer"):
        parts.append(str(evidence.get("human_answer")))
    if evidence.get("warnings"):
        parts.append("warnings=" + " | ".join(str(item) for item in evidence["warnings"][:4]))
    if evidence.get("missing"):
        parts.append("missing=" + ", ".join(str(item) for item in evidence["missing"][:6]))
    return _compact_text(" / ".join(part for part in parts if part), max_len=max_len)


def format_omi_events_for_memory(events: list[dict[str, Any]], *, limit: int = 4) -> str:
    if not events:
        return ""

    lines = ["[Persisted OMI evidence from recent tool calls]"]
    selected = events[-max(1, limit) :]
    for event in selected:
        detail = event.get("detail")
        if isinstance(detail, str):
            detail = parse_omi_response_text(detail) or {}
        if not isinstance(detail, dict):
            continue
        summary = format_omi_evidence_for_history(detail, max_len=520)
        if summary:
            lines.append(f"- {event.get('timestamp') or '-'}: {summary}")
    return "\n".join(lines) if len(lines) > 1 else ""


def extract_omi_resolution_from_tool_results(
    tool_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for result in reversed(tool_results):
        if not isinstance(result, dict):
            continue

        parsed = parse_omi_response_text(str(result.get("content") or ""))
        if not parsed or parsed.get("contract_version") != OMI_ASK_CONTRACT_VERSION:
            continue

        resolution = parsed.get("resolution")
        if isinstance(resolution, dict):
            return resolution

    return None


def format_omi_response_for_llm(text: str) -> str:
    parsed = parse_omi_response_text(text)
    if not parsed or parsed.get("contract_version") != OMI_ASK_CONTRACT_VERSION:
        return str(text or "").strip()

    target = parsed.get("target") if isinstance(parsed.get("target"), dict) else {}
    resolution = parsed.get("resolution") if isinstance(parsed.get("resolution"), dict) else {}
    resolution_target = (
        resolution.get("target")
        if isinstance(resolution.get("target"), dict)
        else target
    )
    mode = parsed.get("mode") if isinstance(parsed.get("mode"), dict) else {}
    clarification = (
        parsed.get("clarification")
        if isinstance(parsed.get("clarification"), dict)
        else {}
    )
    next_actions = parsed.get("next_actions") if isinstance(parsed.get("next_actions"), list) else []
    tool_runs = parsed.get("tool_runs") if isinstance(parsed.get("tool_runs"), list) else []
    tool_plan = parsed.get("tool_plan") if isinstance(parsed.get("tool_plan"), dict) else {}
    missing = parsed.get("missing") if isinstance(parsed.get("missing"), list) else []
    warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []

    target_label = _format_target(resolution_target)
    action_labels = [
        str(action.get("type") or "").strip()
        for action in next_actions
        if isinstance(action, dict) and str(action.get("type") or "").strip()
    ]
    lines = [
        "OMI v2 result summary:",
        f"- target: {target_label}",
        f"- confidence: {resolution.get('confidence') or 'unknown'}",
        f"- mode: {mode.get('requested') or 'unknown'} -> {mode.get('effective') or 'unknown'}",
        f"- report_level: {parsed.get('report_level') or 'unknown'}",
        f"- answer_ready: {bool(parsed.get('answer_ready'))}",
    ]

    assumption = str(resolution.get("assumption") or "").strip()
    if assumption:
        lines.append(f"- assumption: {assumption}")

    if clarification.get("required"):
        lines.append(f"- clarification_required: {clarification.get('question')}")

    if missing:
        lines.append(f"- missing: {', '.join(str(item) for item in missing[:12])}")

    if warnings:
        lines.append(f"- warnings: {' | '.join(str(item) for item in warnings[:5])}")

    if action_labels:
        lines.append(f"- next_actions: {', '.join(action_labels[:8])}")

    if tool_plan:
        lines.append(f"- tool_plan_provider: {tool_plan.get('provider') or 'unknown'}")

    if tool_runs:
        run_labels = []
        for run in tool_runs[:8]:
            if not isinstance(run, dict):
                continue
            tool_name = str(run.get("tool") or "").strip()
            status = str(run.get("status") or "").strip()
            error = str(run.get("error") or "").strip()
            label = f"{tool_name}:{status}" if status else tool_name
            if error:
                label = f"{label} ({error})"
            if label:
                run_labels.append(label)
        if run_labels:
            lines.append(f"- tool_runs: {' | '.join(run_labels)}")

    lines.append("\nRaw OMI v2 JSON:")
    lines.append(json.dumps(parsed, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines)


def _format_target(target: Any) -> str:
    if not isinstance(target, dict):
        return "unknown"

    target_type = str(target.get("type") or "unknown")
    target_id = str(target.get("id") or "").strip()
    label = str(target.get("label") or "").strip()
    market = str(target.get("market") or "").strip()
    parts = [target_type]
    if target_id:
        parts.append(target_id)
    if label:
        parts.append(label)
    if market:
        parts.append(f"market={market}")
    return " ".join(parts)
