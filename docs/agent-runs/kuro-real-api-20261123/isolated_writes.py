"""Exercise unmodified MCP owners, real Hub and Trainer HTTP APIs in temporary data stores."""
from live import *
import argparse, contextlib, re, socket, subprocess, tempfile, threading
from http.server import ThreadingHTTPServer
from dataclasses import replace
EVENTS = []
STAMP = "2026-11-23T00:00:00Z"
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



@contextlib.contextmanager
def isolated_trainer(project, data):
    sys.path.insert(0,str(project / "src"))
    from jlpt_trainer.settings import _central_settings
    from jlpt_trainer.app import TrainerApp, make_handler
    settings = _central_settings(project,data)
    assert all(p.resolve().is_relative_to(data.resolve()) for p in (settings.sets_dir, settings.results_dir, settings.audio_dir, settings.sessions_dir))
    with http_fixture(make_handler(TrainerApp(settings))) as url:
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
    audio_url = stack.enter_context(isolated_trainer(projects / "jlpt-listening-trainer", tmp / "trainer"))
    cfg["listening-audio"] = node("listening_audio", {"LISTENING_TRAINER_BASE_URL": audio_url})
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
        await call(service, "listening_submit_answer", setId="fixture-audio", attemptId="fixture-attempt",
                   submissionId="fixture-answer", answers={"Q1":{"type":"text","value":"today"}}, finalize=True)
        result = await call(service, "listening_get_attempt_result", setId="fixture-audio", attemptId="fixture-attempt")
        assert "completed" in result and "fixture-attempt" in result

if __name__=="__main__":
    start=now()
    with tempfile.TemporaryDirectory(prefix="kuro-live-owners-") as tmp, contextlib.ExitStack() as stack:
        asyncio.run(workflows(Path("C:/GPT_MCPtool"), Path("C:/project"),Path(tmp),stack))
    save("isolated-writes.json", {"start":start,"end":now(),"temporary_data_removed":not Path(tmp).exists(),"events":EVENTS})
