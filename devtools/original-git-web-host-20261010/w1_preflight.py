"""Read-only W1 integrity snapshot; writes only a new task-local evidence file."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from w1_smoke import execution_fingerprint

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = "af83df273602be3a616d6567855ea71d61a9ace7"
OLD = "995c23c7c8d1be62000229d58610d2214f3bb745"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        parser.error("Use a new output file inside the isolated task")
    status = git("status", "--porcelain=v1", "-z", "-uall").decode("utf-8")
    paths = [row[3:] for row in status.split("\0") if row]
    outside = {}
    for relative in paths:
        if relative.startswith(HERE.relative_to(ROOT).as_posix() + "/") or relative == "docs/agent-runs/kuro-original-web-cutover-20261010/W1Checkpoint.md":
            continue
        path = ROOT / relative
        outside[relative] = sha(path.read_bytes()) if path.is_file() else None
    recorded = json.loads((HERE / "SourceVerification.json").read_text(encoding="utf-8"))
    sources = []
    for item in recorded["sources"]:
        relative = item["destination"]
        values = {"worktree": sha((ROOT / relative).read_bytes()),
                  "w0": sha(git("show", BASE + ":" + relative)),
                  "original": sha(git("show", OLD + ":" + item["source"])),
                  "recorded": item["sha256"]}
        sources.append({"path": relative, "sha256": values, "pass": len(set(values.values())) == 1})
    result = {"utc": datetime.now(timezone.utc).isoformat(),
              "branch": git("branch", "--show-current").decode().strip(),
              "head": git("rev-parse", "HEAD").decode().strip(),
              "root": git("rev-parse", "--show-toplevel").decode().strip(),
              "status": status, "pathCount": len(paths),
              "indexSha256": sha((ROOT / ".git/index").read_bytes()),
              "staged": git("diff", "--cached", "--name-only").decode(),
              "outsideTaskFiles": outside, "sources": sources,
              "w1ExecutionFingerprint": execution_fingerprint()}
    if args.compare:
        before = json.loads(args.compare.read_text(encoding="utf-8"))
        previous = before["outsideTaskFiles"]
        result["outsideTaskChanges"] = sorted(p for p in set(outside) | set(previous)
                                               if p not in outside or p not in previous or outside[p] != previous[p])
        result["indexUnchanged"] = result["indexSha256"] == before["indexSha256"]
        result["w1ExecutionUnchanged"] = result["w1ExecutionFingerprint"] == before.get("w1ExecutionFingerprint")
    result["pass"] = (result["head"] == BASE and result["branch"] == "main" and not result["staged"]
                      and all(s["pass"] for s in sources) and not result.get("outsideTaskChanges")
                      and result.get("indexUnchanged", True) and result.get("w1ExecutionUnchanged", True))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["branch", "head", "pathCount", "staged", "pass"]}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
