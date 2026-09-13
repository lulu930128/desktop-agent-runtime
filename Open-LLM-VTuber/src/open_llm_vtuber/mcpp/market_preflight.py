from __future__ import annotations

import asyncio
from .tool_identity import legacy_name
from .privacy import project, safe_text
from .tool_result import ToolResult
from collections.abc import AsyncIterator, Iterator
import datetime
import json
import os
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OMI_ASK_CONTRACT_VERSION = "omi.decision.v4"
OMI_PREVIOUS_CONTRACT_VERSION = "omi.decision.v3"
OMI_LEGACY_CONTRACT_VERSION = "omi.ai.ask.v2"
OMI_ASK_STREAM_TOOL_NAME = "omi.ask_stream"
OMI_AUTONOMOUS_TOOL_ID = "autonomous_omi_preflight"


def should_autorun_omi(route: Any) -> bool:
    """Return true when routing has identified OMI as the market data source."""
    if route is None:
        return False

    tool_names = [legacy_name(name) for name in (getattr(route, "tool_names", None) or [])]
    if "omi.ask" not in tool_names and OMI_ASK_STREAM_TOOL_NAME not in tool_names:
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
        "output": "decision_with_evidence",
        "realtime_policy": "prefer_live",
        "selection": {"max_response_bytes": 65_536},
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


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _omi_api_base_url() -> str:
    return os.environ.get("OMI_API_BASE_URL", "http://127.0.0.1:8400").rstrip("/")


def _omi_api_timeout_seconds() -> int:
    return _env_int("OMI_API_TIMEOUT_SECONDS", 180)


def _omi_ai_trust_token() -> str:
    return (
        os.environ.get("OMI_MCP_AI_TRUST_TOKEN")
        or os.environ.get("OMI_AI_TRUST_TOKEN")
        or ""
    ).strip()


def _utc_timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def iter_omi_sse_events_from_lines(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    event_name = "message"
    data_lines: list[str] = []
    total_bytes = 0

    def build_event() -> dict[str, Any] | None:
        nonlocal event_name, data_lines
        if not data_lines and event_name == "message":
            return None

        data_text = "\n".join(data_lines)
        try:
            data: Any = json.loads(data_text) if data_text else {}
        except json.JSONDecodeError:
            data = {"text": data_text}

        event = {"event": event_name, "data": data}
        event_name = "message"
        data_lines = []
        return event

    for raw_line in lines:
        total_bytes += len(str(raw_line).encode("utf-8"))
        if total_bytes > 8 * 1024 * 1024:
            raise ValueError("OMI stream exceeded its byte limit.")
        line = str(raw_line).rstrip("\r\n")
        if not line:
            event = build_event()
            if event:
                yield event
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())

    event = build_event()
    if event:
        yield event


def _iter_omi_sse_http_events(arguments: dict[str, Any]) -> Iterator[dict[str, Any]]:
    payload = json.dumps(arguments, ensure_ascii=False, default=str).encode("utf-8")
    headers = {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "kuro-omi-preflight/0.1",
    }
    trust_token = _omi_ai_trust_token()
    if trust_token:
        headers["X-OMI-AI-Trust-Token"] = trust_token

    request = Request(
        f"{_omi_api_base_url()}/api/ai/ask/stream",
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=_omi_api_timeout_seconds()) as response:
            def bounded_lines():
                while True:
                    raw_line = response.readline(256 * 1024 + 1)
                    if not raw_line:
                        break
                    if len(raw_line) > 256 * 1024:
                        raise ValueError("OMI stream line exceeded its byte limit.")
                    yield raw_line.decode("utf-8", errors="replace")
            lines = bounded_lines()
            yield from iter_omi_sse_events_from_lines(lines)
    except HTTPError as exc:
        raise RuntimeError(f"OMI API HTTP {exc.code}; response body omitted.") from None
    except URLError as exc:
        raise RuntimeError("OMI API unavailable; transport details omitted.") from None


async def stream_omi_ask_events(arguments: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=64)
    stopped = threading.Event()

    def enqueue(item: dict[str, Any] | None) -> bool:
        if stopped.is_set():
            return False
        pending = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
        while not stopped.is_set():
            try:
                pending.result(timeout=0.2)
                return True
            except FutureTimeout:
                continue
        pending.cancel()
        return False

    def worker() -> None:
        try:
            for event in _iter_omi_sse_http_events(arguments):
                if not enqueue(project(event)):
                    break
        except Exception as exc:
            enqueue(
                {
                    "event": "transport_error",
                    "data": {
                        "error": "OMI transport failed; execution outcome unknown.",
                        "kind": exc.__class__.__name__,
                    },
                }
            )
        finally:
            enqueue(None)

    threading.Thread(target=worker, name="kuro-omi-sse", daemon=True).start()

    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        stopped.set()


