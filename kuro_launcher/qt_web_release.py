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
    fingerprint='159c5832bca59216ceb3a4bb96f92ea031b9437a969700786c4b9ca29cf27811',
    manifest_sha256='8552e5f1d9ef3d01ef1003439a896472d4e2e0a7ff31cfba7d871bac1fe0e727',
    public_key='7efd7353a35415147b8898e072fe19df5ca77255b671c5796ac2dbfac618223e',
    signature='a3771ad7232ae1f7a822a3fb4d91f4b9474b8990a31c921d5b48a509118d382394bb51e169d6efea67ff883c1302a0748b0d479ca8f84dca622479f43b089602',
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
