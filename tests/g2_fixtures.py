"""Only synthetic G2 handoffs; imports never access real private files."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_producer(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "Open-LLM-VTuber/local_mcp" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


status_writer = load_producer("mail_status_handoff")
work_writer = load_producer("mail_work_handoff")


def study(stamp="2026-10-09T00:00:00Z"):
    return {"schemaVersion": 1, "source": "study", "updatedAt": stamp,
            "vocab": {"stats": {"total": 4, "due": 1, "withMistakes": 1},
                      "today": {"review": [{"word_id": "r1", "kanji": "synthetic review"}],
                                "focus": [{"wordId": "f1", "reading": "synthetic focus"}],
                                "new": [{"id": "n1", "meaning": "synthetic new"}]}},
            "today": {"items": []}}


def message(**kwargs):
    return {"id": "m1", "threadId": "t1", "subject": "Synthetic mail", "from": "Sender",
            "senderEmail": "sender@example.invalid", "date": "2026-10-09T00:00:00Z",
            "unread": True, "requiredEvent": False, "muted": False, "attention": False,
            "gmailImportant": True, "priorityLevel": "normal", "event": None, **kwargs}


def mail_snapshot(stamp="2026-10-09T00:00:00Z", messages=None):
    return {"updatedAt": stamp, "mail": {
        **dict.fromkeys(status_writer.COUNT_FIELDS.values(), 1),
        "privacy": {"bodyFetched": False, "attachmentsFetched": False, "mailboxModified": False},
        "messages": [message()] if messages is None else messages}}


def mail_status(stamp="2026-10-09T00:00:00Z", ok=True):
    return {"schemaVersion": 1, "source": "gmail_briefing", "lastSuccessAt": stamp,
            "lastAttemptAt": stamp, "lastAttemptOk": ok, "errorType": "" if ok else "provider_error",
            "counts": dict.fromkeys(status_writer.COUNT_FIELDS, 1),
            "privacy": {"bodyFetched": False, "attachmentsFetched": False, "mailboxModified": False}}