def _stream_event_data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") if isinstance(event, dict) else {}
    return data if isinstance(data, dict) else {"value": data}


def _stream_event_json(data: dict[str, Any]) -> str:
    return ToolResult(structured_content=project(data)).model_text(limit=65536)


def _compact_stream_summary(data: dict[str, Any], *, max_len: int = 520) -> str:
    return _compact_text(data, max_len=max_len)


def format_omi_stream_status_update(
    event: dict[str, Any],
    *,
    tool_id: str = OMI_AUTONOMOUS_TOOL_ID,
) -> dict[str, Any] | None:
    event = project(event)
    event_type = str(event.get("event") or "message").strip()
    data = _stream_event_data(event)
    base = {
        "type": "tool_call_status",
        "tool_id": tool_id,
        "tool_name": OMI_ASK_STREAM_TOOL_NAME,
        "timestamp": _utc_timestamp(),
    }

    if event_type == "status":
        stage = str(data.get("stage") or "").strip()
        message = str(data.get("message") or "").strip()
        content = message or f"OMI status: {stage or 'running'}"
        return {**base, "status": "running", "content": content}

    if event_type == "evidence":
        parts = ["OMI 證據護照"]
        trust_level = data.get("trust_level")
        trust_score = data.get("trust_score")
        freshness = data.get("data_freshness")
        source_grade = data.get("source_grade")
        if trust_level:
            parts.append(f"trust={trust_level}")
        if trust_score is not None:
            parts.append(f"score={trust_score}")
        if freshness:
            parts.append(f"freshness={freshness}")
        if source_grade:
            parts.append(f"source={source_grade}")
        summary = str(data.get("summary") or "").strip()
        if summary:
            parts.append(summary)
        return {**base, "status": "running", "content": " / ".join(parts)}

    if event_type == "tool_run":
        tool_name = str(data.get("tool") or data.get("name") or "tool").strip()
        status = str(data.get("status") or "running").strip()
        detail = str(data.get("message") or data.get("error") or "").strip()
        content = f"OMI tool run: {tool_name}:{status}"
        if detail:
            content = f"{content} - {_compact_text(detail, max_len=260)}"
        return {**base, "status": "running", "content": content}

    if event_type == "delta":
        text = str(data.get("text") or "").strip()
        if not text:
            return None
        return {**base, "status": "running", "content": text}

    if event_type == "final":
        ok = data.get("ok") is not False
        return {
            **base,
            "status": "completed" if ok else "error",
            "content": safe_text(_stream_event_json(data), limit=2048),
            "omi_evidence": build_omi_evidence_snapshot(json.dumps(data, ensure_ascii=False)),
        }

    if event_type in {"error", "transport_error"}:
        return {
            **base,
            "status": "error",
            "content": _compact_stream_summary(data),
        }

    if event_type == "done" and data.get("ok") is False:
        return {
            **base,
            "status": "error",
            "content": "OMI stream finished without a successful result.",
        }

    return None


def format_omi_stream_final_tool_result(
    events: list[dict[str, Any]],
    *,
    tool_id: str = OMI_AUTONOMOUS_TOOL_ID,
) -> dict[str, Any] | None:
    final_data: dict[str, Any] | None = None
    error_data: dict[str, Any] | None = None
    delta_parts: list[str] = []
    for event in events:
        event = project(event)
        event_type = str(event.get("event") or "").strip()
        data = _stream_event_data(event)
        if event_type == "final":
            final_data = data
        elif event_type in {"error", "transport_error"}:
            error_data = data
        elif event_type == "delta":
            text = data.get("text")
            if isinstance(text, str):
                delta_parts.append(text)

    if final_data:
        return {
            "tool_id": tool_id,
            "content": _stream_event_json(final_data),
            "is_error": final_data.get("ok") is False,
        }

    if error_data:
        return {
            "tool_id": tool_id,
            "content": _compact_stream_summary(error_data, max_len=1200),
            "is_error": True,
        }

    if delta_parts:
        return {
            "tool_id": tool_id,
            "content": "OMI stream incomplete; no final result. " + _compact_text("".join(delta_parts), max_len=1600),
            "is_error": True,
        }

    return None


def parse_omi_response_text(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(str(text or ""))
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _compact_text(value: Any, max_len: int = 900) -> str:
    if value is None:
        return ""
    value = project(value)
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


def _is_supported_omi_contract(parsed: dict[str, Any]) -> bool:
    return parsed.get("contract_version") in {
        OMI_ASK_CONTRACT_VERSION,
        OMI_PREVIOUS_CONTRACT_VERSION,
        OMI_LEGACY_CONTRACT_VERSION,
    }


def _extract_result_data(parsed: dict[str, Any]) -> dict[str, Any]:
    evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), dict) else {}
    canonical_result = (
        evidence.get("result")
        if isinstance(evidence.get("result"), dict)
        else {}
    )
    if canonical_result:
        canonical_data = (
            canonical_result.get("data")
            if isinstance(canonical_result.get("data"), dict)
            else {}
        )
        return canonical_data

    result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return data


