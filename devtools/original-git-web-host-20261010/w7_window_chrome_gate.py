"""Read-only W7 source/pin gate. No GUI, service, historical receipt or pin writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FINGERPRINT = '8ba8ea29313601f944f760b901410efb8fc92bc801199d3b0b72ba22b7fa9b14'
MANIFEST_SHA = '425eff86d0426df19aa16e5142658f12f95504955037d623a16ebd633a230630'
# This is a new source checkpoint, never an amendment to W6 native evidence.
EXPECTED_SOURCES = {
    'launcher_qt.py': '518eb86bb9177bd55fc5c0aed797be750a867f18b6ae76ab5e7656d405c4ae6c',
    'kuro_launcher/qt_app.py': 'ff6d7ad5894647df4fc25097931afa8126b8ce10ceb9f18f2e5f650397cf3096',
    'kuro_launcher/qt_web_adapter.py': '3811bca7d741e247b380580f1847851863ec4a56786adbbc9959423774a739ad',
    'kuro_launcher/qt_web_host.py': 'c012de7ee9c5afa3baf31b0fee1c73ce9776f6dc28d6e3ef976b1810599ecac9',
    'kuro_launcher/qt_web_protocol.py': '4850ecc3b291b6a186451cc59cadde5cc355c268fde21849afb1cc26e5143c82',
    'kuro_launcher/qt_web_release.py': '5ba89d3ee1ee860e71ea135072c949a180f55ec0392054575e0561b1c4208e2a',
    'kuro_launcher/qt_controller.py': 'c75a3a4642ee79252c4bd4ba25800a4f8c90c26aceb25528a8eedada4f075bab',
    'kuro_launcher/qt_chat_client.py': 'a0c79f5ed4c4331ae23eab684e0cd9e99f23b1ea1f47cf4661410bd3385c4445',
    'kuro_launcher/qt_notifications.py': 'ca0584422608b0b1c018af58e2946e22b9582b8a427d271f09004cd3f8d47146',
    'devtools/original-git-web-host-20261010/build_owner_bundle.py': '6e84feebd1bf9b6b6aed10b4f772b07d127834685e91d4f14a9989bd49697496',
    'devtools/original-git-web-host-20261010/validate_candidate.py': '0b6caf7be9ea7da2f3a72db624e01c6bfb542f61ea38fe1e9cbbc9f3539b2fd3',
}


def verify():
    from kuro_launcher.qt_web_release import RELEASE_PIN, VerifiedOwnerBundle
    actual = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in EXPECTED_SOURCES}
    drift = [name for name in EXPECTED_SOURCES if actual[name] != EXPECTED_SOURCES[name]]
    if drift: raise ValueError('W7 source drift: ' + ', '.join(drift))
    if RELEASE_PIN is None or RELEASE_PIN.fingerprint != FINGERPRINT or RELEASE_PIN.manifest_sha256 != MANIFEST_SHA:
        raise ValueError('W7 source pin mismatch')
    spec = importlib.util.spec_from_file_location('w7_official_builder', HERE/'build_owner_bundle.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    built = builder.build(verify_only=True)  # six ORIGINALS, adapters, toolchain, signature and assets
    if built['fingerprint'] != FINGERPRINT: raise ValueError('W7 builder lineage mismatch')
    bundle = VerifiedOwnerBundle.load(ROOT/'assets/qt-owner'/FINGERPRINT, RELEASE_PIN)
    return dict(status='W7_SOURCE_PIN_VERIFIED', sourceSha256=actual, bundle=built,
                assets=len(bundle.assets), nativeGestures='UNVERIFIED', productionAdoption=False)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    try:
        print(json.dumps(verify(), indent=2))
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps(dict(status='BLOCKED', error=str(exc), productionAdoption=False)))
        raise SystemExit(2)
