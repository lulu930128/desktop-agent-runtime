"""Exact Addons package gate for the normal-Windows relay, not UI activation.

No alternate interpreter/index, production service, private data or Qt overrides.
The PowerShell caller checks environment idleness immediately before each write.
"""
import argparse
import base64
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FORMAL = ROOT / "envs/kuro-llm310"
VERSION = "6.11.1"
FILENAME = "pyside6_addons-6.11.1-cp310-abi3-win_amd64.whl"
SHA256 = "0d13c4dfd671b050a48e4f8d8ddc724b7248f9c0437e7fc47fdf316278572923"
EXISTING = ("PySide6-Essentials", "shiboken6")
DIST_INFO = "pyside6_addons-6.11.1.dist-info"
DERIVED_FILENAME = FILENAME.replace("-cp310", "-1w6owned-cp310")
PROVENANCE = DIST_INFO + "/W6_ORIGIN.json"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(run, name, value):
    with (run / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def command(run, name, argv):
    # Refuse before executing a command, including stdout/stderr collisions.
    paths = [run / (name + suffix) for suffix in (".json", ".stdout", ".stderr")]
    require(not any(p.exists() for p in paths), "Command receipt already exists: " + name)
    started = datetime.now(timezone.utc).isoformat()
    process = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=600)
    for path, data in zip(paths[1:], (process.stdout, process.stderr)):
        with path.open("xb") as stream:
            stream.write(data)
    write(run, name + ".json", dict(argv=argv, exit=process.returncode, utc=started))
    return process


def pip(run, name, *args):
    return command(run, name, [sys.executable, "-I", "-B", "-m", "pip", "--isolated",
                              "--disable-pip-version-check", *args])


def package_files():
    result = {}
    for name in EXISTING:
        dist = metadata.distribution(name)
        require(dist.version == VERSION, "Existing Qt version mismatch: " + name)
        for entry in dist.files:
            path = no_redirect(Path(dist.locate_file(entry))).resolve(strict=True)
            require(path.is_relative_to(FORMAL.resolve()), "Qt file outside formal env")
            result[path.relative_to(FORMAL).as_posix()] = sha(path.read_bytes())
    return result


def snapshot(run):
    try:
        metadata.distribution("PySide6-Addons")
    except metadata.PackageNotFoundError:
        pass
    else:
        raise RuntimeError("Addons already present: do not reinstall; review current preflight")
    files = package_files()
    with zipfile.ZipFile(run / "QtPreimage.zip", "x", zipfile.ZIP_STORED) as archive:
        for name in files:
            archive.writestr(name, (FORMAL / name).read_bytes())
    with zipfile.ZipFile(run / "QtPreimage.zip") as archive:
        require(all(sha(archive.read(p)) == h for p, h in files.items()), "Backup readback failed")
    for name, args in (("list", ("list", "--format=json")), ("freeze", ("freeze", "--all")),
                       ("check", ("check",)), ("version", ("--version",))):
        result = pip(run, name + "-before", *args)
        require(result.returncode == 0, "Baseline pip " + name + " failed; no install")
    write(run, "Baseline.json", dict(executable=sys.executable, prefix=sys.prefix,
          python=sys.version, packages={name: {"version": metadata.version(name),
              "location": str(metadata.distribution(name).locate_file(""))} for name in EXISTING},
          files=files, backupSha256=sha((run / "QtPreimage.zip").read_bytes())))
    # Keep process receipts distinct from probe JSON on case-insensitive Windows.
    command(run, "preflight-before-process", [sys.executable, "-I", "-B", str(HERE / "w6_preflight.py"),
            "--output", str(run / "Preflight-before.json")])
    probe = json.loads((run / "Preflight-before.json").read_text(encoding="utf-8"))
    require(not probe["overrideNames"] and probe["formalInterpreter"] and probe["qtVersion"] == VERSION,
            "Unsafe Qt override or wrong interpreter/Qt version")
    for name in ("PySide6", "shiboken6", "PySide6.QtCore", "PySide6.QtWidgets"):
        observed = probe["modules"][name]
        require(observed.get("status") == "PASS" and
                Path(observed["origin"]).resolve().is_relative_to(FORMAL.resolve()), "Existing Qt origin invalid")


def record_hash(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")


def no_redirect(path):
    """Reject junctions/reparse points as well as symlinks, including ancestors."""
    path = path.absolute()
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and
                not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "Path redirects: " + str(part))
    return path


