"""SYNTHETIC disposable owners; never construct production controllers/config."""
from types import SimpleNamespace
from unittest.mock import Mock


def core_today():
    return {"contract": "kuro.core.today.v1", "complete": False, "generatedAt": "2026-10-10T00:00:00Z",
        "asOf": "2026-10-10T00:00:00Z", "localDate": "2026-10-10", "timezone": "Asia/Taipei",
        "limitations": ["source_stale"], "sections": [], "counts": {"total": 3, "normal": 1},
        "items": [{"workId": name, "title": "SYNTHETIC " + name, "source": source, "level": level,
            "reasonCodes": ["synthetic_reason"], "evidenceRef": "synthetic-evidence", "stale": True, "partial": True}
            for name, source, level in [("first-normal", "calendar", "normal"), ("second-watch", "study", "watch"), ("third-urgent", "mail", "urgent")]],
        "sourceStates": [{"integrationId": "study", "availability": "partial", "freshness": "stale", "connection": "offline", "observedAt": None, "validUntil": None, "limitationCount": 1}]}


def controller_fixture():
    c = Mock()
    c.character_records = {"char-key": SimpleNamespace(conf_uid="actor", conf_name="SYNTHETIC actor")}
    c.project_records = {"project-key": SimpleNamespace(project_id="project", display_name="SYNTHETIC project")}
    c.selected_character_key, c.selected_project_key = "char-key", "project-key"
    c.llm_model, c.thinking_power = "synthetic-model", "normal"
    c.cfg = SimpleNamespace(openai_models=["synthetic-model"])
    c.selected_character.return_value = c.character_records["char-key"]
    c.expression_options.return_value = (("neutral", "Neutral"),)
    c.read_today.return_value = core_today()
    c.read_core_status.return_value = {"ok": True, "contract": "kuro.core.api.v1", "capabilities": {
        "schedule": {"contract": "kuro.core.schedule.v1", "today": "2026-10-10", "timezone": "Asia/Taipei", "materialization": "incomplete"}}}
    c.read_schedule_view.return_value = {"ok": True, "items": [], "coverage": "incomplete", "limitations": ["materialization_pending"]}
    c.read_schedule_notifications.return_value = {"ok": True, "items": [], "preferences": {}}
    c.prepare_schedule.side_effect = lambda item: {"ok": True, "item": item}
    c.mutate_schedule.return_value = {"ok": True, "id": "synthetic", "revision": 2}
    c.read_tool_policy_summary.return_value = {"default_mode": "blocked", "tools": [], "confirmation_available": False}
    c.read_memory_records.return_value = (SimpleNamespace(entry_id="m1", content="SYNTHETIC memory", memory_type="fact",
        status="pending_confirmation", enabled=False, scope_level="character", source="synthetic", updated_at="", content_digest="digest1"),)
    c.add_memory.return_value = True
    c.set_memory_status.return_value = True
    c.delete_memory.return_value = True
    c.compact_memory.return_value = {"changed": True, "removed_count": 1}
    c.start_profile.return_value = {"ok": True}
    c.run_pet_command.return_value = {"ok": True}
    c.set_pet_toggle.return_value = {"ok": True}
    c.set_expression.return_value = {"ok": True}
    c.read_runtime_status.return_value = SimpleNamespace(pet_shell=False, capture_available=False,
        mic_enabled=False, mic_paused=False, camera_enabled=False, screen_enabled=False, pet_game_mode=False,
        force_ignore_mouse=False, current_outfit_id="normal", current_expression_id="neutral", current_expression_label="Neutral")
    c.presentation_state.return_value = None
    c.read_companion_diagnostics.return_value = {"phase": "synthetic"}
    return c


class ChatFixture:
    def __init__(self):
        self.client_uid, self.conf_uid, self.context_id = "client", "actor", "context"
        self.current_history_uid, self.current_history_title = "history", "SYNTHETIC history"
        self.conf_name, self.active_project_id = "SYNTHETIC actor", "project"
        self.effective_model, self.thinking_power = "synthetic-model", "normal"
        self.connected = self.history_ready = True
        self.history_pending = False
        self.history_request_id = ""
        self.calls = []
    def history_identity(self): return self.client_uid, self.conf_uid, self.context_id, self.current_history_uid
    def send_text(self, text, attachments): self.calls.append(("send", text, attachments)); return True
    def send_interrupt(self): self.calls.append(("interrupt",)); return True
    def send_capture(self, capture, attachments): self.calls.append(("capture",)); return True
    def _request(self, op):
        self.calls.append((op,)); self._history_pending = {"request_id": "ws-id"}; self.history_request_id = "ws-id"; self.history_pending = True; return True
    def request_history_list(self): return self._request("list")
    def create_history(self, **kwargs): return self._request("create")
    def select_history(self, uid): return self._request("select")
    def delete_history(self, uid, *, confirmed=False):
        assert confirmed
        return self._request("delete")


