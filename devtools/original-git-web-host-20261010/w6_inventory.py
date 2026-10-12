"""Read-only W6 inventory. Deliberately has no cutover or deletion operation."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATES = {
    "kuro_launcher/qt_work_companion_view.py": "whole-module candidate after all native gates and caller migration",
    "kuro_launcher/qt_work_companion_theme.py": "whole-module candidate after all native gates and caller migration",
    "kuro_launcher/qt_app.py": "partial only: presentation builders/render handlers; retain window, tray, client, controller, lifecycle",
    "kuro_launcher/qt_core_pages.py": "partial only: TodayPage/SchedulePage/CoreHealthPage presentation; review constants separately",
}
PRESERVE = ["launcher_qt.py", "桌寵啟動器.vbs", "kuro_launcher/qt_controller.py",
    "kuro_launcher/qt_chat_client.py", "kuro_launcher/qt_notifications.py",
    "kuro_launcher/core_runtime.py", "kuro_core/schedule_api.py", "kuro_core/schedule_store.py",
    "kuro_core/schedule_notifications.py", "kuro_core/storage.py"]


def source_graph(root=ROOT):
    """Syntactic graph only: includes nested callbacks, not dynamic dispatch proof."""
    graph = {}
    for relative in [*CANDIDATES, "launcher_qt.py", "kuro_launcher/qt_web_host.py"]:
        source = (root / relative).read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        def owner(node):
            names = []
            while node in parents:
                node = parents[node]
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(node.name)
            return ".".join(reversed(names)) or "<module>"
        attributes, calls, imports = [], [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                attributes.append(dict(name=node.attr, line=node.lineno, owner=owner(node), access=type(node.ctx).__name__))
            if isinstance(node, ast.Call):
                calls.append(dict(target=ast.unparse(node.func), line=node.lineno, owner=owner(node),
                                  expression=ast.unparse(node)))
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(dict(line=node.lineno, expression=ast.unparse(node)))
        graph[relative] = dict(imports=imports, attributes=attributes, calls=calls,
            observers=[c for c in calls if c["target"].endswith((".connect", ".disconnect", ".start", ".stop", ".singleShot"))],
            reverseSelfCalls={name: [c for c in calls if c["target"] == "self." + name]
                              for name in sorted({n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)})})
    return graph


def native_receipts(root=ROOT):
    result = []
    for folder in ("native-candidate-W3-20261011T0750039855024Z", "native-candidate-W5-20261011T0751593632426Z"):
        path = root / "devtools/original-git-web-host-20261010/.runtime" / folder / "NativeResult.json"
        if not path.is_file():
            result.append(dict(path=str(path), status="UNVERIFIED", reason="Receipt absent"))
            continue
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8-sig"))
        # Absent close fields remain absent, never backfill W3 from W5.
        result.append(dict(path=str(path.relative_to(root)), sha256=hashlib.sha256(raw).hexdigest(),
            fields={k: value[k] for k in ("checkpoint", "executable", "native", "qt", "offTheRecord",
                    "brokerClosed", "chatThreadStopped", "serviceExit", "nativeChecksFailed", "exit",
                    "productionAdoption", "humanReview", "ime") if k in value}))
    return result


def inventory(root=ROOT):
    rows = []
    for relative, disposition in CANDIDATES.items():
        raw = (root/relative).read_bytes()
        tree = ast.parse(raw.decode("utf-8-sig"))
        rows.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "disposition": disposition,
            "symbols": [{"name": node.name, "line": node.lineno, "endLine": node.end_lineno}
                for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef))]})
    manifest = json.loads((root/"docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json").read_text(encoding="utf-8-sig"))
    return {"mode": "DRY_RUN_ONLY", "gate": "BLOCKED", "reason": "Formal dependencies and existing-window native handoff must be verified independently; this inventory cannot authorize adoption",
        "deletionAuthorized": False, "cutoverExecuted": False, "w7Started": False,
        "candidates": rows, "preserve": [{"path": p, "sha256": hashlib.sha256((root/p).read_bytes()).hexdigest()} for p in PRESERVE],
        "g7Absent": [r["path"] for r in manifest["files"] if not (root/r["path"]).exists()],
        "sourceGraph": source_graph(root), "nativeReceipts": native_receipts(root),
        "visualDecision": "User accepted original Web visuals for W6; historical strict metrics are retained separately",
        "requiredNativeEvidence": ["Exact formal interpreter Addons/WebEngine/WebChannel and pre-application scheme", "Existing QMainWindow tray/X/reveal/Quit/restart/second launch and exclusive observers", "W2 custom scheme/QWebChannel/CSP/permission/thread",
            "W3 Qt WebEngine + single Qt client disposable WS + native interaction", "W4 native confirmation/effective profile/device failure",
            "W5 Core Today/Schedule + sole tray notification claim-authorize-ack"],
        "rollback": "No production adoption. Retain current Widgets/VBS and exact preimages; never reset the dirty worktree."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = args.output.resolve()
    if not path.is_relative_to(HERE/".runtime") or path.exists():
        parser.error("Use a new task .runtime evidence path")
    result = inventory()
    query = subprocess.run(["rg", "-n", "qt_work_companion|WorkCompanionView|ComposerEdit|transcript_html|qt_core_pages|TodayPage|SchedulePage|CoreHealthPage|qt_web_host",
        "kuro_launcher", "launcher_qt.py", "tests", "devtools/original-git-web-host-20261010/frontend"],
        cwd=ROOT, capture_output=True, encoding="utf-8", errors="strict")
    if query.returncode not in (0, 1):
        raise RuntimeError(query.stderr)
    result["referenceInventory"] = query.stdout.splitlines()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": result["mode"], "gate": result["gate"], "candidates": len(result["candidates"]), "g7Absent": len(result["g7Absent"])}))
    return 0  # Inventory completed; never means the cutover gate passed.


if __name__ == "__main__":
    raise SystemExit(main())
