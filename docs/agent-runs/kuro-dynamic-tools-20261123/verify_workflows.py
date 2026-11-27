"""Five isolated MCP workflows. Run with --owners and --projects pointing to installed source owners."""
import argparse
import asyncio
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import uuid
import wave

from inspect_inventory import ROOT, RUNTIME, ToolAdapter, ToolManager, ServerRegistry
from open_llm_vtuber.mcpp.mcp_client import MCPClient
from open_llm_vtuber.mcpp.tool_manager import ToolSelection
from open_llm_vtuber.mcpp.tool_executor import ToolExecutor

STAMP = "2026-01-01T12:00:00Z"
EVENTS = []


@contextlib.contextmanager
def study_hub(project, prefix, data):
    # Owner interpreter and blank DBs. Pass only startup environment needed by Windows.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "SYSTEMDRIVE") if k in os.environ}
    env.update(PYTHONPATH=str(project / "src"), PYTHONDONTWRITEBYTECODE="1")
    env.update({prefix + "_DATA_DIR": str(data), prefix + "_REFERENCE_DIR": str(data / "ref")})
    module = project.name.replace("-", "_")
    command = [str(project / ".venv/Scripts/python.exe"), "-B", "-m", "uvicorn",
               module + ".api:app", "--port", str(port), "--host", "127.0.0.1", "--log-level", "warning"]
    with subprocess.Popen(command, env=env, cwd=data, creationflags=subprocess.CREATE_NO_WINDOW) as process:
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError("Isolated Hub startup failed")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise TimeoutError("Isolated Hub startup")
            yield f"http://127.0.0.1:{port}"
        finally:
            process.terminate()
            process.wait(timeout=10)


@contextlib.contextmanager
def http_fixture(handler):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


class MarketFixture(BaseHTTPRequestHandler):
    fresh = False

    def send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path != "/api/ai/ask":
            return self.send(404, {})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body.get("allow_write") is False and body.get("allow_llm") is False
        if body.get("allow_external_fetch"):
            type(self).fresh = True
        self.send(200, {"contract_version": "omi.decision.v4", "status": "complete",
                        "freshness": "current" if self.fresh else "stale", "source": "isolated_fixture"})

    def do_GET(self):
        self.send(404, {})

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def trainer_fixture(project, data):
    from dataclasses import replace
    sys.path.insert(0, str(project / "src"))
    from jlpt_trainer.settings import load_settings
    from jlpt_trainer.app import TrainerApp, make_handler
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("jlpt_trainer.settings._load_env_file"))
        stack.enter_context(patch.dict(os.environ, {"JLPT_TTS_MODE": "legacy"}))
        paths = {key: data / key for key in ("sets_dir", "audio_dir", "results_dir", "sessions_dir", "tts_runtime_dir")}
        app = TrainerApp(replace(load_settings(), data_dir=data, **paths))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", ""))
            wav.writeframes(bytes(3200))
        # Substitute only the voice backend. Trainer performs WAV creation, validation and scoring.
        stack.enter_context(patch.object(app.tts, "start_profile"))
        stack.enter_context(patch.object(app.listening, "profile_ready", return_value=True))
        stack.enter_context(patch("jlpt_trainer.tts.port_is_open", return_value=True))
        stack.enter_context(patch.object(app.listening.audio_tts, "request_tts", return_value=buf.getvalue()))
        with http_fixture(make_handler(app)) as url:
            yield url


