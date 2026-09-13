"""Canonical MCP result and bounded consumer views."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any

from .privacy import project, safe_text

MAX_RESULT_BYTES = 8 * 1024 * 1024


@dataclass
class ToolResult:
    execution_id: str = ""
    canonical_tool_id: str = ""
    server_id: str = ""
    wire_name: str = ""
    status: str = "succeeded"
    is_error: bool = False
    protocol_error: str | None = None
    content_items: list[dict[str, Any]] = field(default_factory=list)
    structured_content: dict | None = None
    private_metadata: dict = field(default_factory=dict)
    reason_code: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    result_received: bool = True
    may_have_executed: bool = True
    policy_digest: str = ""
    schema_validation: str = "sdk"

    @property
    def text_blocks(self):
        return [item.get("text", "") for item in self.content_items if item.get("type") == "text"]

    @property
    def resource_links(self):
        return [item for item in self.content_items if item.get("type") == "resource_link"]

    def model_text(self, *, limit=128*1024, secrets=()) -> str:
        blocks = []
        for item in self.content_items:
            if item.get("type") == "text":
                blocks.append(safe_text(item.get("text", ""), secrets=secrets, limit=MAX_RESULT_BYTES))
            elif item.get("type") in {"resource", "resource_link"}:
                view = project(item, secrets=secrets)
                if isinstance(view.get("resource"), dict) and "blob" in view["resource"]:
                    view["resource"]["blob"] = "[binary resource omitted; URI retained]"
                blocks.append(json.dumps(view, ensure_ascii=False))
            else:
                blocks.append(f"[MCP {item.get('type', 'unknown')} content; media not rendered in text mode]")
        if self.structured_content is not None:
            structured = json.dumps(project(self.structured_content, secrets=secrets), ensure_ascii=False)
            if not any(_same_json(block, self.structured_content) for block in self.text_blocks):
                blocks.append(structured)
        if self.status != "succeeded":
            blocks.insert(0, f"Tool execution {self.status}: {self.reason_code or 'tool_error'}.")
        text = safe_text('\n'.join(blocks), secrets=secrets, limit=MAX_RESULT_BYTES)
        if len(text.encode()) > limit:
            # Preserve source-supplied limitations before truncating long prose.
            limits = evidence_limits([self.structured_content, *self.text_blocks], secrets=secrets)
            if limits:
                text = "Source limitations: " + json.dumps(limits, ensure_ascii=False) + "\n" + text
        return safe_text(text, limit=limit, secrets=secrets)

    def status_text(self) -> str:
        return f"Tool execution {self.status}. {self.reason_code}".strip()

    def claude_content(self, *, limit=128*1024, secrets=()) -> list[dict]:
        text = self.model_text(limit=limit, secrets=secrets)
        if "[truncated; evidence incomplete]" in text:
            return [{"type": "text", "text": text}]
        blocks = []
        if self.status != "succeeded":
            blocks.append({"type": "text", "text": self.status_text()})
        for item in project(self.content_items, secrets=secrets):
            if item.get("type") == "image" and item.get("data") and item.get("mimeType") in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": item["mimeType"], "data": item["data"]}})
            else:
                part = ToolResult(content_items=[item]).model_text(limit=limit, secrets=secrets)
                if part:
                    blocks.append({"type": "text", "text": part})
        if self.structured_content is not None and not any(_same_json(block, self.structured_content) for block in self.text_blocks):
            blocks.append({"type": "text", "text": safe_text(json.dumps(project(self.structured_content, secrets=secrets), ensure_ascii=False), limit=limit)})
        return blocks


def normalize_result(response, **identity) -> ToolResult:
    raw = response.model_dump(mode="json", by_alias=True, exclude_none=True)
    size = len(json.dumps(raw, ensure_ascii=False).encode())
    if size > MAX_RESULT_BYTES:
        return ToolResult(**identity, status="failed", is_error=True, reason_code="result_too_large")
    is_error = bool(raw.get("isError", False))
    return ToolResult(**identity, status="failed" if is_error else "succeeded", is_error=is_error,
                      content_items=raw.get("content", []), structured_content=raw.get("structuredContent"),
                      private_metadata=raw.get("_meta", {}), reason_code="tool_error" if is_error else "")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _same_json(text, value):
    try:
        return json.loads(text) == value
    except (ValueError, TypeError):
        return False


def evidence_limits(values, *, secrets=()) -> list:
    """A bounded projection of source fields, without inferring domain truth."""
    found = []
    keys = {"status", "freshness", "data_freshness", "missing", "warnings", "limitations", "provider_failure", "error", "reason_code"}
    def walk(value, depth=0):
        if depth > 12 or len(found) >= 24:
            return
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError, RecursionError):
                return
        if isinstance(value, dict):
            for key, child in value.items():
                if len(found) >= 24:
                    break
                if key in keys:
                    found.append({key: safe_text(json.dumps(project(child, secrets=secrets), ensure_ascii=False), limit=256)})
                else:
                    walk(child, depth+1)
        elif isinstance(value, list):
            for child in value[:128]:
                walk(child, depth+1)
    walk(values)
    return found
