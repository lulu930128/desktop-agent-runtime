"""Source-pinned Web assets. No receipt, environment flag or renderer grants adoption.

The source pin selects the signed owner bundle; it does not assert native
gesture acceptance. Missing or invalid assets stop startup without a fallback.
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
    fingerprint='1fa9b1646a024b573fabe019e4fd940f0e34962f87db6b46cba52408290f3e2a',
    manifest_sha256='fc759d5a95cfa53b0997e3d57ca68dc1c9d40675be9419d10de7a38b0a38ae9d',
    public_key='7fbee49c562d6aa6e4120326daa21843e4510463f92275f2a5a4db7efd276299',
    signature='7d56b8a64b6fd5de6ff3a4c22dd09aa63101f36a90083658d35db4cd94bc480e6f4b05d4db7864b49b038fba120886bee142a7b78ea39c57579d86a78609090d',
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
    """Verify the sole presentation and register its scheme before QApplication."""
    if not isinstance(RELEASE_PIN, OwnerBundlePin):
        raise TypeError("Explicit owner bundle pin required")
    from .qt_web_host import register_candidate_scheme
    bundle = VerifiedOwnerBundle.load(Path(root) / "assets/qt-owner" / RELEASE_PIN.fingerprint, RELEASE_PIN)
    register_candidate_scheme()
    return bundle
