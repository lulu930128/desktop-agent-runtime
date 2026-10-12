"""Build/verify immutable staging assets from the sole original renderer source.

No install, production entry activation, source copies, directory cleanup, or
overwrite. Existing content-addressed bundles must verify or fail closed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FRONTEND = HERE / "frontend"
ASSETS = ROOT / "assets/qt-owner"
COMMIT = "995c23c7c8d1be62000229d58610d2214f3bb745"
ORIGINALS = ("src/work-panel/main.ts", "src/work-panel/styles.css", "src/work-panel/model.ts",
             "src/work-panel/types.ts", "src/work-panel/schedule.ts", "work-panel.html")
ADAPTERS = ("src/owner-bootstrap.ts", "src/owner-bridge.ts", "src/owner-preferences.ts",
            "src/owner-presentation.ts", "src/canonical-model.ts", "vite.owner.config.mjs", "tsconfig.json")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def lineage():
    sources = {}
    for name in ORIGINALS:
        current = (FRONTEND / name).read_bytes()
        pinned = subprocess.check_output(["git", "show", COMMIT + ":pet-electron/renderer/" + name], cwd=ROOT)
        if current != pinned:
            raise ValueError("Immutable Git source mismatch: " + name)
        sources[name] = digest(current)
    for name in ADAPTERS:
        sources[name] = digest((FRONTEND / name).read_bytes())
    tools = {name: json.loads((ROOT / "pet-electron/node_modules" / name / "package.json").read_text(encoding="utf-8"))["version"]
             for name in ("vite", "typescript")}
    tools["node"] = subprocess.check_output(["node", "--version"], text=True).strip()
    tools["lockSha256"] = digest((ROOT / "pet-electron/package-lock.json").read_bytes())
    return dict(contract="kuro.qt.owner-build.v1", originalCommit=COMMIT, sources=sources,
                toolchain=tools, builderSha256=digest(Path(__file__).read_bytes()))


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def verify(directory, expected):
    from kuro_launcher.qt_web_host import AssetBundle
    from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle
    directory = Path(directory).resolve(strict=True)
    record = json.loads((directory / "owner-build.json").read_text(encoding="utf-8"))
    if record.get("lineage") != expected or record.get("fingerprint") != fingerprint(expected):
        raise ValueError("Owner bundle source/toolchain lineage mismatch")
    manifest = directory / "candidate-manifest.json"
    if digest(manifest.read_bytes()) != record.get("manifestSha256"):
        raise ValueError("Owner manifest hash mismatch")
    bundle = AssetBundle(directory)
    expected_files = {p.lstrip("/") for p in bundle.assets} | {"candidate-manifest.json", "owner-build.json"}
    actual_files = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual_files != expected_files:
        raise ValueError("Unexpected or missing owner bundle files")
    html = bundle.assets["/work-panel.html"]
    if b'Content-Security-Policy' not in html or b"connect-src 'none'" not in html:
        raise ValueError("Owner CSP absent")
    for data in bundle.assets.values():
        if b"SYNTHETIC preview" in data or b"fixture.context" in data:
            raise ValueError("Synthetic preview leaked into owner bundle")
    pin = OwnerBundlePin(record["fingerprint"], record["manifestSha256"], record["publicKey"], record["signature"])
    # Copies used by tamper tests needn't have the fingerprint basename; the
    # actual immutable target must, and is the only runtime-loadable location.
    if directory.name == pin.fingerprint:
        VerifiedOwnerBundle.load(directory, pin)
    else:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pin.public_key)).verify(
            bytes.fromhex(pin.signature), (pin.fingerprint + "\n" + pin.manifest_sha256).encode("ascii"))
    return dict(status="STAGING_VERIFIED", directory=str(directory), fingerprint=record["fingerprint"],
                manifestSha256=pin.manifest_sha256, publicKey=pin.public_key, signature=pin.signature,
                assets=len(bundle.assets), productionAdoption=False)


def build(*, verify_only=False):
    expected = lineage()
    target = ASSETS / fingerprint(expected)
    if target.exists():
        return verify(target, expected)
    if verify_only:
        raise FileNotFoundError("Owner bundle absent: " + str(target))
    # Refuse junction/symlink redirects; never build into arbitrary/user output.
    if ASSETS.resolve() != ASSETS or target.resolve() != target:
        raise ValueError("Owner asset path redirects outside its source location")
    target.mkdir(parents=True, exist_ok=False)
    command = ["node", str(ROOT / "pet-electron/node_modules/vite/bin/vite.js"), "build",
               "--config", "vite.owner.config.mjs", "--outDir", str(target)]
    process = subprocess.run(command, cwd=FRONTEND, capture_output=True, text=True, encoding="utf-8",
                             timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    print(process.stdout, end="")
    print(process.stderr, end="", file=sys.stderr)
    if process.returncode:
        raise RuntimeError("Owner build failed with exit " + str(process.returncode))
    if lineage() != expected:
        raise RuntimeError("Source changed during build; incomplete bundle retained, no activation")
    record = dict(lineage=expected, fingerprint=fingerprint(expected),
                  manifestSha256=digest((target / "candidate-manifest.json").read_bytes()),
                  productionAdoption=False)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    signing_key = Ed25519PrivateKey.generate()
    record["publicKey"] = signing_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    record["signature"] = signing_key.sign((record["fingerprint"] + "\n" + record["manifestSha256"]).encode("ascii")).hex()
    with (target / "owner-build.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
    return verify(target, expected)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE / ".runtime") or output.exists():
        parser.error("Use a new task .runtime evidence file")
    sys.path.insert(0, str(ROOT))
    try:
        result = build(verify_only=args.verify)
        code = 0
    except Exception as exc:
        result = dict(status="BLOCKED", errorType=type(exc).__name__, error=str(exc), productionAdoption=False)
        code = 2
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