async def workflows(owners, projects, tmp, stack):
    folder = tmp / "workspace"
    folder.mkdir()
    (folder / "note.txt").write_text("original", encoding="utf-8")
    policy = tmp / "write-policy.json"
    policy.write_text(json.dumps({"version": 1, "enabled": True, "rules": [
        {"root": "demo", "path": "**", "operations": ["patch_text_file"], "extensions": [".txt"]}]}))
    def node(component, env):
        return {"command": "node", "args": [str(owners / component / "dist/src/index.js")], "env": env}
    cfg = {"project-workspace": node("project_reading", {"WORKSPACE_MCP_ROOTS": "demo=" + str(folder),
           "WORKSPACE_MCP_DEFAULT_ROOT": "demo", "WORKSPACE_MCP_WRITE_POLICY": str(policy),
           "WORKSPACE_MCP_WRITE_STATE_DIR": str(tmp / "journal")})}
    for prefix, service in (("JSTUDY", "japanese-study"), ("ESTUDY", "english-study")):
        data = tmp / prefix
        data.mkdir()
        url = stack.enter_context(study_hub(projects / (service + "-hub"), prefix, data))
        cfg[service] = node(service.replace("-", "_"), {prefix + "_HUB_BASE_URL": url})
    audio_url = stack.enter_context(trainer_fixture(projects / "jlpt-listening-trainer", tmp / "trainer"))
    cfg["listening-audio"] = node("listening_audio", {"LISTENING_TRAINER_BASE_URL": audio_url})
    market_url = stack.enter_context(http_fixture(MarketFixture))
    cfg["omi-search"] = {"command": str(owners / "OMI_search/.venv/Scripts/python.exe"),
                         "args": ["-B", str(owners / "OMI_search/server.py")],
                         "env": {"PYTHONUTF8": "1", "OMI_SEARCH_API_BASE_URL": market_url}}
    path = tmp / "registry.json"
    path.write_text(json.dumps({"mcp_servers": cfg}))
    registry = ServerRegistry(path)
    adapter = ToolAdapter(registry)
    _, openai, claude = await adapter.get_tools(list(cfg))
    manager = ToolManager(openai, claude, adapter.get_last_formatted_tools_dict())
    manager.bind_discovery(adapter, cfg)
    async with MCPClient(registry) as client:
        executor = ToolExecutor(client, manager)
        selection = ToolSelection(manager, "OpenAI")
        async def execute(name, args):
            call_id = str(uuid.uuid4())
            calls = [{"name": name, "id": call_id, "input": args}]
            updates = [u async for u in executor.execute_tools(calls, "OpenAI", selection)]
            statuses = [u for u in updates if u["type"] == "tool_call_status"]
            terminal = statuses[-1]
            EVENTS.append({k: terminal[k] for k in ("tool_name","status","reason_code","execution_status","outcome","tool_id","call_summary","content") if k in terminal})
            assert terminal["status"] == "completed", (name, terminal)
            return updates[-1]["results"][0]["content"]

        async def call(service, name, **args):
            identity = service + "::" + name
            await execute("kuro_discover", {"load": [identity], "service": service})
            return await execute(manager.tools[identity].api_name, args)

        names = json.loads(await execute("kuro_discover", {}))["matches"]
        assert len(names) > 6
        many = [r["name"] for r in names if r["allowed"]][:9]
        await execute("kuro_discover", {"load": many})
        assert len(selection.descriptors()) == 10
        service = "project-workspace"
        assert "note.txt" in await call(service, "find_files", root="demo", pattern="*.txt")
        read = await call(service, "read_file", root="demo", path="note.txt", includeSha256=True)
        digest = hashlib.sha256(b"original").hexdigest()
        assert digest in read
        await call(service, "patch_text_file", root="demo", path="note.txt", expected_sha256=digest,
                   operation_id=str(uuid.uuid4()), operations=[{"find":"original", "replace":"updated"}])
        assert "updated" in await call(service, "read_file", root="demo", path="note.txt")
        assert (folder / "note.txt").read_bytes() == b"updated"
        session = {"sessionId":"demo-session", "title":"Isolated practice", "practiceType":"grammar",
                   "startedAt":STAMP, "completedAt":STAMP}
        for service, prefix in (("japanese-study","study"), ("english-study","english")):
            await call(service, prefix + "_get_summary")
            question = {"questionKey": "q1", "position": 1}
            if prefix == "study":
                question.update(snapshot={"stem":"fixture"}, response={"answer":{"text":"yes"},
                                "answerResult":"correct","awardedPoints":1,"submittedAt":STAMP})
            else:
                question.update(prompt="fixture", answerResult="correct", submittedAt=STAMP, awardedPoints=1, maxPoints=1)
            submission = {"submissionId":"demo-submission","session":session,"questions":[question]}
            args = submission if prefix == "study" else {"submission":submission}
            preview = await call(service, prefix + "_preview_practice_record", **args)
            if prefix == "english":
                args["expectedFingerprint"] = re.search(r'"fingerprint"\s*:\s*"([a-f0-9]{64})"',preview)[1]
            await call(service, prefix + "_record_practice", **args)
            assert "demo-session" in await call(service, prefix + "_get_practice_session", sessionId="demo-session")
        service = "listening-audio"
        exam = {"schema_version":"2.0","set_id":"fixture-audio","title":"Fixture","scope":"section",
                "source_ref":"test-fixture","question_count":1,"questions":[{"id":"Q1","prompt":"When?",
                "section":1,"answer_type":"text","word_limit":{"max_words":1,"max_numbers":0},
                "expected_answers":[{"type":"text","value":"today"}],"explanation":"Today.",
                "audio_script":[{"seq":1,"speaker":"Guide","voice_slot":"narrator","text":"Today."}]}]}
        await call(service, "listening_create_exam", language="en", set=exam)
        question = {"setId":"fixture-audio","questionId":"Q1"}
        assert "missing" in await call(service, "listening_get_question", **question)
        assert "ready" in await call(service, "listening_prepare_audio", **question)
        wav_files = list((tmp / "trainer").rglob("*.wav"))
        assert len(wav_files) == 1
        with wave.open(str(wav_files[0])) as wav:
            assert wav.getnframes() > 0
        await call(service, "listening_submit_answer", setId="fixture-audio", attemptId="fixture-attempt",
                   submissionId="fixture-answer", answers={"Q1":{"type":"text","value":"today"}}, finalize=True)
        result = await call(service, "listening_get_attempt_result", setId="fixture-audio", attemptId="fixture-attempt")
        assert "completed" in result and "fixture-attempt" in result
        service = "omi-search"
        assert "stale" in await call(service, "omi_read_data_freshness", market="tw")
        await call(service, "omi_ask", question="Refresh isolated market evidence", refresh_if_missing=True)
        assert "current" in await call(service, "omi_read_data_freshness", market="tw")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owners", required=True, type=Path)
    parser.add_argument("--projects", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
        asyncio.run(workflows(args.owners, args.projects, Path(tmp), stack))
    args.receipt.write_text(json.dumps({"surface":"isolated owner workflows","events":EVENTS},
                                       indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
