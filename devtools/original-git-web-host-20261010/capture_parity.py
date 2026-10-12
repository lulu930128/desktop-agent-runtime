"""Optional Windows relay: synthetic Chromium baseline vs isolated Qt WebEngine.

Requires the task's isolated venv only. Never starts Electron or the launcher.
Fatal validation stops capture. Optional geometry-drift collection retains FAIL.
No security/GPU fallback is attempted.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone

from w1_smoke import EvidenceError, ValidationError, check_environment, fingerprint, read_smoke, run_logged, validate_capture, write_json
from w1_geometry_diagnostics import fractional_diagnosis, measurement_stable

HERE = Path(__file__).resolve().parent
DIST = HERE / "frontend/dist"


def stable_browser_geometry(page, mode, evidence_path):
    previous = None
    attempts = []
    script = (HERE / "geometry.js").read_text(encoding="utf-8")
    for _ in range(8):
        current = json.loads(page.evaluate(script))
        stable = measurement_stable(previous, current, mode)
        attempts.append(current)
        write_json(evidence_path, {"stable": stable, "measurements": attempts})
        if stable:
            return current
        previous = current
        page.wait_for_timeout(200)
    raise ValidationError("Browser geometry/History visibility/animation did not stabilize")


def verify_context(baseline, qt, expected_tokens=None):
    for key in ("viewport", "language", "timezone", "fontStatus"):
        if baseline.get(key) is None or baseline.get(key) != qt.get(key):
            raise ValidationError(f"Unmatched {key}: browser={baseline.get(key)} Qt={qt.get(key)}")
    if expected_tokens is not None:
        for label, measured in (("browser", baseline), ("Qt", qt)):
            tokens = measured.get("tokens", {})
            if (not expected_tokens or any(not value for value in expected_tokens.values())
                    or tokens != expected_tokens):
                raise ValidationError(f"Missing/changed canonical tokens: {label}")


def record_comparison(output, receipt, row, collect_geometry_drift=False):
    """Persist each comparison before deciding whether capture may continue."""
    receipt["results"].append(row)
    write_json(output / "Comparison.json", receipt["results"])
    geometry_equal = row["geometryEqual"] and row.get("deepGeometryEqual", True)
    if not row["tokensEqual"] or not geometry_equal:
        receipt.setdefault("comparisonFailures", []).append({
            "view": row["view"], "viewport": row["viewport"],
            "geometryEqual": row["geometryEqual"], "deepGeometryEqual": row.get("deepGeometryEqual"), "tokensEqual": row["tokensEqual"]})
        receipt.update(captureStatus="FAIL", gateW1="FAIL", exit=1)
    write_json(output / "ParityResult.json", receipt)
    if not row["tokensEqual"]:
        raise ValidationError("Token mismatch: stop and review evidence")
    if not geometry_equal and not collect_geometry_drift:
        raise ValidationError("Geometry mismatch: stop and review evidence")


def finish_capture(receipt, error=None):
    # A later successful capture or infrastructure error must never erase drift.
    failed = bool(receipt.get("comparisonFailures")) or isinstance(error, ValidationError)
    status = "FAIL" if failed else ("BLOCKED" if error is not None else "PASS")
    receipt.update(captureStatus=status, gateW1="UNVERIFIED" if status == "PASS" else status,
                   exit=0 if status == "PASS" else 1)
    if error is not None:
        receipt["error"] = f"{type(error).__name__}: {error}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=["chrome", "msedge"], default="chrome")
    parser.add_argument("--output", type=Path, help="New directory under task .runtime (relay provenance)")
    parser.add_argument("--scale", type=float, choices=[1, 1.25, 2], default=1)
    parser.add_argument("--collect-geometry-drift", action="store_true",
                        help="Collect remaining viewports after geometry drift; gate remains FAIL, exit 1")
    parser.add_argument("--smoke-result", type=Path, required=True,
                        help="Successful current-source w1_smoke.py SmokeResult.json")
    args = parser.parse_args()
    if Path(sys.prefix).resolve() != (HERE / ".venv").resolve():
        parser.error("Run only with this task's isolated .venv/Scripts/python.exe")
    check_environment(os.environ)
    smoke = read_smoke(args.smoke_result)
    # Prove imports before starting any browser. The installed browser is reused
    # as an executable only; playwright creates its own disposable profile.
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from playwright.sync_api import sync_playwright
    from PIL import Image, ImageChops, ImageStat

    if not (DIST / "work-panel.html").is_file():
        raise RuntimeError("Build isolated frontend first")
    output = (args.output or HERE / ".runtime" / (f"parity-{args.channel}-{args.scale:g}-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))).resolve()
    if not output.is_relative_to(HERE / ".runtime"):
        parser.error("Output must be a new directory under task .runtime")
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"captureStatus": "BLOCKED", "gateW1": "UNVERIFIED", "exit": 1, "channel": args.channel,
               "requestedDpr": args.scale, "smokeResult": str(args.smoke_result.resolve()),
               "sourceFingerprint": fingerprint(), "reviewer": "UNVERIFIED",
               "collectGeometryDrift": args.collect_geometry_drift,
               "pending": ["History screenshot pairs require completed matrix and visual review", "Qt interaction and native keyboard/IME",
                           "resource/navigation/download runtime rejection probes", "independent visual review"],
               "results": []}
    write_json(output / "ParityResult.json", receipt)
    handler = partial(SimpleHTTPRequestHandler, directory=str(DIST))
    server = None
    thread = None
    guarded = False
    try:
        run_logged([sys.executable, "-B", HERE / "w1_preflight.py", output / "before.json"], output, "source-before")
        guarded = True
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=args.channel, headless=False, chromium_sandbox=True, timeout=20000)
            try:
                receipt["browserVersion"] = browser.version
                for width, height in [(1280, 720), (1380, 860)]:
                    for mode in ["chat", "settings", "today", "history"]:
                        if receipt["sourceFingerprint"] != fingerprint():
                            raise ValidationError("Source/build changed during comparison")
                        stem = f"{mode}-{width}x{height}"
                        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=args.scale,
                                                      locale=smoke["language"], timezone_id=smoke["timezone"],
                                                      accept_downloads=False, service_workers="block")
                        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort())
                        page = context.new_page()
                        page.set_default_timeout(15000)
                        page.goto(origin + "/work-panel.html?view=" + ("chat" if mode == "history" else mode))
                        page.wait_for_selector(".work-panel")
                        page.wait_for_function("document.body.innerText.includes('SYNTHETIC')")
                        page.evaluate("document.fonts.ready")
                        page.wait_for_timeout(1500)
                        if mode == "history":
                            page.locator("[data-history-toggle]").click()
                            page.wait_for_selector(".stage.has-history")
                            page.wait_for_timeout(400)
                        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                        baseline = stable_browser_geometry(page, mode, output / (stem + "-baseline-stability.json"))
                        page.screenshot(path=str(output / (stem + "-baseline.png")))
                        (output / (stem + "-baseline.json")).write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
                        if mode == "history" and baseline.get("history", {}).get("opened") is not True:
                            raise ValidationError("Edge History drawer is not opened")
                        write_json(output / (stem + "-baseline-typography.json"),
                                   json.loads(page.evaluate((HERE / "typography.js").read_text(encoding="utf-8"))))
                        # Interaction evidence is separate from untouched screenshot state.
                        interactions = {"host": "browser baseline", "realIME": "UNVERIFIED"}
                        if mode == "chat":
                            page.locator("[data-history-toggle]").click()
                            page.wait_for_selector(".stage.has-history")
                            page.locator(".history-search").fill("SYNTHETIC")
                            page.locator(".history-drawer [aria-label='關閉對話紀錄']").click()
                            page.wait_for_selector(".stage:not(.has-history)")
                            composer = page.locator("[data-composer-input]")
                            composer.fill("SYNTHETIC draft")
                            composer.press("Shift+Enter")
                            assert "SYNTHETIC draft" in composer.input_value()
                            interactions.update(historyOpenClose=True, historySearch=True, composerDraft=True)
                        elif mode == "settings":
                            assert page.locator(".settings-nav-item").count() == 6
                            for index in range(6):
                                page.locator(".settings-nav-item").nth(index).click()
                                assert page.locator(".settings-content").inner_text()
                            interactions["sixCategories"] = True
                        elif mode == "today":
                            assert page.locator(".local-schedule").count() == 1
                            interactions["schedulePresent"] = True
                        page.keyboard.press("Tab")
                        interactions["focusTag"] = page.evaluate("document.activeElement.tagName")
                        (output / (stem + "-interactions.json")).write_text(json.dumps(interactions, indent=2), encoding="utf-8")
                        context.close()
                        env = os.environ.copy()
                        # QT_SCALE_FACTOR multiplies native Windows DPR, rather
                        # than replacing it. Verify the effective DOM DPR below.
                        env.update(QT_SCALE_FACTOR=str(args.scale / smoke["viewport"]["devicePixelRatio"]),
                                   QT_SCALE_FACTOR_ROUNDING_POLICY="PassThrough", PYTHONIOENCODING="utf-8")
                        command = [sys.executable, "-B", str(HERE / "qt_preview_host.py"), "--view", mode,
                                   "--width", str(width), "--height", str(height), "--capture", str(output / (stem + "-qt.png"))]
                        host_error = None
                        try:
                            run_logged(command, output, stem + "-qt-process", env=env, timeout=30)
                        except EvidenceError as exc:
                            host_error = exc
                            if not (output / (stem + "-qt.json")).is_file():
                                raise
                        qt = json.loads((output / (stem + "-qt.json")).read_text(encoding="utf-8"))
                        write_json(output / (stem + "-diagnostics.json"),
                                   {"fractional": fractional_diagnosis(baseline, qt.get("geometry", {})),
                                    "viewport": qt.get("viewportDiagnosis"), "hostError": str(host_error) if host_error else None})
                        if host_error:
                            if qt.get("status") == "FAIL":
                                raise ValidationError("Qt host FAIL; raw viewport/timeline/PNG retained") from host_error
                            raise host_error
                        validate_capture(output / (stem + "-qt.png"), width, height, mode, args.scale)
                        verify_context(baseline, qt["geometry"], smoke["tokens"])
                        if mode == "today":
                            for measured in (baseline, qt["geometry"]):
                                coverage = measured.get("deepCoverage", {})
                                if (not coverage.get("today") or not coverage.get("required")
                                        or any(count < 1 for count in coverage["required"].values())):
                                    raise RuntimeError("Today deep geometry missing required DOM nodes; W1 FAIL")
                        a = Image.open(output / (stem + "-baseline.png")).convert("RGB")
                        b = Image.open(output / (stem + "-qt.png")).convert("RGB")
                        if a.size != b.size:
                            raise ValidationError(f"Capture dimensions differ: {a.size} vs {b.size}")
                        diff = ImageChops.difference(a, b)
                        diff.save(output / (stem + "-diff.png"))
                        changed = sum(pixel != (0, 0, 0) for pixel in diff.getdata())
                        row = {"view": mode, "viewport": [width, height], "scale": args.scale,
                               "pixelSize": list(a.size), "crop": "entire Web viewport; excludes native window frame",
                               "geometryEqual": baseline["geometry"] == qt["geometry"]["geometry"],
                               "deepGeometryEqual": baseline["deepGeometry"] == qt["geometry"]["deepGeometry"],
                               "tokensEqual": baseline["tokens"] == qt["geometry"]["tokens"],
                               "meanAbsoluteErrorRGB": ImageStat.Stat(diff).mean,
                               "rmsRGB": ImageStat.Stat(diff).rms,
                               "changedPixelFraction": changed / (a.width * a.height),
                               "hostPlatform": qt["platform"], "windowsDesktop": "automated capture; human review pending",
                               "humanScreenshotReview": "UNVERIFIED", "release": "NOT ACCEPTED"}
                        record_comparison(output, receipt, row, args.collect_geometry_drift)
                if receipt["sourceFingerprint"] != fingerprint():
                    raise ValidationError("Source/build changed during comparison")
                finish_capture(receipt)
            finally:
                browser.close()
    except Exception as exc:
        finish_capture(receipt, exc)
        raise
    finally:
        if server is not None:
            if thread is not None and thread.is_alive():
                server.shutdown()
                thread.join(timeout=2)
            server.server_close()
        if guarded:
            try:
                run_logged([sys.executable, "-B", HERE / "w1_preflight.py", output / "after.json",
                            "--compare", output / "before.json"], output, "source-after")
            except Exception as exc:
                receipt.update(captureStatus="FAIL", exit=1, integrityError=str(exc))
        receipt["gateW1"] = "UNVERIFIED" if receipt["captureStatus"] == "PASS" else receipt["captureStatus"]
        write_json(output / "ParityResult.json", receipt)
        print(json.dumps({"result": str(output / "ParityResult.json"), "captureStatus": receipt["captureStatus"],
                          "gateW1": receipt["gateW1"], "pending": receipt["pending"]}, ensure_ascii=True))
    return receipt["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