def safe_name(name):
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix() == name and
            all(p not in (".", "..") and not p.endswith((".", " ")) for p in path.parts) and
            not any(c in name for c in ("\\", ":", "\x00")) and ".data/" not in name,
            "Unsafe wheel path: " + name)
    require(not any(p.split(".")[0].upper() in
                    {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
                     *[f"LPT{i}" for i in range(1, 10)]} for p in path.parts), "Reserved wheel path")


def target_path(site, name):
    safe_name(name)
    current = no_redirect(site)
    for component in PurePosixPath(name).parts:
        if current.exists():
            require(current.is_dir(), "Non-directory wheel parent: " + str(current))
            matches = [p.name for p in current.iterdir() if p.name.casefold() == component.casefold()]
            require(not matches or matches == [component], "Case collision: " + name)
        current = no_redirect(current / component)
    return current


def record_rows(raw, label):
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8")), strict=True))
    require(all(len(r) == 3 and r[0] for r in rows), "Malformed RECORD: " + label)
    return rows


def ownership_index(site):
    """Inventory every distribution, not only the expected shared owner."""
    owners, manifests = {}, {}
    for directory in sorted(site.iterdir()):
        if directory.name.lower().endswith(".egg-info"):
            # Legacy packages without RECORD cannot be accepted as shared owners.
            top = no_redirect(directory / "top_level.txt").read_text(encoding="utf-8").splitlines()
            require(top and not {s.casefold() for s in top} & {"pyside6", "pyside6_addons"},
                    "Unknown legacy ownership: " + directory.name)
            manifests[directory.name + "/top_level.txt"] = sha((directory / "top_level.txt").read_bytes())
            continue
        if not directory.name.lower().endswith(".dist-info"):
            continue
        raw = no_redirect(directory / "RECORD").read_bytes()
        meta_raw = no_redirect(directory / "METADATA").read_bytes()
        meta = BytesParser().parsebytes(meta_raw)
        require(meta["Name"] and meta["Version"], "Missing distribution identity")
        for name, data in (("RECORD", raw), ("METADATA", meta_raw)):
            manifests[directory.name + "/" + name] = sha(data)
        seen = set()
        for name, digest, size in record_rows(raw, directory.name):
            # Installed RECORD permits ../Scripts and absolute paths. Normalize for
            # ownership lookup, but require canonical spelling for shared entries.
            key = os.path.abspath(site / name).casefold()
            # Existing pip/conda metadata can repeat optional pyc rows. Retain
            # every claim, so any wheel overlap still fails the sole-owner gate.
            # Non-pyc duplicates are malformed; no installed RECORD is repaired.
            require(key not in seen or name.endswith(".pyc"),
                    "Duplicate RECORD ownership: " + directory.name + "/" + name)
            seen.add(key)
            owners.setdefault(key, []).append(dict(distribution=meta["Name"], version=meta["Version"],
                record=directory.name + "/RECORD", path=name, hash=digest, bytes=size))
    return owners, manifests


def cache_claims(site, name, owners, installing):
    """pip uninstall also removes bytecode implied by a .py RECORD entry."""
    if not name.endswith(".py"):
        return
    path = site / name
    adjacent = {str(path.with_suffix(s).absolute()).casefold() for s in (".pyc", ".pyo")}
    prefix = str((path.parent / "__pycache__" / (path.stem + ".")).absolute()).casefold()
    def matches(key):
        return key in adjacent or (key.startswith(prefix) and key.endswith(".pyc"))
    for key, claimed in owners.items():
        if matches(key):
            require(not installing and all(c["record"] == DIST_INFO + "/RECORD" for c in claimed),
                    "Implicit bytecode ownership overlap: " + name)
    candidates = [no_redirect(path.with_suffix(s)) for s in (".pyc", ".pyo")]
    cache = no_redirect(path.parent / "__pycache__")
    if cache.exists():
        candidates.extend(no_redirect(p) for p in cache.iterdir() if matches(str(p.absolute()).casefold()))
    if installing:
        require(not any(p.exists() or p.is_symlink() for p in candidates), "Existing implicit bytecode overlap: " + name)