def _extract_human_answer_text(
    *,
    parsed: dict[str, Any],
    analysis: dict[str, Any],
    result_data: dict[str, Any],
) -> str:
    canonical_answer = (
        parsed.get("answer")
        if isinstance(parsed.get("answer"), dict)
        else {}
    )
    for key in ("text", "detail", "headline"):
        text = str(canonical_answer.get(key) or "").strip()
        if text:
            return _compact_text(text, max_len=1200)
    canonical_summary = canonical_answer.get("summary")
    if isinstance(canonical_summary, list):
        text = "\n".join(str(line) for line in canonical_summary if str(line).strip())
        if text:
            return _compact_text(text, max_len=1200)

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
    canonical_evidence = (
        parsed.get("evidence")
        if isinstance(parsed.get("evidence"), dict)
        else {}
    )
    freshness = _first_mapping(
        canonical_evidence.get("freshness"),
        parsed.get("freshness"),
    )
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
    if not parsed or not _is_supported_omi_contract(parsed):
        return None

    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    mode = parsed.get("mode") if isinstance(parsed.get("mode"), dict) else {}
    continuation = (
        parsed.get("continuation")
        if isinstance(parsed.get("continuation"), dict)
        else {}
    )
    resolution = _first_mapping(
        continuation.get("resolution"),
        parsed.get("resolution"),
    )
    target = _first_mapping(
        resolution.get("target") if isinstance(resolution.get("target"), dict) else {},
        parsed.get("target") if isinstance(parsed.get("target"), dict) else {},
    )
    result_data = _extract_result_data(parsed)
    execution = (
        parsed.get("execution")
        if isinstance(parsed.get("execution"), dict)
        else {}
    )
    status = parsed.get("status") if isinstance(parsed.get("status"), dict) else {}
    readiness = (
        status.get("readiness")
        if isinstance(status.get("readiness"), dict)
        else {}
    )
    limitations = (
        parsed.get("limitations")
        if isinstance(parsed.get("limitations"), dict)
        else {}
    )
    canonical_evidence = (
        parsed.get("evidence")
        if isinstance(parsed.get("evidence"), dict)
        else {}
    )
    tool_runs = execution.get("tool_runs")
    if not isinstance(tool_runs, list):
        tool_runs = parsed.get("tool_runs")
    if not isinstance(tool_runs, list):
        tool_runs = []
    decision = parsed.get("decision") if isinstance(parsed.get("decision"), dict) else {}

    evidence = {
        "kind": "omi_evidence",
        "contract_version": parsed.get("contract_version"),
        "question": _compact_text(parsed.get("question"), max_len=420),
        "target": _compact_mapping(
            target,
            ("type", "id", "label", "market", "name"),
            max_len=120,
        ),
        "mode": _compact_mapping(mode, ("requested", "effective", "response"), max_len=80),
        "action": _compact_text(parsed.get("action"), max_len=120),
        "report_level": _compact_text(
            execution.get("report_level") or parsed.get("report_level"),
            max_len=80,
        ),
        "answer_ready": bool(
            readiness.get("answer_ready", parsed.get("answer_ready"))
        ),
        "decision_ready": bool(
            readiness.get("decision_ready", parsed.get("decision_ready"))
        ),
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
        "decision": _compact_mapping(
            decision,
            ("intent", "action_plan", "scenarios", "counter_evidence", "risks", "data_limits"),
            max_len=240,
        ),
        "human_answer": _extract_human_answer_text(
            parsed=parsed,
            analysis=analysis,
            result_data=result_data,
        ),
        "missing": _compact_list(
            limitations.get("missing", parsed.get("missing")),
            max_items=12,
            max_len=120,
        ),
        "warnings": _compact_list(
            limitations.get("warnings", parsed.get("warnings")),
            max_items=8,
            max_len=180,
        ),
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
                canonical_evidence.get("source_refs")
                if isinstance(canonical_evidence.get("source_refs"), list)
                else parsed.get("source_refs")
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
        if not parsed or not _is_supported_omi_contract(parsed):
            continue

        continuation = (
            parsed.get("continuation")
            if isinstance(parsed.get("continuation"), dict)
            else {}
        )
        resolution = continuation.get("resolution") or parsed.get("resolution")
        if isinstance(resolution, dict):
            return resolution

    return None


def format_omi_response_for_llm(text: str) -> str:
    parsed = parse_omi_response_text(text)
    if not parsed or not _is_supported_omi_contract(parsed):
        return str(text or "").strip()
    if parsed.get("contract_version") in {
        OMI_ASK_CONTRACT_VERSION,
        OMI_PREVIOUS_CONTRACT_VERSION,
    }:
        return (
            "OMI canonical decision envelope:\n"
            + json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        )

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
