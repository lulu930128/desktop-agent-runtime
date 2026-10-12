"""Interactive-user W1 relay. Smoke success is NOT whole-gate acceptance.

Uses the existing isolated Qt host unchanged. No package installation, production
imports, privileged operations, external endpoints, or security/GPU fallback.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WIDTH, HEIGHT = 1280, 720
OVERRIDES = (
    "QTWEBENGINE_DISABLE_SANDBOX", "QTWEBENGINE_CHROMIUM_FLAGS",
    "QTWEBENGINE_REMOTE_DEBUGGING", "QTWEBENGINEPROCESS_PATH",
    "QT_QPA_PLATFORM", "QT_OPENGL", "QT_QUICK_BACKEND", "QSG_RHI_BACKEND",
    "QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS", "QT_FONT_DPI",
    "QT_ENABLE_HIGHDPI_SCALING", "QT_AUTO_SCREEN_SCALE_FACTOR", "QT_SCALE_FACTOR_ROUNDING_POLICY",
)


class EvidenceError(RuntimeError):
    pass


class ValidationError(EvidenceError):
    pass


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


EXECUTION_FILES = (
    "qt_preview_host.py", "preview_protocol.py", "geometry.js", "typography.js",
    "w1_geometry_diagnostics.py", "capture_parity.py", "w1_smoke.py",
    "w1_preflight.py", "w1_import_probe.py", "Invoke-W1WindowsRelay.ps1", "summarize_w1.py",
)


def execution_fingerprint():
    # Required files deliberately use read_bytes without an is_file filter.
    # Missing helpers must fail closed, not shrink the execution manifest.
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in EXECUTION_FILES}


def fingerprint():
    manifest = execution_fingerprint()
    paths = []
    paths += sorted((HERE / "frontend/src").rglob("*"))
    paths += sorted((HERE / "frontend/dist").rglob("*"))
    paths += [HERE / ("frontend/" + name) for name in
              ("work-panel.html", "qt-preview.html", "vite.config.mjs", "tsconfig.json", "package.json")]
    manifest.update({p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in paths if p.is_file()})
    return manifest


def check_environment(environ):
    overrides = [key for key in OVERRIDES if environ.get(key)]
    if overrides:
        raise EvidenceError("Inherited override(s); use a normal unmodified PowerShell: " + ", ".join(overrides))


def run_logged(command, output, name, *, cwd=HERE, env=None, timeout=45):
    """Bounded owned child, preserving logs and an exit receipt even on timeout."""
    row = {"command": [str(arg) for arg in command], "cwd": str(cwd), "timeoutSeconds": timeout,
           "startedUtc": datetime.now(timezone.utc).isoformat(), "exit": None}
    try:
        with (output / (name + ".stdout.log")).open("wb") as stdout, (output / (name + ".stderr.log")).open("wb") as stderr:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            child = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, creationflags=flags)
            row["pid"] = child.pid
            try:
                row["exit"] = child.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                row["timedOut"] = isinstance(exc, subprocess.TimeoutExpired)
                row["interrupted"] = isinstance(exc, KeyboardInterrupt)
                # Only this runner's still-running, exact child PID and its tree.
                if os.name == "nt" and child.poll() is None:
                    cleanup = subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                                             capture_output=True, timeout=10, creationflags=flags)
                    row["timeoutCleanupExit"] = cleanup.returncode
                    (output / (name + ".cleanup.log")).write_bytes(cleanup.stdout + cleanup.stderr)
                if child.poll() is None:
                    child.kill()
                row["exit"] = child.wait(timeout=10)
                raise EvidenceError(name + ": timeout/interruption; stopped only the owned child; inspect logs")
        if row["exit"] != 0:
            raise EvidenceError(f"{name}: child exit {row['exit']}; inspect stdout/stderr")
        return row
    except OSError as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        raise EvidenceError(name + ": " + row["error"]) from exc
    finally:
        row["finishedUtc"] = datetime.now(timezone.utc).isoformat()
        write_json(output / (name + ".process.json"), row)


def validate_metadata(metadata, width, height, view, expected_dpr=None):
    if metadata.get("status") != "PASS" or metadata.get("offTheRecord") is not True:
        raise ValidationError("Qt render/WebChannel or off-the-record evidence did not pass")
    if metadata.get("platform") != "windows" or metadata.get("view") != view:
        raise ValidationError("Expected the Windows host and requested view")
    count = metadata.get("bridgeRequests")
    if type(count) is not int or not 6 <= count <= 100:
        raise ValidationError("Expected 6..100 synthetic WebChannel requests")
    measured = metadata.get("geometry", {})
    viewport = measured.get("viewport", {})
    if not measured.get("ready") or viewport.get("width") != width or viewport.get("height") != height:
        raise ValidationError("Rendered page not ready or viewport was resized/clipped")
    dpr = viewport.get("devicePixelRatio")
    if type(dpr) not in (int, float) or not math.isfinite(dpr) or not 0.5 <= dpr <= 4:
        raise ValidationError("Missing/invalid rendered devicePixelRatio")
    if expected_dpr is not None and not math.isclose(dpr, expected_dpr, abs_tol=0.001):
        raise ValidationError(f"Effective DPR {dpr} != requested {expected_dpr}; keep windows on the same display")
    if measured.get("fontStatus") != "loaded" or not measured.get("language") or not measured.get("timezone"):
        raise ValidationError("Font/locale/timezone evidence is incomplete")
    tokens = measured.get("tokens", {})
    if any(tokens.get(key) != value for key, value in {"--rail-width": "78px", "--chrome-height": "50px", "--iris": "#65b3a6"}.items()):
        raise ValidationError("Original visual tokens differ")
    selector = {"chat": ".composer", "settings": ".settings-shell", "today": ".local-schedule", "history": ".history-drawer"}[view]
    rect = measured.get("geometry", {}).get(selector)
    if not rect or rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0 or rect.get("display") == "none":
        raise ValidationError("Requested view has no visible positive geometry: " + selector)
    if view == "settings" and len(measured.get("categories", [])) != 6:
        raise ValidationError("Expected six original Settings groups")
    if view == "history" and measured.get("history", {}).get("opened") is not True:
        raise ValidationError("History capture must prove opened drawer, not a renamed Chat capture")
    if view == "history":
        history = measured["history"]
        intersection = history.get("visibleIntersection") or {}
        if history.get("animationsSettled") is not True or any(intersection.get(k, 0) <= 0 for k in ("width", "height")):
            raise ValidationError("History capture needs visible intersection and settled animation")
    return dpr


def validate_capture(capture, width, height, view, expected_dpr=None):
    metadata = json.loads(capture.with_suffix(".json").read_text(encoding="utf-8"))
    dpr = validate_metadata(metadata, width, height, view, expected_dpr)
    if not capture.is_file() or capture.stat().st_size == 0:
        raise ValidationError("Missing or empty PNG")
    from PIL import Image, ImageStat
    with Image.open(capture) as source:
        if source.format != "PNG":
            raise ValidationError("Capture is not a PNG")
        source.verify()
    with Image.open(capture) as source:
        source.load()
        expected = (round(width * dpr), round(height * dpr))
        if source.size != expected:
            raise ValidationError(f"PNG dimensions {source.size} != DOM/DPR dimensions {expected}")
        if "A" in source.getbands() and source.getchannel("A").getextrema() != (255, 255):
            raise ValidationError("PNG is not fully opaque")
        rgb = source.convert("RGB")
        extrema = rgb.getextrema()
        if all(low == high for low, high in extrema):
            raise ValidationError("PNG is a single-color/blank image")
        return {"view": view, "capture": capture.name, "pixelSize": list(source.size),
                "devicePixelRatio": dpr, "bytes": capture.stat().st_size,
                "sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
                "extremaRGB": extrema, "stddevRGB": ImageStat.Stat(rgb).stddev,
                "nonBlank": True, "metadata": metadata}


def read_smoke(path):
    path = path.resolve()
    if not path.is_relative_to(HERE) or path.name != "SmokeResult.json":
        raise EvidenceError("Use this task's SmokeResult.json")
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("smokeStatus") != "PASS" or result.get("sourceFingerprint") != fingerprint():
        raise EvidenceError("Missing PASS smoke or source/build changed; rerun smoke first")
    captures = [validate_capture(path.parent / (view + ".png"), WIDTH, HEIGHT, view)
                for view in ("chat", "settings")]
    for current, original in zip(captures, result["captures"], strict=True):
        if current != original:
            # JSON converts extrema tuples to arrays: compare the serialized values.
            if json.loads(json.dumps(current)) != original:
                raise EvidenceError("Smoke capture or metadata changed after receipt")
    baseline = captures[0]["metadata"]["geometry"]
    for item in captures[1:]:
        measured = item["metadata"]["geometry"]
        for key in ("viewport", "language", "timezone"):
            if measured[key] != baseline[key]:
                raise EvidenceError("Smoke views have differing DPI/locale/timezone")
    return baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if Path(sys.prefix).resolve() != HERE / ".venv":
        parser.error("Run with this task's .venv/Scripts/python.exe")
    output = (args.output or HERE / ".runtime" / ("w1-smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))).resolve()
    if not output.is_relative_to(HERE / ".runtime"):
        parser.error("Output must be a new directory under task .runtime")
    output.mkdir(parents=True, exist_ok=False)
    result = {"smokeStatus": "BLOCKED", "gateW1": "UNVERIFIED", "captures": [],
              "scope": "existing Qt host: chat + settings, 1280x720, native Windows DPR",
              "reviewer": "UNVERIFIED", "w2Started": False}
    code = 2
    guarded = False
    try:
        check_environment(os.environ)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        run_logged([sys.executable, "-B", HERE / "w1_preflight.py", output / "before.json"], output, "source-before", env=env)
        guarded = True
        run_logged([sys.executable, "-B", HERE / "w1_import_probe.py", "--output", output / "imports.json"], output, "imports", env=env)
        node_modules = ROOT / "pet-electron/node_modules"
        run_logged(["node", node_modules / "typescript/bin/tsc", "--project", "tsconfig.json", "--noEmit"], output, "typecheck", cwd=HERE / "frontend", env=env, timeout=60)
        run_logged(["node", node_modules / "vite/bin/vite.js", "build", "--config", "vite.config.mjs"], output, "build", cwd=HERE / "frontend", env=env, timeout=60)
        result["sourceFingerprint"] = fingerprint()
        for view in ("chat", "settings"):
            capture = output / (view + ".png")
            run_logged([sys.executable, "-B", HERE / "qt_preview_host.py", "--view", view,
                        "--width", str(WIDTH), "--height", str(HEIGHT), "--capture", capture], output, "qt-" + view, env=env, timeout=30)
            row = validate_capture(capture, WIDTH, HEIGHT, view)
            result["captures"].append(row)
            write_json(output / (view + ".validation.json"), row)
        if result["sourceFingerprint"] != fingerprint():
            raise EvidenceError("Source/build changed during captures")
        result["smokeStatus"] = "PASS"
        code = 0
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, (ValidationError, ValueError)):
            result["smokeStatus"], code = "FAIL", 1
        # Preserve a host's explicit render FAIL despite its nonzero process exit.
        for view in ("chat", "settings"):
            evidence = output / (view + ".json")
            if evidence.is_file():
                try:
                    if json.loads(evidence.read_text(encoding="utf-8")).get("status") == "FAIL":
                        result["smokeStatus"], code = "FAIL", 1
                except (OSError, ValueError):
                    result["smokeStatus"], code = "FAIL", 1
    finally:
        if guarded:
            try:
                run_logged([sys.executable, "-B", HERE / "w1_preflight.py", output / "after.json", "--compare", output / "before.json"], output, "source-after")
            except Exception as exc:
                result["integrityError"] = str(exc)
                result["smokeStatus"] = "FAIL"
                code = 1
        result["exit"] = code
        result["gateW1"] = "UNVERIFIED" if result["smokeStatus"] == "PASS" else result["smokeStatus"]
        write_json(output / "SmokeResult.json", result)
        print(json.dumps({"smokeStatus": result["smokeStatus"], "gateW1": result["gateW1"],
                          "exit": code, "result": str(output / "SmokeResult.json"),
                          "error": result.get("error")}, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