def archive_records(archive):
    names = [i.filename for i in archive.infolist() if not i.is_dir()]
    require(len({n.casefold() for n in names}) == len(names), "Duplicate wheel paths")
    for item in archive.infolist():
        safe_name(item.filename.rstrip("/"))
        require(not stat.S_ISLNK(item.external_attr >> 16), "Wheel symlink")
    rows = record_rows(archive.read(DIST_INFO + "/RECORD"), "wheel")
    require(len({r[0].casefold() for r in rows}) == len(rows), "Duplicate wheel RECORD")
    require({r[0] for r in rows} == set(names), "Wheel RECORD coverage mismatch")
    records = {r[0]: r[1:] for r in rows}
    for name in names:
        data = archive.read(name)
        expected = ["", ""] if name == DIST_INFO + "/RECORD" else [record_hash(data), str(len(data))]
        require(records[name] == expected, "Wheel RECORD hash/size mismatch: " + name)
    return names, records


def wheel_contents(wheel, site):
    """Reject path redirection, collisions and wrong package metadata before pip."""
    from pip._vendor.packaging.tags import sys_tags
    from pip._vendor.packaging.utils import parse_wheel_filename
    from pip._vendor.packaging.specifiers import SpecifierSet
    no_redirect(wheel)
    require(wheel.name == FILENAME and sha(wheel.read_bytes()) == SHA256, "Official wheel SHA/name mismatch")
    require(bool(parse_wheel_filename(wheel.name)[3] & set(sys_tags())), "Wheel tag incompatible")
    with zipfile.ZipFile(wheel) as archive:
        names, records = archive_records(archive)
        owners, manifests = ownership_index(site)
        overlaps = []
        for name in names:
            path = target_path(site, name)
            claimed = owners.get(str(path).casefold(), [])
            if not path.exists():
                require(not claimed, "Missing owned wheel target: " + name)
                cache_claims(site, name, owners, installing=True)
                continue
            require(path.is_file(), "Existing non-file overlap: " + name)
            require(len(claimed) == 1, "Unknown or multiple RECORD owner overlap: " + name)
            owner = claimed[0]
            require(owner["distribution"].lower().replace("_", "-") == "pyside6-essentials" and
                    owner["version"] == VERSION and
                    owner["record"] == "pyside6_essentials-6.11.1.dist-info/RECORD" and
                    owner["path"] == name and name.startswith("PySide6/"),
                    "Unapproved owner/version/path overlap: " + name)
            data, existing = archive.read(name), path.read_bytes()
            require(data == existing, "Different bytes overlap: " + name)
            require([owner["hash"], owner["bytes"]] == [record_hash(existing), str(len(existing))],
                    "Owner RECORD hash/size mismatch: " + name)
            overlaps.append(dict(path=name, owners=claimed, existingSha256=sha(existing),
                wheelSha256=sha(data), existingBytes=len(existing), wheelBytes=len(data),
                identical=True, decision="RETAIN_ESSENTIALS_ONLY_EXCLUDE_FROM_ADDONS"))
        meta = BytesParser().parsebytes(archive.read("pyside6_addons-6.11.1.dist-info/METADATA"))
        require(meta["Name"].lower().replace("_", "-") == "pyside6-addons"
                and meta["Version"] == VERSION, "Wheel METADATA mismatch")
        require(bool(meta["Requires-Python"]) and
                SpecifierSet(meta["Requires-Python"]).contains(".".join(map(str, sys.version_info[:3]))),
                "Wheel Requires-Python mismatch")
        wheel_meta = archive.read("pyside6_addons-6.11.1.dist-info/WHEEL").decode()
        require("Tag: cp310-abi3-win_amd64" in wheel_meta, "Wheel internal tag mismatch")
        require(shutil.disk_usage(site).free > sum(i.file_size for i in archive.infolist()) * 2,
                "Insufficient free space")
    return dict(files=names, metadataName=meta["Name"], metadataVersion=meta["Version"],
                requiresDist=meta.get_all("Requires-Dist"), wheelMetadata=wheel_meta, sha256=SHA256,
                overlaps=overlaps, ownershipManifests=manifests, records=records)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue().encode("utf-8")


