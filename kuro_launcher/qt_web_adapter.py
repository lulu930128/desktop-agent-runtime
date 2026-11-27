"""Explicit projection onto existing Qt owners; no second client, DB or notifier.

The caller supplies worker execution + GUI delivery. Tests supply disposable owners.
This module deliberately has no launcher/config initialization side effects.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import json
from threading import Event
from .qt_web_protocol import Rejected, error, attachments


def today_projection(raw):
    if (raw.get("contract") != "kuro.core.today.v1" or type(raw.get("complete")) is not bool
            or not all(isinstance(raw.get(k), list) for k in ("items", "sections", "sourceStates", "limitations"))):
        raise Rejected("today_contract_invalid")
    items = []
    for row in raw["items"]:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("workId", "title", "source", "level")):
            raise Rejected("today_item_invalid")
        # Order, severity and membership are supplied by Core; no scoring/filtering.
        items.append({**copy.deepcopy(row), "id": row["workId"], "refId": row["workId"],
            "text": row["title"], "date": row.get("dueAt"),
            "meta": " · ".join(str(v) for v in row.get("reasonCodes", [])),
            "evidence": json.dumps({k: row[k] for k in ("evidenceRef", "summary", "stale", "partial", "reasonCodes", "actionKind") if k in row}, ensure_ascii=False)})
    sources = []
    for row in raw["sourceStates"]:
        if not isinstance(row, dict) or not isinstance(row.get("integrationId"), str):
            raise Rejected("today_source_invalid")
        # The text includes all axes; no connected=>current inference.
        sources.append({"id": row["integrationId"], "label": row["integrationId"],
            "status": row.get("freshness"), "updatedAt": row.get("observedAt"),
            "message": json.dumps(row, ensure_ascii=False), "canonical": copy.deepcopy(row)})
    return {"ok": True, "canonical": copy.deepcopy(raw), "updatedAt": raw.get("generatedAt"),
        "snapshot": {"date": raw.get("localDate"), "updatedAt": raw.get("generatedAt"),
            "sourceStatus": sources, "sections": [],
            "today": {"items": items, "counts": copy.deepcopy(raw.get("counts", {})),
                      "updatedAt": raw.get("generatedAt")}}}


class QtOwnerAdapter:
    def __init__(self, controller, chat, run_worker, *, window_action, event=lambda *_: None,
                 request_status=None, request_data=None, profile_action=None, archive_picker=None):
        self.controller, self.chat, self.run_worker = controller, chat, run_worker
        self.window_action, self.event = window_action, event
        self.request_status, self.profile_action = request_status, profile_action
        self.archive_picker = archive_picker
        self.request_data = request_data
        self.closed = False
        self.revision = 0
        self.scope = tuple(chat.history_identity())
        self.scope_cancelled = Event()
        self.transport_scope_cancelled = None
        self.state = "offline"
        self.history_rows = []
        self.histories = []
        self.memory_snapshot = None
        self.history_wait = None
        self.profile_wait = None
        self.latest_user = ""
        self.latest_assistant = ""
        self.timeline = []
        self.speech_status = ""
        self.speech_missing = {}
        self.capture_identity = None
        self.runtime_snapshot = None

    def identity(self):
        snapshot = getattr(self.chat, "history_scope_snapshot", None)
        if callable(snapshot):
            current, self.transport_scope_cancelled = snapshot()
        else:
            current = tuple(self.chat.history_identity())
        if current != self.scope:
            self.scope_cancelled.set()
            self.scope_cancelled = Event()
            self.scope = current
            self.revision += 1
            self.memory_snapshot = None
            self.history_rows = []
            self.histories = []
            self.latest_user = self.latest_assistant = ""
            self.timeline = []
            self.speech_status = ""
            self.speech_missing = {}
            self.runtime_snapshot = None
        client, actor, context, history = current
        return {"client": client, "actor": actor, "context": context, "history": history, "revision": self.revision}

    def chat_state(self):
        identity = self.identity()
        return {"ok": True, "aiState": self.state, "wsConnected": self.chat.connected,
            "confUid": self.chat.conf_uid, "confName": self.chat.conf_name,
            "currentHistoryUid": self.chat.current_history_uid,
            "currentHistoryTitle": self.chat.current_history_title,
            "latestUserText": self.latest_user, "latestAssistantText": self.latest_assistant,
            "timeline": copy.deepcopy(self.timeline), "identity": identity,
            "speechStatus": self.speech_status, "speechMissing": self.speech_missing,
            "historyReady": self.chat.history_ready}

    def _history_result(self):
        identity = self.identity()
        return {"ok": True, "confUid": self.chat.conf_uid, "historyUid": self.chat.current_history_uid,
            "current_history_uid": self.chat.current_history_uid, "selected_history_uid": self.chat.current_history_uid,
            "title": self.chat.current_history_title, "messages": copy.deepcopy(self.history_rows),
            "histories": copy.deepcopy(self.histories), "identity": identity}

    def _require_chat(self, *, idle=False):
        if not self.chat.history_ready: raise Rejected("conversation_not_ready")
        if self.chat.history_pending or self.history_wait or self.profile_wait: raise Rejected("conversation_busy")
        if idle and self.state not in {"idle", "interrupted", "offline"}: raise Rejected("turn_busy")

    def prepare(self, method, p):
        if method in {"getMemories", "memoryAction"} and (self.chat.connected is not True or self.chat.history_ready is not True):
            self.memory_snapshot = None
            raise Rejected("memory_actor_not_ready")
        if method in {"sendText", "getHistories", "createHistory", "selectHistory", "deleteHistory", "applyProfile"}:
            self._require_chat(idle=True)
        if method == "sendText":
            status = self.runtime_snapshot or {}
            p["_capture_images"] = bool(status.get("cameraEnabled") or status.get("screenEnabled"))
        if method == "memoryAction":
            if not self.memory_snapshot or self.memory_snapshot["identity"] != self.identity():
                raise Rejected("read_memory_before_confirming")
            p["expected_conf_uid"] = self.identity()["actor"]
            if self.memory_snapshot.get("formation"):
                p["expected_project_id"] = self.memory_snapshot["formation"]["project_id"]
                if p["expected_project_id"] != self.chat.active_project_id:
                    raise Rejected("memory_project_changed")
            if p["action"] in {"reprocess","backup","restore"}:
                p["expected_project_id"] = self.memory_snapshot["formation"]["project_id"]
                if p["action"] == "reprocess":
                    p["history_uid"] = self.identity()["history"]
                    if not p["history_uid"]:
                        raise Rejected("history_required")
                else:
                    selection = self.archive_picker(p["action"]) if self.archive_picker else None
                    if not selection:
                        raise Rejected("cancelled")
                    p.update(selection)
            if p["action"] == "formation":
                if not self.memory_snapshot.get("formation"):
                    raise Rejected("formation_owner_unavailable")
                p["expected_policy_digest"] = self.memory_snapshot["formation"]["digest"]
                p["expected_project_id"] = self.memory_snapshot["formation"]["project_id"]
            if p["action"] == "compact":
                p["digests"] = {r["id"]: r["content_digest"] for r in self.memory_snapshot["memories"]}
            elif p["action"]=="review":
                rows = {r["id"]:r for r in self.memory_snapshot["memories"]}
                p["review_content"] = []
                for item in p["payload"]["entries"]:
                    row = rows.get(item["entry_id"])
                    if not row or row["status"]!="pending_confirmation" or row["content_digest"]!=item["content_digest"]:
                        raise Rejected("memory_stale_digest")
                    p["review_content"].append(row["content"])
            elif p["action"] in {"status", "delete","revise","source"}:
                row = next((r for r in self.memory_snapshot["memories"] if r["id"] == p["payload"]["entry_id"]), None)
                if not row or not row["content_digest"]: raise Rejected("memory_digest_required")
                if p["payload"].get("content_digest", row["content_digest"]) != row["content_digest"]: raise Rejected("memory_stale_digest")
                p["payload"]["content_digest"] = row["content_digest"]
                p["review_content"] = row["content"]
        if method == "applyProfile":
            c = self.controller
            characters = [key for key, row in c.character_records.items() if row.conf_uid == p["character_id"]]
            projects = [key for key, row in c.project_records.items() if row.project_id == p["project_id"]]
            if len(characters) != 1 or len(projects) != 1:
                raise Rejected("profile_not_registered")
            p["_character_key"], p["_project_key"] = characters[0], projects[0]
            if p["model"] not in c.cfg.openai_models or p["thinking_power"] not in {"fast", "normal", "deep"}:
                raise Rejected("profile_option_unsupported")
        if method == "control":
            action = p["action"]
            allowed = {"interrupt", "set-outfit", "set-expression", "set-force-ignore-mouse", "set-game-mode",
                "toggle-camera", "toggle-screen", "mic-start", "mic-submit", "mic-pause", "mic-resume", "mic-cancel",
                "reset-pet-position", "move-next-display", "retry-pet-model"}
            if action not in allowed: raise Rejected("control_unsupported_no_permission_escalation")
            body = p["payload"]
            if action in {"toggle-camera", "toggle-screen", "set-force-ignore-mouse", "set-game-mode"}:
                if set(body) != {"enabled"}: raise Rejected("enabled_required")
            elif action == "set-outfit":
                if set(body) != {"outfitId"} or body["outfitId"] not in {"normal", "hoodie"}: raise Rejected("outfit_unsupported")
            elif action == "set-expression":
                if set(body) != {"expressionId"} or body["expressionId"] not in dict(self.controller.expression_options()): raise Rejected("expression_unsupported")
            elif body: raise Rejected("unexpected_control_payload")
            if action.startswith("mic-") or action in {"toggle-camera", "toggle-screen", "interrupt"}:
                self._require_chat(idle=action != "interrupt")
            if (action.startswith("mic-") and action != "mic-cancel" or action in {"toggle-camera", "toggle-screen"}) and not (self.runtime_snapshot or {}).get("captureAvailable"):
                raise Rejected("capture_unavailable_read_status_first")
            if action == "mic-submit" and self.capture_identity != self.identity(): raise Rejected("capture_context_changed_cancel_required")
        return p

    def dispatch(self, method, p, done, *, active=None):
        active = active or getattr(done, "active", lambda: True)
        if self.closed or not active(): return
        if method in {"getChatState", "getChatHistory"}:
            done(self.chat_state() if method == "getChatState" else self._history_result())
            return
        if method in {"getWindowState", "startWindowMove", "startWindowResize"}:
            done(self.window_action(method, p))
            return
        if method in {"closeWindow", "minimizeWindow", "toggleMaximizeWindow"}:
            self.window_action(method)
            done({"ok": True})
            return
        if method in {"getHistories", "createHistory", "selectHistory", "deleteHistory"}:
            if method == "getHistories": accepted = self.chat.request_history_list()
            elif method == "createHistory": accepted = self.chat.create_history(force_new=True)
            elif method == "selectHistory": accepted = self.chat.select_history(p["historyUid"])
            else: accepted = self.chat.delete_history(p["historyUid"], confirmed=True)
            if not accepted:
                done(error("history_not_submitted"))
                return
            request_id = self.chat.history_request_id
            if not request_id:
                done(error("history_submission_unknown", unknown=method != "getHistories")); return
            self.history_wait = {"request_id": request_id, "identity": self.identity(), "done": done, "method": method, "active": active}
            return
        if method == "sendText":
            if not self.chat.current_history_uid:
                expected = self.identity()
                def created(result):
                    if self.closed or not active(): return
                    if not result.get("ok"):
                        done(result); return
                    if not self.chat.current_history_uid or any(self.identity()[k] != expected[k] for k in ("actor", "client", "context")):
                        done(error("new_history_context_changed", unknown=True)); return
                    self._submit_text(p, lambda sent: done({**sent, "createdHistory": True}), active)
                self.dispatch("createHistory", {}, created, active=active)
            else: self._submit_text(p, done, active)
            return
        if method == "control" and p["action"] == "interrupt":
            done({"ok": True, "accepted": True} if self.chat.send_interrupt() else error("interrupt_result_unknown", unknown=True))
            return
        expected = self.identity()
        scope_cancelled = self.scope_cancelled
        transport_cancelled = self.transport_scope_cancelled
        context = {"identity": copy.deepcopy(expected), "chat": self.chat_state(),
            "effective": {"actor": self.chat.conf_uid, "project": self.chat.active_project_id,
                "model": self.chat.effective_model, "thinking_power": self.chat.thinking_power}}
        def work():
            if self.closed or not active(): return error("request_expired")
            if scope_cancelled.is_set() or transport_cancelled is not None and transport_cancelled.is_set():
                return error("context_changed_before_operation")
            try:
                return self._owned_call(method, p, context)
            except Rejected as exc:
                return error(str(exc))
            except Exception:
                # No exception text / private payload / paths pass into HTML.
                return error("owner_failed_or_offline", unknown=method in {"applyProfile", "memoryAction", "control", "updateAssistantSettings", "updateChatSpeechSettings"} or method == "schedule" and p["action"] in {"mutate", "notification-action"})
        def complete(result):
            if self.closed or not active(): return
            if expected != self.identity() and method != "applyProfile":
                done(error("context_changed_during_operation", unknown=method in {"memoryAction", "control", "updateAssistantSettings", "updateChatSpeechSettings"} or method == "schedule" and p["action"] in {"mutate", "notification-action"}))
                return
            if method == "applyProfile" and result.get("ok"):
                c = self.controller
                target = (p["character_id"], p["project_id"], p["model"], p["thinking_power"])
                self.profile_wait = {"target": target, "context": expected["context"], "done": done, "active": active}
                self._reconcile_profile()
                return
            if method == "getMemories":
                self.memory_snapshot = copy.deepcopy(result) if result.get("ok") is True else None
            if method == "getState":
                self.runtime_snapshot = copy.deepcopy(result) if result.get("ok") is True else None
            if method == "memoryAction" and p["action"]!="source": self.memory_snapshot = None
            if method == "control" and result.get("ok"):
                if p["action"] == "mic-start": self.capture_identity = expected
                if p["action"] in {"mic-cancel", "mic-submit"}: self.capture_identity = None
                if p["action"] == "mic-submit":
                    media = result.get("result", {})
                    if not isinstance(media, dict) or media.get("ok") is not True or not media.get("capture"):
                        done(error("capture_missing")); return
                    try: images = self._capture_images(media.get("images", []))
                    except (Rejected, ValueError, TypeError): done(error("capture_images_invalid")); return
                    if not self.chat.send_capture(media["capture"], images):
                        done(error("capture_send_unknown", unknown=True)); return
                    result = {"ok": True, "accepted": True, "completed": False}
            done(result)
        if method == "getState" and self.request_status is not None:
            self.request_status(lambda result: complete(self._state_result(result, context)))
        elif method == "getData" and self.request_data is not None:
            self.request_data(complete)
        elif method == "applyProfile" and self.profile_action is not None:
            self.profile_action(lambda: work(), complete)
        else:
            self.run_worker(work, complete)

    def read_status(self):
        c = self.controller
        # Missing Live2D assets/diagnostics must never suppress the independent
        # runtime status which owns Chat auto-connect.
        result = {"ok": True, "status": c.read_runtime_status()}
        for name, read in (("presentation", c.presentation_state), ("diagnostics", c.read_companion_diagnostics)):
            try: result[name] = read()
            except Exception:
                result[name] = {"ok": False, "state": "unavailable", "error": name + "_unavailable"}
        return result

    def _state_result(self, raw, context):
        if raw.get("ok") is not True: return raw
        status = raw["status"]
        result = copy.deepcopy(context["chat"])
        # The original renderer consumes the lifecycle contract (including
        # voice), not the independent Live2D presentation descriptor.
        launcher = raw["diagnostics"] if raw["diagnostics"].get("ok") is not False else None
        result.update({"capabilities": {"launcher": launcher,
            "pet": {"state": "ready" if status.pet_shell else "unavailable"}},
            "diagnostics": raw["diagnostics"], "presentation": raw["presentation"],
            "captureAvailable": status.capture_available})
        for source, destination in (("mic_enabled", "micEnabled"), ("mic_paused", "micPaused"),
                ("camera_enabled", "cameraEnabled"), ("screen_enabled", "screenEnabled"),
                ("pet_game_mode", "petGameMode"), ("force_ignore_mouse", "forceIgnoreMouse"),
                ("current_outfit_id", "currentOutfitId"), ("current_expression_id", "currentExpressionId"),
                ("current_expression_label", "currentExpressionLabel")):
            result[destination] = getattr(status, source)
        return result

    def _owned_call(self, method, p, context):
        c = self.controller
        if method == "getData": return today_projection(c.read_today())
        if method in {"refreshMail", "getMailMessage"}: return error("mail_canonical_contract_unavailable")
        if method == "getAssistantSettings": return {"ok": True, **c.read_assistant_settings()}
        if method == "getChatSpeechSettings": return {"ok": True, **c.read_chat_speech_settings()}
        if method == "updateChatSpeechSettings":
            return {"ok": True, **c.update_chat_speech_settings(p["settings"], p["expectedRevision"])}
        if method == "updateAssistantSettings":
            return {"ok": True, **c.update_assistant_settings(p["settings"], p["expectedRevision"])}
        if method == "getTools":
            return {"ok": True, **c.read_tool_policy_summary(context["identity"].get("client")),
                    "events": context["chat"].get("timeline", [])}
        if method == "updateToolPolicy": return {"ok": True, **c.update_tool_policy(p, context["identity"].get("client"))}
        if method == "getProfile":
            return {"ok": True, "characters": [{"id": row.conf_uid, "name": row.conf_name} for row in c.character_records.values()],
                "projects": [{"id": row.project_id, "name": row.display_name} for row in c.project_records.values()],
                "models": list(c.cfg.openai_models), "thinking_options": ["fast", "normal", "deep"],
                "outfits": [{"id": "normal", "name": "Normal"}, {"id": "hoodie", "name": "Hoodie"}],
                "expressions": [{"id": key, "name": label} for key, label in c.expression_options()],
                "selected": {"character_id": c.character_records[c.selected_character_key].conf_uid, "project_id": c.project_records[c.selected_project_key].project_id,
                    "model": c.llm_model, "thinking_power": c.thinking_power},
                "effective": context["effective"]}
        if method == "applyProfile":
            lock = getattr(getattr(c, "lifecycle", None), "lock", None)
            if lock is not None and not lock.acquire(blocking=False): return error("lifecycle_busy")
            try:
                c.set_selected_character(p["_character_key"])
                c.set_selected_project(p["_project_key"])
                c.set_llm_model(p["model"])
                c.set_thinking_power(p["thinking_power"])
                result = c.start_profile()
            finally:
                if lock is not None: lock.release()
            if not isinstance(result, dict) or result.get("ok") is not True or result.get("pending"):
                return error("profile_effect_unknown", unknown=True)
            return {"ok": True}  # Completion is held until effective WS identity agrees.
        if method == "getMemories":
            character = c.selected_character()
            if not character or not context["identity"]["actor"] or character.conf_uid != context["identity"]["actor"]:
                return error("memory_actor_not_ready")
            project = context["effective"]["project"]
            scoped = {"project_id":project} if hasattr(c,"_memory_project") else {}
            rows = c.read_memory_records(strict=True,**scoped)
            formation = c.memory_formation(character.conf_uid,context["effective"]["project"]) if hasattr(c,"memory_formation") else None
            return {"ok": True, "character_id": character.conf_uid, "character_name": character.conf_name,
                "formation": formation if isinstance(formation,dict) else None,
                "processing": c.memory_processing_status(character.conf_uid, project) if hasattr(c,"memory_processing_status") else None,
                "identity": context["identity"], "memories": [{"id": r.entry_id, "content": r.content,
                    "memory_type": r.memory_type, "status": r.status, "enabled": r.enabled,
                    "scope": r.scope_level, "source": r.source, "updated_at": r.updated_at,
                    "content_digest": r.content_digest, "origin_history":getattr(r,"source_history_uid",""),
                    "origin_actor":getattr(r,"source_character_id",""), "revision":getattr(r,"revision",1), "valid_to":getattr(r,"valid_to","")} for r in rows]}
        if method == "memoryAction":
            body, action = p["payload"], p["action"]
            kwargs = {"expected_conf_uid": p["expected_conf_uid"]}
            if "expected_project_id" in p and p["expected_project_id"] != context["effective"]["project"]:
                raise Rejected("memory_project_changed")
            if action in {"status","delete","compact"} and hasattr(c,"_memory_project"):
                kwargs["project_id"] = context["effective"]["project"]
            if action == "add": changed = c.add_memory(body["content"], **kwargs)
            elif action=="source":
                return c.read_memory_source(p["expected_conf_uid"],context["effective"]["project"],body)
            elif action in {"review","revise"}:
                return c.review_memories(action,body,p["expected_conf_uid"],context["effective"]["project"])
            elif action in {"reprocess","backup","restore"}:
                return {"ok": True, "maintenance": c.maintain_memories(action,p)}
            elif action == "formation":
                changed = c.configure_memory_formation(p["expected_conf_uid"],p["expected_project_id"],body,p["expected_policy_digest"])
            elif action == "compact": return {"ok": True, **c.compact_memory(expected_digests=p["digests"], **kwargs)}
            elif action == "status": changed = c.set_memory_status(body["entry_id"], body["status"], expected_digest=body["content_digest"], **kwargs)
            else: changed = c.delete_memory(body["entry_id"], expected_digest=body["content_digest"], **kwargs)
            return {"ok": True, "changed": changed}
        if method == "getState":
            return self._state_result(self.read_status(), context)
        if method == "schedule":
            action, body = p["action"], p["payload"]
            if action == "notification-action":
                command = {k:v for k,v in body.items() if k not in {"expectedRevision", "idempotencyKey"}}
                return {"ok": True, **c.schedule_notification_command({"command": {**command, "confirmed": True},
                    "expectedRevision": body["expectedRevision"], "idempotencyKey": body["idempotencyKey"]})}
            if action == "status":
                raw = c.read_core_status()
                schedule = raw.get("capabilities", {}).get("schedule", {})
                if raw.get("contract") != "kuro.core.api.v1" or schedule.get("contract") != "kuro.core.schedule.v1": raise Rejected("schedule_contract_invalid")
                return {"ok": True, **schedule}
            calls = {"view": lambda: c.read_schedule_view(**body), "item": lambda: c.read_schedule_item(body["id"]),
                     "prepare": lambda: c.prepare_schedule(body["item"]), "notifications": c.read_schedule_notifications,
                     "mutate": lambda: c.mutate_schedule({**body, "confirmed": True})}
            if action not in calls: raise Rejected("schedule_action_denied")
            result = calls[action]()
            if not isinstance(result, dict): raise Rejected("schedule_result_invalid")
            return {"ok": True, **result}
        if method == "control":
            action, body = p["action"], p["payload"]
            if action == "set-expression": return c.set_expression(body["expressionId"])
            if action == "set-outfit":
                result = c.run_pet_command("set-outfit", {"outfitId": body["outfitId"], "parameterId": "Param10", "value": 1 if body["outfitId"] == "hoodie" else 0})
                if result.get("ok") is True: c.set_outfit(body["outfitId"])
                return result
            if action in {"toggle-camera", "toggle-screen", "set-force-ignore-mouse", "set-game-mode"}:
                return c.set_pet_toggle(action, body["enabled"])
            commands = {"mic-start": "mic-start", "mic-submit": "mic-submit", "mic-pause": "mic-pause", "mic-resume": "mic-resume", "mic-cancel": "mic-cancel",
                "reset-pet-position": "reset-pet-position", "move-next-display": "move-next-display", "retry-pet-model": "reload-frontend"}
            return c.run_pet_command(commands[action])
        raise Rejected("unmapped_method")

    def _submit_text(self, payload, done, active):
        if self.closed or not active(): return
        if payload.get("_capture_images"):
            expected = self.identity()
            scope_cancelled = self.scope_cancelled
            transport_cancelled = self.transport_scope_cancelled
            def capture():
                if self.closed or not active(): return error("request_expired")
                if scope_cancelled.is_set() or transport_cancelled is not None and transport_cancelled.is_set():
                    return error("context_changed_before_operation")
                try: return self.controller.run_pet_command("capture-input")
                except Exception: return error("capture_unavailable")
            def captured(result):
                if self.closed or not active(): return
                if expected != self.identity(): done(error("capture_context_changed")); return
                media = result.get("result", {})
                if result.get("ok") is not True or not isinstance(media, dict) or media.get("ok") is not True:
                    done(error("capture_unavailable")); return
                try:
                    images = self._capture_images(media.get("images", []))
                    combined = payload["attachments"] + images
                    # User attachments + both capture sources share one total bound.
                    attachments([{k:v for k,v in row.items() if k != "source"} for row in combined])
                except (Rejected, ValueError, TypeError): done(error("capture_images_invalid")); return
                self._submit_text({**payload, "_capture_images": False, "attachments": combined}, done, active)
            self.run_worker(capture, captured)
            return
        if not self.chat.send_text(payload["text"], payload["attachments"]):
            done(error("send_result_unknown", unknown=True))
        else:
            self.latest_user = payload["text"]
            done({"ok": True, "accepted": True, "completed": False})
            self.event("onChatState", self.chat_state())

    @staticmethod
    def _capture_images(images):
        if not isinstance(images, list) or len(images) > 2: raise Rejected("capture_images_limit")
        result = []
        for row in images:
            if not isinstance(row, dict) or row.get("source") not in {"camera", "screen"}: raise Rejected("capture_source")
            data, mime = row.get("data"), row.get("mime_type")
            if not isinstance(data, str) or len(data) > 6 * 1024 * 1024 or mime not in {"image/png", "image/jpeg", "image/webp"}: raise Rejected("capture_mime")
            raw = base64.b64decode(data.split(",", 1)[-1], validate=True)
            item = {"kind": "image", "name": row["source"], "size": len(raw), "mime_type": mime, "data": data}
            attachments([item]); result.append({**item, "source": row["source"]})
        return result

    def _reconcile_profile(self):
        wait = self.profile_wait
        if wait and not wait["active"]():
            self.profile_wait = None
            return
        actual = (self.chat.conf_uid, self.chat.active_project_id, self.chat.effective_model, self.chat.thinking_power)
        if (wait and self.chat.connected and self.chat.history_ready
                and actual == wait["target"] and self.chat.context_id != wait["context"]):
            self.profile_wait = None
            wait["done"]({"ok": True, "effective": True})

    def receive(self, payload):
        """Only connect to QtRuntimeChatClient.message_received (already fenced)."""
        if self.closed: return
        self.identity()
        kind = payload.get("type")
        if kind == "set-model-and-conf": self._reconcile_profile()
        if kind in {"history-list", "history-data", "new-history-created", "history-deleted", "history-error"}:
            wait = self.history_wait
            if not wait or payload.get("request_id") != wait["request_id"]: return
            if not wait["active"]():
                self.history_wait = None
                return
            if any(payload.get(key) != wait["identity"][target] for key, target in (("client_uid", "client"), ("conf_uid", "actor"), ("context_id", "context"))): return
            self.history_wait = None
            if kind == "history-list":
                self.histories = copy.deepcopy(payload.get("histories", []))
                # The original renderer expects list + selected transcript in one result.
                # Fetch only the already-selected history via the existing fenced owner.
                if self.chat.current_history_uid and self.chat.select_history(self.chat.current_history_uid):
                    self.history_wait = {"request_id": self.chat.history_request_id, "identity": self.identity(), "done": wait["done"], "method": wait["method"], "active": wait["active"]}
                    return
                if self.chat.current_history_uid:
                    wait["done"](error("selected_history_read_busy")); return
            if kind == "history-data":
                if not isinstance(payload.get("timeline"), list):
                    wait["done"](error("history_timeline_missing")); return
                self.history_rows = copy.deepcopy(payload["timeline"])
            if kind == "history-deleted" and payload.get("success"):
                self.histories = [r for r in self.histories if r.get("uid") != payload.get("history_uid")]
            if kind == "history-error": wait["done"](error("history_owner_rejected"))
            elif kind == "history-deleted" and payload.get("success") is not True: wait["done"](error("history_delete_unknown", unknown=True))
            else: wait["done"](self._history_result())
        if kind in {"tool_call_status", "full-text", "audio", "control", "speech-status"}:
            expected_scope = dict(zip(("client_uid", "conf_uid", "context_id", "history_uid"), self.chat.history_identity()))
            if payload.get("conversation_scope") != expected_scope: return
        if kind == "speech-status":
            self.speech_status = str(payload.get("status", "unavailable"))
            self.speech_missing = {k: v for k in ("missing_segments", "missing_units")
                                   if isinstance((v := payload.get(k)), list) and v}
            request_id = payload.get("speech_request_id")
            if request_id and self.speech_status in {"completed", "partial", "unconfirmed", "failed",
                                                     "timeout", "interrupted", "unavailable", "fallback"}:
                self.controller.log("qt_speech_result " + json.dumps({
                    "request_id": request_id, "history_uid": self.chat.current_history_uid,
                    "status": self.speech_status, "missing": self.speech_missing,
                    "display_sha256": hashlib.sha256(self.latest_assistant.encode("utf-8")).hexdigest(),
                }))
        elif kind == "tool_call_status":
            tool_id = payload.get("tool_id")
            self.timeline = [row for row in self.timeline if row.get("tool_id") != tool_id]
            self.timeline.append({key: payload[key] for key in ("tool_id", "tool_name", "status", "timestamp", "execution_status", "reason_code", "outcome", "call_summary", "content") if key in payload})
            self.timeline = self.timeline[-120:]
        elif kind in {"full-text", "audio"}:
            status_changed = bool(kind == "audio" and payload.get("speech_status"))
            if status_changed:
                self.speech_status = str(payload["speech_status"])
            value = payload.get("text") if kind == "full-text" else (payload.get("display_text") or {}).get("text")
            previous = self.latest_assistant
            if isinstance(value, str) and value and value not in {"Connection established", "Thinking..."}:
                if kind == "full-text":
                    # A full-text snapshot replaces the stream, including its
                    # whitespace. Never append a second copy of that answer.
                    self.latest_assistant = value
                elif payload.get("display_contract") == "kuro.speech-lanes.v1" and payload.get("display_append") is True:
                    # This is the Display transport contract, independent of the
                    # private Speech v2 footer. Ordered deltas may repeat words
                    # or contain only whitespace; neither is a duplicate caption.
                    self.latest_assistant += value
                elif value.startswith(self.latest_assistant): self.latest_assistant = value
                elif value not in self.latest_assistant:
                    gap = " " if self.latest_assistant[-1:].isalnum() and value[:1].isalnum() else ""
                    self.latest_assistant += gap + value
            if self.latest_assistant == previous and not status_changed:
                return  # Empty TTS captions/repeated snapshots are not updates.
        elif kind == "control":
            control = payload.get("text")
            if control == "conversation-chain-start":
                self.speech_status = ""
                self.speech_missing = {}
                self.state = "thinking"; self.latest_assistant = ""; self.timeline = []
            elif control == "conversation-chain-end": self.state = "idle"
            elif control in {"interrupt", "interrupt-signal"}: self.state = "interrupted"
            elif control == "audio-play-start": self.state = "speaking"
        self.event("onChatState", self.chat_state())

    def on_state(self, state, connected):
        # Turn state is accepted only from scoped protocol messages, not an
        # unscoped legacy control signal. Connection loss is transport-owned.
        if self.closed: return
        # A queued 'connecting/offline' can arrive after the client has already
        # connected/reconnected. It cannot cancel a newer request or review.
        if connected != self.chat.connected: return
        if not connected:
            self.state = "offline"
            self.memory_snapshot = self.runtime_snapshot = self.capture_identity = None
            wait, self.history_wait = self.history_wait, None
            if wait:
                wait["done"](error("history_connection_lost", unknown=wait["method"] != "getHistories"))
        self.identity()
        self.event("onChatState", self.chat_state())

    def on_assistant(self, text):
        if self.closed: return
        self.identity()
        self.latest_assistant = str(text)
        self.event("onChatState", self.chat_state())

    def abandon(self, method):
        """Release presentation waits; the broker retains mutation uncertainty."""
        if self.history_wait and (self.history_wait["method"] == method or not self.history_wait["active"]()):
            self.history_wait = None
        if method == "applyProfile": self.profile_wait = None

    def close(self):
        self.closed = True
        self.scope_cancelled.set()
        self.history_wait = self.profile_wait = self.memory_snapshot = None
        self.capture_identity = self.runtime_snapshot = None
