"""Read-only W8 Qt source gate. Pet repair and native acceptance are blocked."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPECTED_SOURCES = json.loads((HERE / 'W8QtSources-20261017.json').read_text(encoding='utf-8'))
FINGERPRINT = '8ba8ea29313601f944f760b901410efb8fc92bc801199d3b0b72ba22b7fa9b14'
MANIFEST_SHA = '425eff86d0426df19aa16e5142658f12f95504955037d623a16ebd633a230630'


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify():
    from kuro_launcher.qt_web_release import RELEASE_PIN, VerifiedOwnerBundle
    actual = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in EXPECTED_SOURCES}
    drift = [name for name in EXPECTED_SOURCES if actual[name] != EXPECTED_SOURCES[name]]
    if drift:
        raise ValueError('W8 source drift: ' + ', '.join(drift))
    if RELEASE_PIN is None or RELEASE_PIN.fingerprint != FINGERPRINT or RELEASE_PIN.manifest_sha256 != MANIFEST_SHA:
        raise ValueError('W8 source pin mismatch')
    w7 = load_module('w8_historical_w7', 'w7_window_chrome_gate.py')
    historical_drift = [name for name, digest in w7.EXPECTED_SOURCES.items()
                        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    if historical_drift != ['kuro_launcher/qt_app.py']:
        raise ValueError('Unexpected W7 historical drift')
    builder = load_module('w8_official_builder', 'build_owner_bundle.py')
    built = builder.build(verify_only=True)
    if built['fingerprint'] != FINGERPRINT:
        raise ValueError('W8 builder lineage mismatch')
    bundle = VerifiedOwnerBundle.load(ROOT / 'assets/qt-owner' / FINGERPRINT, RELEASE_PIN)
    return dict(status='W8_QT_SOURCE_PIN_VERIFIED', sourceSha256=actual, assets=len(bundle.assets),
                historicalW7='EXPECTED_SOURCE_DRIFT', historicalDrift=historical_drift,
                petRepair='BLOCKED_PERMISSION_DENIED', nativeAcceptance='UNVERIFIED',
                productionAdoption=False)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    try:
        print(json.dumps(verify(), indent=2))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps(dict(status='BLOCKED', error=str(exc), productionAdoption=False)))
        raise SystemExit(2)
