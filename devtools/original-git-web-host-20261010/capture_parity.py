"""Optional Windows relay: synthetic Chromium baseline vs isolated Qt WebEngine.

Requires the task's isolated venv only. Never starts Electron or the launcher.
Failure stops the comparison; no security/GPU fallback is attempted.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import threading

HERE = Path(__file__).resolve().parent
DIST = HERE / "frontend/dist"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=["chrome", "msedge"], default="chrome")
    parser.add_argument("--scale", type=float, choices=[1, 1.25, 2], default=1)
    args = parser.parse_args()
    if Path(sys.prefix).resolve() != (HERE / ".venv").resolve():
        parser.error("Run only with this task's isolated .venv/Scripts/python.exe")
    # Prove imports before starting any browser. The installed browser is reused
    # as an executable only; playwright creates its own disposable profile.
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from playwright.sync_api import sync_playwright
    from PIL import Image, ImageChops, ImageStat

    if not (DIST / "work-panel.html").is_file():
        raise RuntimeError("Build isolated frontend first")
    output = HERE / f"captures-{args.scale:g}"
    output.mkdir(exist_ok=False)  # preserve earlier evidence on rerun
    handler = partial(SimpleHTTPRequestHandler, directory=str(DIST))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    results = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=args.channel, headless=True, chromium_sandbox=True)
            try:
                for width, height in [(1280, 720), (1380, 860)]:
                    for mode in ["chat", "settings", "today"]:
                        stem = f"{mode}-{width}x{height}"
                        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=args.scale, locale="zh-TW", timezone_id="Asia/Taipei")
                        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort())
                        page = context.new_page()
                        page.goto(origin + "/work-panel.html?view=" + mode)
                        page.wait_for_selector(".work-panel")
                        page.wait_for_function("document.body.innerText.includes('SYNTHETIC')")
                        page.evaluate("document.fonts.ready")
                        page.wait_for_timeout(1500)
                        baseline = json.loads(page.evaluate((HERE / "geometry.js").read_text(encoding="utf-8")))
                        page.screenshot(path=str(output / (stem + "-baseline.png")))
                        (output / (stem + "-baseline.json")).write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
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
                        env.update(QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=str(args.scale), PYTHONIOENCODING="utf-8")
                        command = [sys.executable, "-B", str(HERE / "qt_preview_host.py"), "--view", mode,
                                   "--width", str(width), "--height", str(height), "--capture", str(output / (stem + "-qt.png"))]
                        subprocess.run(command, check=True, timeout=30, env=env)
                        qt = json.loads((output / (stem + "-qt.json")).read_text(encoding="utf-8"))
                        if qt["status"] != "PASS":
                            raise RuntimeError("Qt import/load/render/bridge did not pass")
                        a = Image.open(output / (stem + "-baseline.png")).convert("RGB")
                        b = Image.open(output / (stem + "-qt.png")).convert("RGB")
                        if a.size != b.size:
                            raise RuntimeError(f"Capture dimensions differ: {a.size} vs {b.size}")
                        diff = ImageChops.difference(a, b)
                        diff.save(output / (stem + "-diff.png"))
                        changed = sum(pixel != (0, 0, 0) for pixel in diff.getdata())
                        row = {"view": mode, "viewport": [width, height], "scale": args.scale,
                               "pixelSize": list(a.size), "crop": "entire Web viewport; excludes native window frame",
                               "geometryEqual": baseline["geometry"] == qt["geometry"]["geometry"],
                               "tokensEqual": baseline["tokens"] == qt["geometry"]["tokens"],
                               "meanAbsoluteErrorRGB": ImageStat.Stat(diff).mean,
                               "rmsRGB": ImageStat.Stat(diff).rms,
                               "changedPixelFraction": changed / (a.width * a.height),
                               "hostPlatform": qt["platform"], "windowsDesktop": "UNVERIFIED",
                               "humanScreenshotReview": "UNVERIFIED", "release": "NOT ACCEPTED"}
                        results.append(row)
                        (output / "Comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                        if not row["geometryEqual"] or not row["tokensEqual"]:
                            raise RuntimeError("Geometry/token mismatch: stop and review evidence")
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
