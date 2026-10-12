"""Feature-off Work UI protocol. No Qt, storage, socket or service ownership."""
from __future__ import annotations

import base64
import copy
import json
import re
import time
from dataclasses import dataclass, field
from threading import Event

CONTRACT = "kuro.qt.work.v1"
METHODS = frozenset(("schedule", "getState", "getData", "getChatState", "getChatHistory",
    "getProfile", "applyProfile", "getHistories", "createHistory", "selectHistory",
    "deleteHistory", "getMemories", "memoryAction", "getTools", "sendText",
    "refreshMail", "getMailMessage", "control", "closeWindow", "minimizeWindow",
    "toggleMaximizeWindow"))
IDENTITY_KEYS = {"actor", "history", "context", "client", "revision"}
MAX_BYTES = 12 * 1024 * 1024


class Rejected(ValueError):
    pass


def error(code, *, unknown=False):
    return {"ok": False, "error": code, "unknownResult": unknown, "retry": False}


def object_fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise Rejected("invalid_fields")


def string(value, limit=160, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()) or "\x00" in value:
        raise Rejected("invalid_string")
    return value


def attachments(values):
    if not isinstance(values, list) or len(values) > 6:
        raise Rejected("attachments_limit")
    total = 0
    mime_kinds = {"image/png": "image", "image/jpeg": "image", "image/webp": "image",
                  "text/plain": "text", "application/pdf": "binary", "audio/wav": "audio", "audio/x-wav": "audio"}
    for item in values:
        object_fields(item, {"kind", "name", "size", "mime_type", "data"}, {"kind", "name", "size", "mime_type", "data"})
        string(item["name"], 240)
        mime = item["mime_type"]
        if not isinstance(mime, str) or mime_kinds.get(mime) != item["kind"]:
            raise Rejected("attachment_type_unsupported")
        if type(item["size"]) is not int or not 0 < item["size"] <= 4 * 1024 * 1024:
            raise Rejected("attachment_size")
        data = string(item["data"], 6 * 1024 * 1024)
        prefix = f"data:{mime};base64,"
        if not data.startswith(prefix):
            raise Rejected("attachment_data_url")
        try:
            raw = base64.b64decode(data[len(prefix):], validate=True)
        except ValueError as exc:
            raise Rejected("attachment_encoding") from exc
        if len(raw) != item["size"]:
            raise Rejected("attachment_size_mismatch")
        total += len(raw)
    if total > 8 * 1024 * 1024:
        raise Rejected("attachments_total_limit")