def build_install_wheel(run, original, receipt):
    """Local derivative: exclude shared payload AND RECORD rows before pip sees it.

    Never patch a live RECORD after installing: an interruption in that approach
    would leave pip able to uninstall Essentials' files (and their .pyc files).
    """
    house = run / "install-wheel"
    house.mkdir()
    target = house / DERIVED_FILENAME
    excluded = {r["path"] for r in receipt["overlaps"]}
    origin = dict(kind="W6_LOCAL_OWNERSHIP_DERIVATIVE", officialFilename=FILENAME,
                  officialSha256=SHA256, excluded=receipt["overlaps"],
                  policy="Essentials remains sole owner; no original payload bytes changed")
    payload = json.dumps(origin, sort_keys=True, indent=2).encode("utf-8")
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(target, "x", zipfile.ZIP_STORED) as dest:
        rows = []
        for name in receipt["files"]:
            if name in excluded or name == DIST_INFO + "/RECORD":
                continue
            data = source.read(name)
            dest.writestr(name, data)
            rows.append([name, record_hash(data), str(len(data))])
        dest.writestr(PROVENANCE, payload)
        rows.extend([[PROVENANCE, record_hash(payload), str(len(payload))], [DIST_INFO + "/RECORD", "", ""]])
        dest.writestr(DIST_INFO + "/RECORD", csv_bytes(rows))
    with zipfile.ZipFile(target) as archive:
        names, records = archive_records(archive)
    result = dict(filename=DERIVED_FILENAME, sha256=sha(target.read_bytes()), officialSha256=SHA256,
                  files=names, records=records, excluded=sorted(excluded), provenance=origin)
    validate_install_wheel(target, original, receipt, result)
    write(run, "InstallWheelReceipt.json", result)
    return result


def validate_install_wheel(target, original, receipt, derived):
    no_redirect(target)
    require(target.name == DERIVED_FILENAME and sha(target.read_bytes()) == derived["sha256"],
            "Derived wheel hash/name mismatch")
    require(sha(no_redirect(original).read_bytes()) == SHA256, "Original provenance changed")
    excluded = {r["path"] for r in receipt["overlaps"]}
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(target) as archive:
        names, records = archive_records(archive)
        require(set(names) == (set(receipt["files"]) - excluded) | {PROVENANCE}, "Derived file set mismatch")
        require(names == derived["files"] and records == derived["records"] and
                excluded == set(derived["excluded"]), "Derived receipt mismatch")
        for name in names:
            if name not in (PROVENANCE, DIST_INFO + "/RECORD"):
                require(archive.read(name) == source.read(name), "Derived payload changed: " + name)
        provenance = json.loads(archive.read(PROVENANCE))
        require(provenance == derived["provenance"] and provenance["officialSha256"] == SHA256 and
                provenance["excluded"] == receipt["overlaps"], "Derived provenance mismatch")


def installed_ownership(run):
    """Verify exact pip RECORD, hashes and sole ownership before accepting/uninstalling."""
    site = FORMAL / "Lib/site-packages"
    receipt = json.loads((run / "WheelReceipt.json").read_text(encoding="utf-8"))
    derived = json.loads((run / "InstallWheelReceipt.json").read_text(encoding="utf-8"))
    validate_install_wheel(run / "install-wheel" / DERIVED_FILENAME,
                           run / "wheelhouse" / FILENAME, receipt, derived)
    owners, manifests = ownership_index(site)
    require(all(manifests.get(n) == h for n, h in receipt["ownershipManifests"].items()),
            "Existing distribution ownership changed")
    record = DIST_INFO + "/RECORD"
    rows = record_rows(target_path(site, record).read_bytes(), record)
    generated = {DIST_INFO + "/" + n for n in ("INSTALLER", "REQUESTED", "direct_url.json")}
    require({r[0] for r in rows} == set(derived["files"]) | generated, "Installed RECORD file set mismatch")
    for name, digest, size in rows:
        data = target_path(site, name).read_bytes()
        expected = ["", ""] if name == record else [record_hash(data), str(len(data))]
        require([digest, size] == expected, "Installed RECORD hash/size mismatch: " + name)
        if name in derived["records"] and name != record:
            require([digest, size] == derived["records"][name], "Installed payload changed: " + name)
        claimed = owners.get(str((site / name).absolute()).casefold(), [])
        require(len(claimed) == 1 and claimed[0]["record"] == record and claimed[0]["version"] == VERSION,
                "Installed duplicate/unknown ownership: " + name)
        cache_claims(site, name, owners, installing=False)
    for overlap in receipt["overlaps"]:
        name = overlap["path"]
        require(owners.get(str((site / name).absolute()).casefold()) == overlap["owners"] and
                sha(target_path(site, name).read_bytes()) == overlap["existingSha256"],
                "Shared Essentials ownership/bytes changed: " + name)
    direct = json.loads((site / DIST_INFO / "direct_url.json").read_text(encoding="utf-8"))
    require(direct["archive_info"]["hashes"]["sha256"] == derived["sha256"], "pip origin hash mismatch")
    return dict(status="SINGLE_OWNER_PASS", sharedEssentialsFiles=len(receipt["overlaps"]),
                addonsRecordFiles=len(rows), officialSha256=SHA256, derivedSha256=derived["sha256"])


