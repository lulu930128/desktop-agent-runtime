"""Source-pinned Web assets. No receipt, environment flag or renderer grants adoption.

RELEASE_PIN remains None until the exact existing-window native release gate.
Disposable harnesses verify a build pin explicitly and use the same host path.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType



@dataclass(frozen=True)
class OwnerBundlePin:
    fingerprint: str
    manifest_sha256: str
    public_key: str
    signature: str


RELEASE_PIN = OwnerBundlePin(
    fingerprint='dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e',
    manifest_sha256='c2920dff0455acfdbee2fcb9ae0a0f42cd1aa6c9d6b1690d54da5e377b765bed',
    public_key='0155b171027785abc70b0afcbba2e746fc49c7fb06b2cff705844acb2ca5da7b',
    signature='868e58bc3c994baf9f8d6d6e7661af4d8c01b479c9f925e9c2e2ad93e1b71d31bef33ef848153e8b8a49b161869566395c469491b6cb62fba8d98715bbd18b04',
)

@dataclass(frozen=True)
class VerifiedOwnerBundle:
    pin: OwnerBundlePin
    assets: object

    @classmethod
    def load(cls, directory, pin):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from .qt_web_host import AssetBundle
        if not isinstance(pin, OwnerBundlePin): raise TypeError("Explicit owner bundle pin required")
        root = Path(directory).absolute()
        if root.resolve(strict=True) != root or root.name != pin.fingerprint:
            raise ValueError("Owner bundle location or redirect mismatch")
        manifest = (root / "candidate-manifest.json").read_bytes()
        if hashlib.sha256(manifest).hexdigest() != pin.manifest_sha256:
            raise ValueError("Pinned manifest mismatch")
        # Trust comes from the caller's source pin, not a key supplied by HTML
        # or a mutable manifest. The builder never persists the signing key.
        message = (pin.fingerprint + "\n" + pin.manifest_sha256).encode("ascii")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pin.public_key)).verify(bytes.fromhex(pin.signature), message)
        record = json.loads((root / "owner-build.json").read_text(encoding="utf-8"))
        lineage_hash = hashlib.sha256(json.dumps(record["lineage"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if lineage_hash != pin.fingerprint or record["manifestSha256"] != pin.manifest_sha256:
            raise ValueError("Pinned owner lineage mismatch")
        # Parse the bytes already pinned and signature-verified. Never reopen
        # a mutable manifest between verification and asset digest checks.
        bundle = AssetBundle(root, manifest_bytes=manifest)
        expected = {p.lstrip("/") for p in bundle.assets} | {"candidate-manifest.json", "owner-build.json"}
        if {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} != expected:
            raise ValueError("Unexpected owner asset files")
        if b"connect-src 'none'" not in bundle.assets["/work-panel.html"]:
            raise ValueError("Owner CSP absent")
        return cls(pin, MappingProxyType(dict(bundle.assets)))


def prepare_owner_presentation(root):
    """Called before QApplication; safe Widgets default imports no Addons."""
    if RELEASE_PIN is None: return None
    from .qt_web_host import register_candidate_scheme
    bundle = VerifiedOwnerBundle.load(Path(root) / "assets/qt-owner" / RELEASE_PIN.fingerprint, RELEASE_PIN)
    register_candidate_scheme()
    return bundle