def validate(method, p):
    """Return whether a command changes state (separate from native confirmation)."""
    if method not in METHODS:
        raise Rejected("unsupported_method")
    if method in {"applyProfile"}:
        object_fields(p, {"character_id", "project_id", "model", "thinking_power"},
                      {"character_id", "project_id", "model", "thinking_power"})
        for value in p.values(): string(value, 300)
        return True
    if method == "sendText":
        object_fields(p, {"text", "attachments"}, {"text", "attachments"})
        string(p["text"], 32000, empty=True)
        attachments(p["attachments"])
        if not p["text"].strip() and not p["attachments"]: raise Rejected("empty_message")
        return True
    if method in {"selectHistory", "deleteHistory", "getHistories", "getMailMessage"}:
        keys = {"messageId"} if method == "getMailMessage" else {"historyUid", "historyTitle"}
        object_fields(p, keys)
        for value in p.values(): string(value, 300, empty=method == "getHistories")
        if method in {"selectHistory", "deleteHistory"} and not p.get("historyUid"):
            raise Rejected("history_required")
        return method in {"selectHistory", "deleteHistory"}
    if method == "memoryAction":
        object_fields(p, {"action", "payload"}, {"action", "payload"})
        action, body = p["action"], p["payload"]
        fields = {"add": {"content"}, "status": {"entry_id", "status", "content_digest"},
                  "delete": {"entry_id", "content_digest"}, "compact": set()}
        if not isinstance(action, str) or action not in fields: raise Rejected("memory_action_unsupported")
        object_fields(body, fields[action])
        if action == "add": string(body.get("content"), 260)
        if action in {"status", "delete"}: string(body.get("entry_id"))
        if "content_digest" in body: string(body["content_digest"], 128)
        if action == "status" and body.get("status") not in {"active", "disabled"}: raise Rejected("memory_status")
        return True
    if method == "schedule":
        object_fields(p, {"action", "payload"}, {"action", "payload"})
        action, body = p["action"], p["payload"]
        if action == "materialize": raise Rejected("materialize_owned_by_core_scheduler")
        if action == "notification-action":
            object_fields(body, {"action", "id", "until", "preferences", "confirmed", "expectedRevision", "idempotencyKey"}, {"action", "expectedRevision", "idempotencyKey"})
            if body["action"] not in {"dismiss", "snooze", "preferences"}: raise Rejected("notification_delivery_owned_by_qt")
            fields = {"dismiss": {"action", "id"}, "snooze": {"action", "id", "until"}, "preferences": {"action", "preferences"}}[body["action"]]
            object_fields(body, fields | {"expectedRevision", "idempotencyKey", "confirmed"}, fields | {"expectedRevision", "idempotencyKey"})
            if body["action"] != "preferences": string(body["id"], 100)
            if body["action"] == "snooze": string(body["until"], 80)
            if body["action"] == "preferences":
                object_fields(body["preferences"], {"timezone", "quietEnabled", "quietStart", "quietEnd"}, {"timezone", "quietEnabled", "quietStart", "quietEnd"})
                if type(body["preferences"]["quietEnabled"]) is not bool: raise Rejected("invalid_boolean")
                for key in ("timezone", "quietStart", "quietEnd"): string(body["preferences"][key], 80)
            string(body["expectedRevision"], 64); string(body["idempotencyKey"])
            if not re.fullmatch(r"[a-f0-9]{64}", body["expectedRevision"]): raise Rejected("notification_revision_required")
            body.pop("confirmed", None)
            return True
        fields = {"status": set(), "notifications": set(), "view": {"start", "end", "timezone", "limit", "offset"},
                  "item": {"id"}, "prepare": {"item"}, "mutate": {"action", "idempotencyKey", "id", "expectedRevision", "item", "scope", "occurrenceDate", "confirmed"}}
        if not isinstance(action, str) or action not in fields: raise Rejected("schedule_action_unsupported")
        object_fields(body, fields[action])
        if action == "item": string(body.get("id"))
        if action == "view":
            for key in ("start", "end", "timezone"): string(body.get(key), 80)
            for key, maximum in (("limit", 200), ("offset", 100000)):
                if key in body and (type(body[key]) is not int or not 0 <= body[key] <= maximum): raise Rejected("schedule_bounds")
        if action in {"prepare", "mutate"} and "item" in body:
            if not isinstance(body["item"], dict): raise Rejected("schedule_item")
        if action == "prepare" and set(body) != {"item"}: raise Rejected("schedule_item")
        if action == "mutate":
            string(body.get("idempotencyKey"))
            if body.get("action") not in {"create", "update", "cancel", "complete", "skip", "reopen"}: raise Rejected("schedule_mutation")
            if body["action"] != "create":
                string(body.get("id"))
                if type(body.get("expectedRevision")) is not int or body["expectedRevision"] < 1: raise Rejected("schedule_revision_required")
            # A renderer-supplied confirmed:true is never authority.
            body.pop("confirmed", None)
            return True
        return False
    if method == "control":
        object_fields(p, {"action", "payload"}, {"action", "payload"})
        string(p["action"], 80)
        object_fields(p["payload"], {"enabled", "outfitId", "expressionId"})
        if "enabled" in p["payload"] and type(p["payload"]["enabled"]) is not bool: raise Rejected("invalid_boolean")
        return p["action"] != "interrupt"
    object_fields(p, set())
    return method == "createHistory"


def requires_confirmation(method, payload):
    # Ordinary chat/create/select use the explicit UI action + downstream policy.
    return (method in {"deleteHistory", "memoryAction", "applyProfile"}
            or method == "schedule" and payload.get("action") in {"mutate", "notification-action"}
            or method == "control" and payload.get("action") != "interrupt")


@dataclass
class Pending:
    request: dict
    started: float
    mutation: bool
    timed_out: bool = False
    cancelled: Event = field(default_factory=Event)


class Completion:
    """One dispatch lifetime, also consulted before starting queued owner work."""
    def __init__(self, broker, rid, pending):
        self.broker, self.rid, self.pending = broker, rid, pending

    def active(self):
        return not self.pending.cancelled.is_set()

    def __call__(self, result):
        if self.active(): self.broker.complete(self.rid, result)


