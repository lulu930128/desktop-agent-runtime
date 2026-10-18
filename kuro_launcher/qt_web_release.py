"""Source-pinned Web assets. No receipt, environment flag or renderer grants adoption.

The W7 source pin selects the signed owner bundle; it does not assert native
gesture acceptance. Setting it to None retains the explicit Widgets rollback.
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
    fingerprint='8ba8ea29313601f944f760b901410efb8fc92bc801199d3b0b72ba22b7fa9b14',
    manifest_sha256='425eff86d0426df19aa16e5142658f12f95504955037d623a16ebd633a230630',
    public_key='10733638989cee0420da1ba31b550d192dca6f91676d25524e079c40b77cb5f5',
    signature='c6aa35146177156cc7ef03aa2a1a9535e60c5f58a23a72ca612cd38faeada2fc5027ad287cd644e93e981c1746812bfe81636d791c17c1ba9303883d8e89e208',
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
    """Called before QApplication; explicit Widgets rollback imports no Addons."""
    if RELEASE_PIN is None: return None
    from .qt_web_host import register_candidate_scheme
    bundle = VerifiedOwnerBundle.load(Path(root) / "assets/qt-owner" / RELEASE_PIN.fingerprint, RELEASE_PIN)
    register_candidate_scheme()
    return bundle
