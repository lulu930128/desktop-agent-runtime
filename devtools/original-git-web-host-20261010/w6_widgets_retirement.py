"""Bounded reverse-reference inventory. No deletion/cutover implementation."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRESENTATION = ('_build_ui', '_build_status_panels', '_build_settings_surface',
                '_build_chat_page', '_build_workspace_page', '_build_chat_memory_page',
                '_build_chat_tab', '_build_memory_tab', '_build_pet_page',
                '_build_settings_page', '_build_perception_page', '_build_tools_page')
FILES = ('kuro_launcher/qt_app.py', 'kuro_launcher/qt_work_companion_view.py',
         'kuro_launcher/qt_work_companion_theme.py', 'kuro_launcher/qt_core_pages.py')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def analyze():
    raw = (ROOT/FILES[0]).read_bytes()
    tree = ast.parse(raw.decode('utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'KuroQtLauncherWindow')
    methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    forward = {}
    reverse = {name: [] for name in methods}
    for name, node in methods.items():
        refs = []
        for n in ast.walk(node):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'self' and n.attr in methods:
                refs.append(dict(target=n.attr, line=n.lineno))
                reverse[n.attr].append(dict(caller=name, line=n.lineno))
        forward[name] = refs
    references = []
    pattern = re.compile(r'qt_work_companion|qt_core_pages|WorkCompanionView|ComposerEdit|transcript_html|TodayPage|SchedulePage|CoreHealthPage|ScheduleEditor|MAIN_NAV_KEYS|SETTINGS_LABELS')
    # Fixed source/test surfaces only; no env, private state, vendor, or logs.
    for path in [ROOT/'launcher_qt.py', *sorted((ROOT/'kuro_launcher').glob('*.py')), *sorted((ROOT/'tests').glob('*.py'))]:
        for line, text in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if pattern.search(text):
                references.append(dict(path=path.relative_to(ROOT).as_posix(), line=line, text=text.strip()))
    owners = []
    for n in ast.walk(cls):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {
                'QtLauncherController', 'QtRuntimeChatClient', 'QtScheduleDelivery', 'QSystemTrayIcon'}:
            owners.append(dict(name=n.func.id, line=n.lineno))
    allowlist = []
    for name in PRESENTATION:
        node = methods[name]
        fragment = b''.join(raw.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
        allowlist.append(dict(path=FILES[0], symbol=name, line=node.lineno, endLine=node.end_lineno,
            preimageSha256=digest(fragment), reverseReferences=reverse[name],
            condition='MANUAL_APPROVAL + REAL_PRODUCTION_WEB_ACCEPTED + all callers migrated/removed'))
    return dict(contract='kuro.w6.widgets-retirement.v1', deletionAuthorized=False,
        adoption='MANUAL_PENDING', sourceSha256={p:digest((ROOT/p).read_bytes()) for p in FILES},
        ownerConstructors=owners, forwardSelfReferences=forward, reverseSelfReferences=reverse,
        crossFileReferences=references, futureMethodAllowlist=allowlist,
        conditionalWholeModules=[dict(path=p, condition='Remove qt_app imports and port presentation tests after human adoption') for p in FILES[1:3]],
        defer=['qt_core_pages.py: constants, CorePage, ScheduleEditor and tests require separate caller migration',
               '__init__: remove only Widgets tail, preserve shared owner initialization and Web branch',
               'Callbacks, imports, module constants and APP_STYLE require final reverse-reference sweep'],
        preserveMethods=[n for n in methods if n not in PRESENTATION],
        preserveOwners=['launcher_qt.py', 'kuro_launcher/qt_controller.py', 'kuro_launcher/qt_chat_client.py',
                        'kuro_launcher/qt_notifications.py', 'kuro_launcher/qt_web_host.py',
                        'kuro_launcher/qt_web_adapter.py', 'kuro_launcher/core_runtime.py', 'kuro_core'],
        limitations=['Conservative lexical graph includes BOTH branches; not runtime counts',
                    'self callback references included; dynamic getattr, Qt virtual dispatch and external callers require manual review',
                    'No currently dead module: Widgets remains the formal entry',
                    'Allowlist is conditional planning, not an executable deletion list'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.resolve() != output or not output.is_relative_to(HERE/'.runtime'):
        parser.error('Use a fresh task .runtime evidence file')
    result = analyze()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(deletionAuthorized=False, owners=result['ownerConstructors'],
                         futureMethods=len(result['futureMethodAllowlist']))))


if __name__ == '__main__':
    main()
