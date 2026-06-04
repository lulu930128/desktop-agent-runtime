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
