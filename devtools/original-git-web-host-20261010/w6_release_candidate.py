"""Offline W6.E receipt review and source-pin rehearsal; never enables the UI.

The candidate pin below is a review proposal, not imported by production. Raw
receipts are unsigned observations; their hashes preserve identity, not origin.
Only the asset pin has an Ed25519 signature (builder self-attestation).
"""
import argparse
import ast
from dataclasses import asdict, replace
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RECEIPTS = HERE / '.runtime/w6-security-user-20261011T1357535580236Z'
OWNER_BUILD = HERE / '.runtime/w6-security-20261011T133551558915Z/OwnerBuild.json'
PIN_VALUES = dict(
    fingerprint='dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e',
    manifest_sha256='c2920dff0455acfdbee2fcb9ae0a0f42cd1aa6c9d6b1690d54da5e377b765bed',
    public_key='0155b171027785abc70b0afcbba2e746fc49c7fb06b2cff705844acb2ca5da7b',
    signature='868e58bc3c994baf9f8d6d6e7661af4d8c01b479c9f925e9c2e2ad93e1b71d31bef33ef848153e8b8a49b161869566395c469491b6cb62fba8d98715bbd18b04',
)
PIN_KEYS = dict(fingerprint='fingerprint', manifest_sha256='manifestSha256',
                public_key='publicKey', signature='signature')
