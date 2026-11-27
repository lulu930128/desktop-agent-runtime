"""Reopen a completed isolated learner using the original Hub and compare all stored question snapshots."""
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "kuro-real-api-20261123"))
from isolated_writes import study_hub
from live import ROOT

result = {}
for f in HERE.glob("teacher-test-*.json"):
    run = json.loads(f.read_text(encoding="utf-8"))
    if not run.get("model_loop_completed"):
        continue
    data = (ROOT / run["test_store"]).resolve()
    assert data.is_relative_to((ROOT / ".git/kuro-production-tools-20261123/teacher-test-hub").resolve())
    assert (data / "study.db").is_file()
    with study_hub(ROOT.parent / "japanese-study-hub", "JSTUDY", data) as url:
        with urlopen(url + "/api/v1/practice/sessions/" + quote(run["session_id"], safe="")) as response:
            owner = json.load(response)
    assert owner == run["owner_readback"]
    calls = run["calls"]
    record_index = next(i for i, call in enumerate(calls) if call["tool"] == "study_record_practice")
    preview = next(call for call in reversed(calls[:record_index]) if call["tool"] == "study_preview_practice_record")
    exact = preview["arguments"] == calls[record_index]["arguments"]
    questions = owner["questions"]
    result[f.name] = {
        "reopened_original_hub": True, "readback_equal": True, "preview_equal_to_record": exact,
        "fixture_store": run["test_store"], "session": run["session_id"], "submission": owner["session"]["submission_id"],
        "source": owner["session"]["source"], "score": owner["summary"],
        "questions": [{"id": q["question_key"], "snapshot_hash": q["snapshot_hash"],
                       "answer": q["response"]["answer"], "answer_result": q["response"]["answer_result"],
                       "target_assessments": [(t.get("assessment") or {}).get("result") for t in q["targets"]],
                       "diagnosis_events": [{"code": e.get("diagnosis_code") or e.get("code"),
                                             "definition_version": e.get("definition_version")}
                                            for e in q["response"].get("diagnosis_events", []) + [
                                                e for t in q["targets"] for e in (t.get("assessment") or {}).get("diagnosis_events", [])]]}
                      for q in questions],
        "requests": len(run["requests"]), "model": run["model"], "effort": run["effort"],
        "diagnosis_catalog_read": "study_get_diagnosis_catalog" in [call["tool"] for call in calls]
    }
(HERE / "persistence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("Reopened", len(result), "persistent test learners.")
