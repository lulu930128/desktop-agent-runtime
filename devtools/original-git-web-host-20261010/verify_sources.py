"""Read-only Git/WIP verification; only the evidence JSON is written."""
from pathlib import Path
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMIT = "995c23c7c8d1be62000229d58610d2214f3bb745"
PLAN = "docs/agent-runs/qt-ui-convergence-20261007/OriginalGitRendererQtWebHostPlan.md"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    before = json.loads((HERE / "WipBefore.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json").read_text(encoding="utf-8-sig"))
    inventory = json.loads((ROOT / "devtools/git-work-companion-parity-20261010/GitSourceInventory.json").read_text(encoding="utf-8-sig"))
    plan = (ROOT / PLAN).read_text(encoding="utf-8-sig")
    sources = []
    for item in manifest["files"][:6]:
        source = item["path"]
        raw = git("show", COMMIT + ":" + source)
        name = Path(source).name
        destination = HERE / "frontend" / source.removeprefix("pet-electron/renderer/")
        row = {"source": source, "commit": COMMIT, "blob": git("rev-parse", COMMIT + ":" + source).decode().strip(),
               "sha256": sha(raw), "recordedSha256": item["sha256"], "bytes": len(raw),
               "destination": destination.relative_to(ROOT).as_posix(), "destinationSha256": sha(destination.read_bytes()),
               "inventorySha256": inventory["HEAD"].get(name, {}).get("sha256"),
               "planRecordedShaPresent": item["sha256"] in plan if name != "work-panel.html" else None,
               "comparisons": {}}
        for revision in ["94065af5cfbaa3b5acbd5e7e19417a803cdaa122", "3baf05728921607d71306c98d43eaad155b0dbc1"]:
            obj = subprocess.run(["git", "cat-file", "-e", revision + ":" + source], cwd=ROOT, capture_output=True)
            row["comparisons"][revision] = ({"sha256": sha(git("show", revision + ":" + source)),
                                             "sameBytes": git("show", revision + ":" + source) == raw}
                                            if obj.returncode == 0 else {"status": "absent_in_local_git_tree"})
        row["pass"] = (row["sha256"] == row["destinationSha256"] == row["recordedSha256"] and
                       (name == "work-panel.html" or row["inventorySha256"] == row["sha256"]))
        sources.append(row)
    changed = []
    for relative, digest in before["files"].items():
        if relative == PLAN:
            continue  # only pre-existing file authorized for checkpoint append
        path = ROOT / relative
        current = sha(path.read_bytes()) if path.is_file() else None
        if current != digest:
            changed.append(relative)
    absent = [entry["path"] for entry in manifest["files"] if not (ROOT / entry["path"]).exists()]
    result = {"head": git("rev-parse", "HEAD").decode().strip(), "sources": sources,
              "g7Absent": absent, "wipBaselineFiles": len(before["files"]), "unrelatedChanges": changed,
              "planPreimageSha256": before["files"][PLAN], "planCurrentSha256": sha((ROOT / PLAN).read_bytes()),
              "status": git("status", "--porcelain=v1", "-z", "--untracked-files=all").decode(),
              "toolchain": {name: json.loads((ROOT / "pet-electron/node_modules" / name / "package.json").read_text())["version"] for name in ["vite", "typescript"]},
              "petPackageLockSha256": sha((ROOT / "pet-electron/package-lock.json").read_bytes())}
    result["planChangedFromBaseline"] = result["planPreimageSha256"] != result["planCurrentSha256"]
    result["planChangeNote"] = "Concurrent checkpoint observed; this run append/patch attempts returned access errors. Preserve current plan."
    result["pass"] = result["head"] == COMMIT and all(row["pass"] for row in sources) and len(absent) == 35 and not changed
    (HERE / "SourceVerification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": result["pass"], "sources": len(sources), "g7Absent": len(absent), "unrelatedChanges": changed}))
    return int(not result["pass"])


if __name__ == "__main__":
    raise SystemExit(main())