def prepare(run, local_wheel=None):
    if local_wheel:
        no_redirect(local_wheel)
    snapshot(run)
    house = run / "wheelhouse"
    house.mkdir()
    target = house / FILENAME
    if local_wheel:
        require(local_wheel.name == FILENAME and sha(local_wheel.read_bytes()) == SHA256,
                "Unverified local wheel")
        shutil.copyfile(local_wheel, target)
    else:
        with urllib.request.urlopen("https://pypi.org/pypi/PySide6-Addons/6.11.1/json", timeout=30) as response:
            raw = response.read()
        (run / "OfficialPyPI.json").write_bytes(raw)
        rows = [r for r in json.loads(raw)["urls"] if r["filename"] == FILENAME]
        require(len(rows) == 1, "Official wheel missing from metadata")
        row = rows[0]
        require(not row["yanked"] and row["digests"]["sha256"] == SHA256
                and row["url"].startswith("https://files.pythonhosted.org/"), "Official metadata mismatch")
        result = pip(run, "download", "download", "--no-index", "--no-deps", "--only-binary=:all:",
                     "--no-cache-dir", "--dest", str(house), row["url"] + "#sha256=" + SHA256)
        require(result.returncode == 0, "DOWNLOAD_BLOCKED; environment unchanged")
    receipt = wheel_contents(target, FORMAL / "Lib/site-packages")
    write(run, "WheelReceipt.json", receipt)
    build_install_wheel(run, target, receipt)


def package_delta(before, after):
    normalize = lambda rows: {r["name"].lower().replace("_", "-"): r["version"] for r in rows}
    expected = normalize(before)
    require("pyside6-addons" not in expected, "Baseline already contains Addons")
    expected["pyside6-addons"] = VERSION
    require(normalize(after) == expected, "Unexpected installed package delta")


def install(run):
    baseline = json.loads((run / "Baseline.json").read_text(encoding="utf-8"))
    require(package_files() == baseline["files"], "Qt changed since snapshot")
    require(sha((run / "QtPreimage.zip").read_bytes()) == baseline["backupSha256"], "Backup changed")
    wheel = run / "wheelhouse" / FILENAME
    site = FORMAL / "Lib/site-packages"
    receipt = json.loads((run / "WheelReceipt.json").read_text(encoding="utf-8"))
    require(wheel_contents(wheel, site) == receipt, "Wheel/ownership changed since prepare")
    derived = json.loads((run / "InstallWheelReceipt.json").read_text(encoding="utf-8"))
    target = run / "install-wheel" / DERIVED_FILENAME
    validate_install_wheel(target, wheel, receipt, derived)
    # Probe create/read/delete in existing destination parents before pip can
    # partially install. A denial stops here; never adjust ACL or elevate.
    parents = {site}
    for name in derived["files"]:
        parent = target_path(site, name).parent
        while not parent.exists():
            parent = parent.parent
        parents.add(parent)
    checked = []
    phase = "CREATE"
    try:
        for parent in sorted(parents):
            phase = "CREATE"
            with tempfile.NamedTemporaryFile(prefix=".w6-write-probe-", dir=parent) as probe:
                phase = "WRITE_READBACK"
                probe.write(b"W6 permission probe\n")
                probe.flush()
                # Windows O_TEMPORARY requires delete-sharing; use the same
                # handle rather than reopening it with pathlib's normal open.
                probe.seek(0)
                require(probe.read() == b"W6 permission probe\n", "Write probe readback failed")
                phase = "DELETE_ON_CLOSE"
            require(not Path(probe.name).exists(), "Write probe cleanup failed")
            checked.append(str(parent))
    except OSError as exc:
        write(run, "WriteAccess.json", dict(status="BLOCKED_BEFORE_PIP", phase=phase,
              checked=checked, error=str(exc)))
        raise
    write(run, "WriteAccess.json", dict(status="PASS", checked=checked))
    temp = run / "pip-temp"
    temp.mkdir()
    saved = {n: os.environ.get(n) for n in ("TEMP", "TMP")}
    try:
        os.environ.update(TEMP=str(temp), TMP=str(temp))
        result = pip(run, "install", "install", "--no-index", "--no-deps", "--only-binary=:all:",
                     "--no-cache-dir", "--no-compile", "--no-user", "--prefix", str(FORMAL),
                     "--report", str(run / "PipInstallReport.json"), str(target))
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    require(result.returncode == 0, "Install failed: preserve evidence; review rollback before restarting Kuro")
    write(run, "InstalledOwnership.json", installed_ownership(run))


