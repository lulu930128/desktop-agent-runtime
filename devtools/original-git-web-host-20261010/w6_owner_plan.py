"""Executable W6 migration map of the existing window; never activates a host.

This is a syntactic reachability inventory, not a runtime/exclusivity proof.
Widget attributes and owner calls are reported for every connected callback,
including indirect self-method calls. Unknown/dynamic calls remain visible.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OWNERS = {"QtLauncherController", "QtRuntimeChatClient", "QtScheduleDelivery", "QSystemTrayIcon"}
WIDGETS = {"work_companion", "today_page", "schedule_page", "core_health_page", "runtime_detail",
           "settings_surface", "settings_stack", "stack", "chat_input", "chat_transcript",
           "history_list", "log_box", "perception_status", "chat_send_button", "memory_list",
           "preview_label", "character_combo", "project_combo", "model_combo", "thinking_combo"}
MUTATIONS = {"create_history", "delete_history", "select_history", "send_text", "send_capture",
             "start_profile", "stop_profile", "write_runtime_config", "schedule_materialize"}


def reachable(start, edges):
    found, pending = set(), [start]
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        pending.extend(edges.get(name, ()))
    return found


def analyze(source):
    tree = ast.parse(source)
    window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "KuroQtLauncherWindow")
    methods = {n.name: n for n in window.body if isinstance(n, ast.FunctionDef)}
    edges, attrs, calls, bindings, constructors = {}, {}, {}, [], []
    for name, method in methods.items():
        nodes = list(ast.walk(method))
        attrs[name] = {n.attr for n in nodes if isinstance(n, ast.Attribute)
                       and isinstance(n.value, ast.Name) and n.value.id == "self"}
        invokes = [n for n in nodes if isinstance(n, ast.Call)]
        calls[name] = [ast.unparse(n.func) for n in invokes]
        edges[name] = {n.func.attr for n in invokes if isinstance(n.func, ast.Attribute)
                       and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
                       and n.func.attr in methods}
        for call in invokes:
            target = ast.unparse(call.func)
            if target in OWNERS:
                constructors.append(dict(owner=target, method=name, line=call.lineno))
            if target.endswith(".connect"):
                callbacks = []
                for arg in call.args:
                    if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "self":
                        callbacks.append(arg.attr)
                    elif isinstance(arg, ast.Lambda):
                        callbacks.extend(n.func.attr for n in ast.walk(arg) if isinstance(n, ast.Call)
                                         and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                                         and n.func.value.id == "self")
                bindings.append(dict(signal=target[:-8], sourceMethod=name, line=call.lineno,
                                     expression=ast.unparse(call), callbacks=callbacks))
    for binding in bindings:
        reach = set().union(*(reachable(n, edges) for n in binding["callbacks"])) if binding["callbacks"] else set()
        touched = set().union(*(attrs.get(n, set()) for n in reach)) if reach else set()
        invoked = sorted({c for n in reach for c in calls.get(n, ())})
        binding.update(reachableMethods=sorted(reach), widgetAttributes=sorted(touched & WIDGETS),
                       ownerMutationCalls=[c for c in invoked if c.rsplit(".", 1)[-1] in MUTATIONS],
                       indirectCalls=invoked)
    counts = {name: sum(c["owner"] == name for c in constructors) for name in sorted(OWNERS)}
    return dict(contract="kuro.w6.owner-plan.v1", sourceTextSha256=hashlib.sha256(source.encode()).hexdigest(),
                mode="STATIC_PREPARATION_ONLY", productionAdoption=False, native="UNVERIFIED",
                ownerConstructors=constructors, ownerCounts=counts,
                ownerCountViolations={name: count for name, count in counts.items() if count != 1},
                bindings=bindings, connectedWidgetPaths=[b for b in bindings if b["widgetAttributes"]],
                retainedLifecycle=[n for n in ("reveal", "_create_tray", "_tray_activated", "cleanup",
                    "_ensure_desktop_entry", "quit_application", "closeEvent") if n in methods],
                limitations=["Attribute allowlist is not exhaustive; inspect all indirectCalls and dynamic dispatch",
                             "Constructor counts are lexical, not runtime instance counts",
                             "No cutover/deletion authorization or native acceptance is inferred"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(HERE / ".runtime"):
        parser.error("Use a fresh task .runtime output")
    raw = (ROOT / "kuro_launcher/qt_app.py").read_bytes()
    value = analyze(raw.decode("utf-8-sig"))
    value["sourceFileSha256"] = hashlib.sha256(raw).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(dict(mode=value["mode"], bindings=len(value["bindings"]),
                         widgetPaths=len(value["connectedWidgetPaths"]), ownerCounts=value["ownerCounts"])))
    return 2 if value["ownerCountViolations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