class RequestBroker:
    """Called only on the GUI thread. Worker completions must be queued to that thread."""
    def __init__(self, adapter, confirm, emit, *, clock=time.monotonic, timeout=20):
        self.adapter, self.confirm, self.emit = adapter, confirm, emit
        self.clock, self.timeout = clock, timeout
        self.pending = {}
        self.seen = set()
        self.closed = False
        self.mutation_pending = False
        self.uncertain = False

    def response(self, request, result):
        if self.closed: return
        self.emit({"contract": CONTRACT, "id": request.get("id"),
                   "expected": request.get("expected"), "identity": self.adapter.identity(), "result": result})

    def submit(self, raw):
        request = {}
        owns_pending = False
        try:
            if self.closed: raise Rejected("bridge_closed")
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_BYTES: raise Rejected("request_size")
            request = json.loads(raw)
            object_fields(request, {"contract", "id", "expected", "method", "payload"}, {"contract", "id", "expected", "method", "payload"})
            if request["contract"] != CONTRACT: raise Rejected("contract_mismatch")
            rid = string(request["id"], 80)
            if not re.fullmatch(r"[A-Za-z0-9_-]+", rid): raise Rejected("request_id")
            if rid in self.seen:
                # A duplicate must not complete/release an in-flight mutation.
                # Its original correlated response (or timeout) remains authoritative.
                if rid in self.pending: return
                raise Rejected("duplicate_request_no_replay")
            if len(self.seen) >= 10000: raise Rejected("session_request_limit")
            self.seen.add(rid)
            if len(self.pending) >= 12: raise Rejected("busy")
            if request["method"] == "hello":
                object_fields(request["payload"], set())
                self.response(request, {"ok": True, "identity": self.adapter.identity()})
                return
            object_fields(request["expected"], IDENTITY_KEYS, IDENTITY_KEYS)
            for key in ("actor", "client", "context", "history"): string(request["expected"][key], 300, empty=True)
            if type(request["expected"]["revision"]) is not int or request["expected"]["revision"] < 0: raise Rejected("invalid_revision")
            if request["expected"] != self.adapter.identity(): raise Rejected("stale_context")
            mutation = validate(request["method"], request["payload"])
            if mutation and (self.mutation_pending or self.uncertain): raise Rejected("busy_or_unknown_result")
            # Validate owner-specific scopes before displaying any confirmation.
            prepared = self.adapter.prepare(request["method"], copy.deepcopy(request["payload"]))
            self.pending[rid] = Pending(request, float("inf") if requires_confirmation(request["method"], prepared) else self.clock(), mutation)
            owns_pending = True
            if mutation:
                self.mutation_pending = True
            if requires_confirmation(request["method"], prepared):
                accepted = self.confirm(request["method"], copy.deepcopy(prepared))
                # Native modal dialogs run a nested event loop. Quit may have
                # closed this broker while the confirmation was visible.
                if self.closed or rid not in self.pending: return
                if not accepted:
                    self.complete(rid, {"ok": False, "cancelled": True, "error": "cancelled"})
                    return
                if request["expected"] != self.adapter.identity():
                    self.complete(rid, error("confirmation_context_changed"))
                    return
            self.pending[rid].started = self.clock()
            self.adapter.dispatch(request["method"], prepared, Completion(self, rid, self.pending[rid]))
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            code = str(exc) if isinstance(exc, Rejected) else "invalid_request"
            if isinstance(request, dict) and isinstance(request.get("id"), str) and request["id"] in self.pending:
                if owns_pending: self.complete(request["id"], error(code))
            else:
                self.response(request if isinstance(request, dict) else {}, error(code))

    def complete(self, rid, result):
        pending = self.pending.pop(rid, None)
        if pending is None or self.closed: return
        pending.cancelled.set()
        if pending.mutation: self.mutation_pending = False
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            result = error("invalid_owner_result", unknown=pending.mutation)
        try:
            if len(json.dumps(result, allow_nan=False).encode("utf-8")) > MAX_BYTES:
                result = error("owner_result_too_large", unknown=pending.mutation)
        except (TypeError, ValueError):
            result = error("invalid_owner_result", unknown=pending.mutation)
        if result.get("unknownResult") and pending.mutation: self.uncertain = True
        if pending.timed_out: return  # Never overwrite a visible unknown result with late success.
        current = self.adapter.identity()
        created_history = (pending.request["method"] == "sendText" and not pending.request["expected"]["history"]
            and result.get("createdHistory") is True and bool(current["history"])
            and all(pending.request["expected"][k] == current[k] for k in ("actor", "context", "client")))
        initial_history = (pending.request["method"] == "getHistories" and not pending.request["expected"]["history"]
            and result.get("historyUid") == current["history"]
            and all(pending.request["expected"][k] == current[k] for k in ("actor", "context", "client")))
        if (result.get("ok") and pending.request["method"] in {"createHistory", "selectHistory", "deleteHistory"}
                and any(pending.request["expected"][key] != current[key] for key in ("client", "actor", "context"))):
            result = error("stale_history_completion", unknown=pending.mutation)
        elif (result.get("ok") and not created_history and not initial_history and pending.request["expected"] != current
                and pending.request["method"] not in {"createHistory", "selectHistory", "deleteHistory", "applyProfile"}):
            result = error("stale_completion", unknown=pending.mutation)
        if result.get("unknownResult") and pending.mutation: self.uncertain = True
        self.response(pending.request, result)

    def expire(self):
        if self.closed: return
        for pending in list(self.pending.values()):
            limit = 95 if pending.request["method"] == "applyProfile" else self.timeout
            if not pending.timed_out and self.clock() - pending.started >= limit:
                pending.timed_out = True
                pending.cancelled.set()
                if pending.mutation: self.uncertain = True
                abandon = getattr(self.adapter, "abandon", None)
                if callable(abandon): abandon(pending.request["method"])
                self.response(pending.request, error("timeout_result_unknown" if pending.mutation else "read_timeout", unknown=pending.mutation))
                if not pending.mutation: self.pending.pop(pending.request["id"], None)

    def close(self):
        if self.closed: return
        self.closed = True
        for pending in self.pending.values(): pending.cancelled.set()
        self.pending.clear()
        close = getattr(self.adapter, "close", None)
        if callable(close): close()