def verify(run):
    baseline = json.loads((run / "Baseline.json").read_text(encoding="utf-8"))
    require(package_files() == baseline["files"], "Essentials/shiboken files changed")
    ownership = installed_ownership(run)
    listing = pip(run, "list-after", "list", "--format=json")
    require(listing.returncode == 0, "pip list failed")
    package_delta(json.loads((run / "list-before.stdout").read_bytes()), json.loads(listing.stdout))
    result = pip(run, "check-after", "check")
    require(result.returncode == 0, "New pip dependency failure")
    result = command(run, "preflight-after-process", [sys.executable, "-I", "-B", str(HERE / "w6_preflight.py"),
                     "--output", str(run / "Preflight-after.json")])
    require(result.returncode == 0, "Formal WebEngine preflight failed")
    receipt = json.loads((run / "Preflight-after.json").read_text(encoding="utf-8"))
    require(receipt["status"] == "PREREQUISITES_PASS" and
            receipt["schemeRegistration"] == "PASS_BEFORE_APPLICATION", "Prerequisite gate failed")
    write(run, "PackageGate.json", dict(status="PREREQUISITES_PASS", installedOnly="PySide6-Addons==6.11.1",
          essentialsAndShibokenBytesUnchanged=True, ownership=ownership,
          nativeWindow="UNVERIFIED", productionAdoption=False))


def rollback(run):
    require(json.loads((run / "install.json").read_text(encoding="utf-8"))["exit"] == 0,
            "Partial install needs manual review; automatic uninstall not qualified")
    baseline = json.loads((run / "Baseline.json").read_text(encoding="utf-8"))
    require(package_files() == baseline["files"], "Existing Qt changed; manual review required")
    # Reject the original wheel's broad RECORD, missing entries and tampered
    # payload before pip uninstall is allowed to calculate any delete paths.
    installed_ownership(run)
    receipt = json.loads((run / "InstallWheelReceipt.json").read_text(encoding="utf-8"))
    dist = metadata.distribution("PySide6-Addons")
    require(dist.version == VERSION, "Different Addons version; do not uninstall")
    site = (FORMAL / "Lib/site-packages").resolve()
    permitted = set(receipt["files"]) | {"pyside6_addons-6.11.1.dist-info/" + n
                                         for n in ("INSTALLER", "REQUESTED", "direct_url.json")}
    for entry in dist.files:
        path = Path(dist.locate_file(entry)).resolve()
        require(path.is_relative_to(site) and path.relative_to(site).as_posix() in permitted,
                "Unexpected rollback RECORD path; manual review required")
    result = pip(run, "rollback", "uninstall", "--yes", "PySide6-Addons")
    require(result.returncode == 0 and package_files() == baseline["files"], "Rollback failed")
    result = pip(run, "list-rollback", "list", "--format=json")
    require(result.returncode == 0 and json.loads(result.stdout) ==
            json.loads((run / "list-before.stdout").read_bytes()), "Rollback package mismatch")
    require(pip(run, "check-rollback", "check").returncode == 0, "Rollback pip check failed")
    write(run, "RollbackReceipt.json", dict(status="BASELINE_RESTORED"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "install", "verify", "rollback"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args()
    run = no_redirect(args.run).resolve(strict=True)
    require(run.is_relative_to(HERE / ".runtime"), "Evidence must be task-local")
    require(Path(sys.prefix).resolve() == FORMAL.resolve() and Path(sys.executable).parent == FORMAL,
            "Use exact formal interpreter")
    require(sys.flags.isolated and sys.dont_write_bytecode, "Use -I -B")
    require(sys.version_info[:2] == (3, 10) and sys.maxsize > 2**32, "Use formal CPython 3.10 x64")
    try:
        if args.stage == "prepare":
            prepare(run, args.wheel)
        else:
            globals()[args.stage](run)
    except Exception as exc:
        write(run, args.stage + "-Failure.json", dict(type=type(exc).__name__, error=str(exc)))
        print(args.stage + " BLOCKED: " + str(exc), file=sys.stderr)
        return 2
    print(args.stage + " PASS (package evidence only; no UI activation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