class SyntheticConversation:
    """Protocol fixture only: deterministic replies, no LLM or canonical claim."""
    def __init__(self):
        import threading
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.histories = {'h1': [{'role': 'event', 'content': 'SYNTHETIC tool event'}]}
        self.received = []
        self.connections = 0
        self.roles = []
        self.port = None
        self.failure = None
        self.sessions = []

    async def connection(self, ws, path):
        import json
        import uuid
        if path != '/client-ws?client_role=qt-primary':
            await ws.close(code=1008); return
        self.connections += 1
        self.roles.append(path)
        context = 'synthetic-context-' + str(self.connections)
        scope = dict(client_uid='client', conf_uid='actor', context_id=context)
        self.sessions.append((ws, scope))
        history = next(iter(self.histories), '')
        await ws.send(json.dumps(dict(type='set-model-and-conf', **scope, conf_name='SYNTHETIC actor',
            history_protocol='kuro.conversation.history.v1', active_project_id='project',
            effective_model='synthetic-model', thinking_power='normal')))
        async for raw in ws:
            p = json.loads(raw)
            kind = p.get('type')
            self.received.append({'type': kind, 'request_id': p.get('request_id'), 'context_id': p.get('context_id')})
            if any(p.get(k) != v for k, v in scope.items()): continue
            identity = dict(scope, request_id=p.get('request_id'))
            if kind == 'fetch-history-list':
                result = dict(type='history-list', current_history_uid=history, histories=[
                    {'uid': key, 'title': 'SYNTHETIC ' + key, 'preview': 'disposable fixture'} for key in self.histories])
            elif kind == 'fetch-and-set-history' and p.get('history_uid') in self.histories:
                history = p['history_uid']
                result = dict(type='history-data', history_uid=history, title='SYNTHETIC '+history, timeline=self.histories[history])
            elif kind == 'create-new-history':
                history = 'h-' + uuid.uuid4().hex[:8]; self.histories[history] = []
                result = dict(type='new-history-created', history_uid=history)
            elif kind == 'delete-history':
                target = p.get('history_uid'); existed = target in self.histories
                self.histories.pop(target, None)
                if history == target: history = ''
                result = dict(type='history-deleted', history_uid=target, success=existed)
            elif kind == 'text-input' and p.get('history_uid') == history and history:
                # Deliberate transport-disconnect case, typed only in this fixture.
                if p.get('text') == 'SYNTHETIC DISCONNECT':
                    await ws.close(code=1012); return
                conversation_scope = dict(scope, history_uid=history)
                for event in [dict(type='control', text='conversation-chain-start'),
                        dict(type='full-text', text='SYNTHETIC reply'),
                        dict(type='tool_call_status', tool_id='fixture-tool', tool_name='SYNTHETIC tool', status='completed'),
                        dict(type='control', text='conversation-chain-end')]:
                    await ws.send(json.dumps(dict(event, conversation_scope=conversation_scope)))
                self.histories[history].extend([{'role':'human','content':'SYNTHETIC input'}, {'role':'assistant','content':'SYNTHETIC reply'}])
                await ws.send(json.dumps(dict(type='full-text', text='STALE MUST NOT RENDER', conversation_scope=dict(conversation_scope, history_uid='old'))))
                continue
            elif kind == 'interrupt-signal':
                await ws.send(json.dumps(dict(type='control', text='interrupt', conversation_scope=dict(scope, history_uid=history))))
                continue
            elif kind in {'mic-audio-data', 'mic-audio-end'}:
                continue  # Synthetic capture sink; no voice/provider work.
            else:
                result = dict(type='history-error', error='history_not_found_for_profile')
            await ws.send(json.dumps(dict(result, **identity)))

    def start(self):
        import asyncio
        import threading
        async def serve_loop():
            self.loop = asyncio.get_running_loop()
            from websockets.legacy.server import serve
            async with serve(self.connection, '127.0.0.1', 0, max_size=12*1024*1024) as server:
                self.port = server.sockets[0].getsockname()[1]; self.ready.set()
                while not self.stop.is_set(): await asyncio.sleep(.05)
        def run():
            try: asyncio.run(serve_loop())
            except Exception as exc: self.failure = str(exc); self.ready.set()
        self.thread = threading.Thread(target=run, daemon=True); self.thread.start()
        if not self.ready.wait(5) or self.failure: raise RuntimeError(self.failure or 'Fixture WS timeout')

    def rotate_context(self):
        """Synthetic server-side profile adoption on the same single WS."""
        import asyncio
        import json
        import uuid
        async def rotate():
            for ws, scope in self.sessions:
                if ws.closed: continue
                scope['context_id'] = 'synthetic-profile-' + uuid.uuid4().hex
                await ws.send(json.dumps(dict(type='set-model-and-conf', **scope,
                    conf_name='SYNTHETIC actor', history_protocol='kuro.conversation.history.v1',
                    active_project_id='project', effective_model='synthetic-model', thinking_power='normal')))
        asyncio.run_coroutine_threadsafe(rotate(), self.loop).result(timeout=3)

    def close(self):
        self.stop.set(); self.thread.join(6)
        if self.thread.is_alive(): raise RuntimeError('Fixture WS shutdown timeout')