PACKAGES = {'PySide6-Essentials', 'PySide6-Addons', 'shiboken6'}
MODULES = {'PySide6', 'shiboken6', 'PySide6.QtCore', 'PySide6.QtWidgets',
           'PySide6.QtWebChannel', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'}
QT_DLLS = {'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6WebChannel.dll',
           'Qt6WebEngineCore.dll', 'Qt6WebEngineWidgets.dll'}
RELEASE_SOURCE = 'kuro_launcher/qt_web_release.py'
PREIMAGE_SHA = 'ed65d342f7bdd6fdf7ecdd08f021b8e6797e5c45f873a374eccd0ae8b1d9de41'
ADOPTED_SHA = 'bf91caa1f6945b69fd366e05fc73199281d977324e17b14b1c589e12388261eb'


def release_preimage():
    """Only the exact reviewed pin delta is allowed; retain native provenance."""
    raw = (ROOT / RELEASE_SOURCE).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest in {PREIMAGE_SHA, ADOPTED_SHA}, 'Unreviewed release source drift')
    source = raw.decode('utf-8')
    if digest == ADOPTED_SHA:
        assignment = '\n\nRELEASE_PIN = OwnerBundlePin(\n' + ''.join(
            f'    {key}={value!r},\n' for key, value in PIN_VALUES.items()) + ')'
        source = source.replace(assignment, '', 1).replace(
            'from types import MappingProxyType\n',
            'from types import MappingProxyType\n\nRELEASE_PIN = None', 1)
    require(hashlib.sha256(source.encode()).hexdigest() == PREIMAGE_SHA,
            'Reviewed release preimage mismatch')
    return source


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def required_checks():
    tree = ast.parse((HERE / 'w6_existing_window.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'REQUIRED_CHECKS' for t in n.targets))
    require(isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
            and node.value.func.id == 'frozenset', 'Required checks declaration changed')
    return set(ast.literal_eval(node.value.args[0]))


def required_sources():
    tree = ast.parse((HERE / 'w6_existing_window.py').read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'source_hashes')
    names = next(n for n in function.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets))
    return set(ast.literal_eval(names.value))


def verify_round(native, security, preflight):
    """Recompute coverage/security from raw fields, not a receipt PASS alone."""
    required = required_checks()
    checks = native['checks']
    names = [row['name'] for row in checks]
    require(len(required) == 70 and len(checks) == 74 and len(set(names)) == 74,
            'Check count or duplicate names')
    require(all(row['pass'] is True for row in checks), 'Failed native check')
    require(required <= set(names) and set(native['coverage']['required']) == required
            and native['coverage']['missing'] == [] and native['coverage']['pass'] is True,
            'Required coverage mismatch')
    navigation = next(row for row in checks if row['name'] == 'navigation-denied')
    require(navigation.get('deniedCallbacks') == 3
            and navigation.get('probeHitsBefore') == navigation.get('probeHitsAfter') == 1,
            'Navigation denial side effects mismatch')
    require(native['native'] == 'AUTOMATED_EXISTING_WINDOW_PASS' and native['exit'] == 0,
            'Native did not pass')
    require(native['productionAdoption'] is False and native['humanReview'] == 'UNVERIFIED',
            'Unexpected adoption claim')
    require(native['sourceUnchangedDuringRun'] is True and len(native['sourceSha256']) == 13
            and set(native['sourceSha256']) == required_sources(),
            'Source coverage missing')
    current = {}
    for relative, expected in native['sourceSha256'].items():
        path = (ROOT / relative).resolve(strict=True)
        require(path.is_relative_to(ROOT), 'Source outside repo')
        current[relative] = sha(path)
        if relative == RELEASE_SOURCE:
            require(expected == PREIMAGE_SHA, 'Native release preimage mismatch')
            release_preimage()
        else:
            require(current[relative] == expected, 'Source drift: ' + relative)
    require(native['security'] == security, 'Separate security evidence mismatch')
    evaluator = module('w6_security_review', HERE / 'w6_security_probe.py')
    axes = evaluator.evaluate_security(security)
    require(axes == dict(network=True, asset=True, popup=True, storage=True)
            and security['axes'] == axes, 'Security axes failed')
    require(security['probeHitsBefore'] == security['probeHitsAfter'] == 1, 'Network hit increment')
    require(security['asset']['blockedByHost'] == 1 and security['asset']['unexpectedReplies'] == 0,
            'Asset denial absent')
    require(security['popup']['newObjects'] == 0 and security['popup']['deniedCallbacks'] == 1
            and security['popup']['discardedRequests'] == 1, 'Popup side effects')
    require(security['javascriptErrors'] == [] and security['javascriptErrorsComplete'] is True
            and security['javascriptErrorSamples'] == dict(initial=True, beforeReload=True,
                nativeFirst=True, nativeReload=True), 'JS samples incomplete')
    require(native['javascriptErrors'] == [] and native['javascriptErrorsObserved'] is True,
            'Native JS error evidence absent')
    require(native['windowClass'] == 'KuroQtLauncherWindow' and native['platform'] == 'windows'
            and native['connections'] == 1 and native['controllerCloseCount'] == 1
            and native['brokerClosed'] is True, 'Owner/lifecycle mismatch')
    require(native['webEngineEvents'] == [{'loadFinished': b} for b in [True]*3 + [False]*3],
            'Unexpected load/renderer event')
    formal = ROOT / 'envs/kuro-llm310'
    site = formal / 'Lib/site-packages'
    require(Path(native['executable']).resolve() == formal / 'python.exe', 'Wrong native Python')
    require(preflight['status'] == 'PREREQUISITES_PASS' and preflight['blockers'] == []
            and preflight['overrideNames'] == [] and preflight['applicationCreated'] is False
            and preflight['productionAdoption'] is False and preflight['formalInterpreter'] is True
            and preflight['schemeRegistration'] == 'PASS_BEFORE_APPLICATION', 'Preflight failed')
    require(Path(preflight['executable']).resolve() == formal / 'python.exe'
            and Path(preflight['prefix']).resolve() == formal
            and Path(preflight['expectedPrefix']).resolve() == formal
            and preflight['python'].startswith('3.10.12 '), 'Wrong preflight Python')
    require(preflight['qtVersion'] == '6.11.1' and set(preflight['packages']) == PACKAGES
            and all(v['version'] == '6.11.1' and Path(v['location']).resolve() == site
                    for v in preflight['packages'].values()), 'Package identity mismatch')
    for key, status, expected in [('modules', 'PASS', MODULES), ('loadedQtLibraries', 'OBSERVED', QT_DLLS)]:
        require(set(preflight[key]) == expected and all(v['status'] == status
                and Path(v['origin']).resolve().is_relative_to(formal) for v in preflight[key].values()),
                'Module/DLL identity mismatch')
        for name, row in preflight[key].items():
            relative = ('PySide6/' + name) if key == 'loadedQtLibraries' else (
                name + '/__init__.py' if name in {'PySide6', 'shiboken6'} else name.replace('.', '/') + '.pyd')
            require(Path(row['origin']).resolve() == site/relative, 'Module/DLL exact origin mismatch')
    require(Path(preflight['qtLibraryPath']).resolve() == site/'PySide6/lib', 'Qt library path mismatch')
    return dict(pid=native['pid'], checks=checks, required=sorted(required), sourceSha256=current,
                nativeSourceSha256=native['sourceSha256'],
                reviewedSourceDelta={k: dict(native=native['sourceSha256'][k], current=v)
                    for k, v in current.items() if v != native['sourceSha256'][k]},
                securityAxes=axes, legacyPopupPredicate=security['legacyPredicates']['popup'],
                physicalIme=native['physicalIme'], osNotificationDelivery=native['osNotificationDelivery'],
                voiceLive2D=native['voiceLive2D'])


def verify_receipts():
    relay = read(RECEIPTS / 'RelayResult.json')
    require(relay['status'] == 'AUTOMATED_NATIVE_PAIR_PASS' and relay['restartObserved'] is True
            and relay['productionAdoption'] is False and relay['humanApproval'] == 'UNVERIFIED'
            and len(relay['processes']) == 2, 'Relay gate mismatch')
    rounds = []
    for process, folder in zip(relay['processes'], ['first', 'first/restarted']):
        path = RECEIPTS / folder
        native = read(path / 'NativeResult.json')
        require(Path(process['receipt']).resolve() == path / 'NativeResult.json'
                and process['pid'] == native['pid'] and process['actualExit'] == process['reportedExit'] == 0,
                'Relay process correlation mismatch')
        for key, value in PIN_VALUES.items():
            require(native['bundle'][PIN_KEYS[key]] == value, 'Receipt bundle differs from proposal')
        rounds.append(verify_round(native, read(path / 'SecurityEvidence.json'), read(path / 'FormalPreflight.json')))
    require(rounds[0]['pid'] != rounds[1]['pid'] and rounds[0]['sourceSha256'] == rounds[1]['sourceSha256'],
            'Restart/source correlation mismatch')
    return dict(status='AUTOMATED_NATIVE_PASS', receiptRoot=str(RECEIPTS), rounds=rounds,
                rawSha256={p.relative_to(RECEIPTS).as_posix(): sha(p) for p in RECEIPTS.rglob('*') if p.is_file()},
                receiptAuthenticity='UNSIGNED_USER_SUPPLIED_OBSERVATIONS', humanApproval='UNVERIFIED',
                productionAdoption=False)


def proposed_source(pin):
    source = release_preimage()
    require(source.count('RELEASE_PIN = None') == 1, 'Formal pin is no longer disabled')
    source = source.replace('RELEASE_PIN = None\n', '', 1)
    marker = '\n\n@dataclass(frozen=True)\nclass VerifiedOwnerBundle:'
    require(source.count(marker) == 1, 'Release source structure changed')
    assignment = '\n\nRELEASE_PIN = OwnerBundlePin(\n' + ''.join(
        f'    {key}={value!r},\n' for key, value in asdict(pin).items()) + ')'
    candidate = source.replace(marker, assignment + marker, 1)
    compile(candidate, '<manual-pending-release-candidate>', 'exec')
    return candidate


def dry_run(output):
    from cryptography.exceptions import InvalidSignature
    from kuro_launcher import qt_web_release as release
    from PySide6.QtCore import QCoreApplication
    pin = release.OwnerBundlePin(**PIN_VALUES)
    release_preimage()
    require(release.RELEASE_PIN in (None, pin) and QCoreApplication.instance() is None,
            'Validation requires exact reviewed pin or rollback, and no application')
    active = release.RELEASE_PIN is not None
    directory = ROOT / 'assets/qt-owner' / pin.fingerprint
    # Both build receipts and immutable record must contain these EXACT values.
    for path in [OWNER_BUILD, directory/'owner-build.json']:
        record = read(path)
        require(all(record[wire] == PIN_VALUES[key] for key, wire in PIN_KEYS.items()),
                'OwnerBuild exact pin mismatch: ' + str(path))
    builder = module('w6_release_builder_review', HERE / 'build_owner_bundle.py')
    builder.verify(directory, builder.lineage())
    bundle = release.VerifiedOwnerBundle.load(directory, pin)
    rejected = []
    for label, bad, error in [('wrong-manifest', replace(pin, manifest_sha256='0'*64), ValueError),
                              ('wrong-signature', replace(pin, signature='0'*128), InvalidSignature),
                              ('wrong-key', replace(pin, public_key='0'*64), InvalidSignature)]:
        try:
            release.VerifiedOwnerBundle.load(directory, bad)
        except error:
            rejected.append(label)
        else:
            raise AssertionError('Accepted ' + label)
    for target in ['work-panel.html', 'candidate-manifest.json', 'owner-build.json', 'extra.js']:
        with tempfile.TemporaryDirectory(prefix='pin-negative-', dir=output) as folder:
            copied = Path(folder) / pin.fingerprint
            shutil.copytree(directory, copied)
            path = copied / target
            if target == 'owner-build.json':
                record = read(path); record['lineage']['originalCommit'] = 'tampered'
                path.write_text(json.dumps(record), encoding='utf-8')
            else:
                path.write_bytes((path.read_bytes() if path.exists() else b'') + b' tampered')
            try:
                release.VerifiedOwnerBundle.load(copied, pin)
            except ValueError:
                rejected.append(target)
            else:
                raise AssertionError('Accepted tamper: ' + target)
    try:
        bundle.assets['/unexpected'] = b'bad'
    except TypeError:
        rejected.append('frozen-assets')
    else:
        raise AssertionError('Asset map is mutable')
    candidate = proposed_source(pin)
    name = 'kuro_launcher._w6_manual_pending_rehearsal'
    rehearsal = types.ModuleType(name); rehearsal.__package__ = 'kuro_launcher'
    sys.modules[name] = rehearsal
    try:
        exec(compile(candidate, '<manual-pending-release-candidate>', 'exec'), rehearsal.__dict__)
        prepared = rehearsal.prepare_owner_presentation(ROOT)
        require(dict(prepared.assets) == dict(bundle.assets), 'Rehearsal load mismatch')
    finally:
        del sys.modules[name]
    require(release.RELEASE_PIN == (pin if active else None)
            and QCoreApplication.instance() is None, 'Formal state changed')
    if active:
        prepared = release.prepare_owner_presentation(ROOT)
        require(prepared.pin == pin and dict(prepared.assets) == dict(bundle.assets), 'Formal pinned load mismatch')
        require(sha(ROOT / RELEASE_SOURCE) == ADOPTED_SHA, 'Formal source changed during validation')
    before = release_preimage()
    patch = ''.join(difflib.unified_diff(before.splitlines(True), candidate.splitlines(True),
        fromfile='a/kuro_launcher/qt_web_release.py', tofile='b/kuro_launcher/qt_web_release.py'))
    # Preserve LF patch bytes on Windows; text-mode CRLF translation produces
    # an unappliable patch against the existing LF source.
    (output/'ReleasePin.proposed.patch').write_bytes(patch.encode('utf-8'))
    return dict(status='SOURCE_PIN_ACTIVE_VALIDATION_PASS' if active else 'SOURCE_PIN_DRY_RUN_PASS',
        sourceCutover=active, pin=asdict(pin), assets={k: hashlib.sha256(v).hexdigest() for k,v in bundle.assets.items()},
        negativeRejected=rejected, applicationCreated=False, productionAdoption=False,
        formalSourceSha256=sha(ROOT/'kuro_launcher/qt_web_release.py'),
        proposedUtf8LfSha256=hashlib.sha256(candidate.encode()).hexdigest(),
        patchSha256=sha(output/'ReleasePin.proposed.patch'), scheme='REGISTERED_BEFORE_APP_IN_REHEARSAL',
        approval='SOURCE_PIN_PRESENT_NOT_LIVE_ACCEPTANCE' if active else 'MANUAL_PENDING',
        trust='BUILDER_SELF_ATTESTATION_NOT_PUBLISHER_TRUST')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.resolve() != output or not output.is_relative_to(HERE/'.runtime'):
        parser.error('Use a new non-redirected task .runtime directory')
    require(sys.flags.isolated and sys.dont_write_bytecode, 'Use -I -B')
    require(Path(sys.executable).resolve() == ROOT/'envs/kuro-llm310/python.exe', 'Use formal Python')
    sys.path.insert(0, str(ROOT))
    output.mkdir(parents=True)
    try:
        receipts = verify_receipts()
        (output/'W6EAccepted.json').write_text(json.dumps(receipts, indent=2), encoding='utf-8')
        result = dry_run(output)
        (output/'ReleaseCandidate.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    except Exception as exc:
        (output/'Failure.json').write_text(json.dumps(dict(errorType=type(exc).__name__, error=str(exc))), encoding='utf-8')
        raise
    print(json.dumps(dict(automation=receipts['status'], sourcePin=result['status'],
        sourceCutover=result['sourceCutover'], liveAdoption='UNVERIFIED')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
