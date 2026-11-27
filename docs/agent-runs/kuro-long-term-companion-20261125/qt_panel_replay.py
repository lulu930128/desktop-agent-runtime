"""Read the candidate panel through the real isolated launcher window and native WebEngine."""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
from quality_replay import ROOT

sys.path[:0] = [
    str(ROOT),
    str(ROOT / "tests"),
    str(ROOT / "Open-LLM-VTuber/src"),
    str(ROOT / "devtools/original-git-web-host-20261010"),
]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from kuro_launcher.qt_web_host import register_candidate_scheme
from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle
from build_owner_bundle import build
from web_existing_window_fixtures import ExistingWindowFixture


def replay(output, scratch):
    from PySide6.QtWidgets import QApplication
    from open_llm_vtuber.character_memory_manager import add_character_memory
    import kuro_launcher.qt_app as qt_app

    built = build(verify_only=True)
    bundle = VerifiedOwnerBundle.load(
        built["directory"],
        OwnerBundlePin(
            built["fingerprint"],
            built["manifestSha256"],
            built["publicKey"],
            built["signature"],
        ),
    )
    from PySide6.QtCore import Qt

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL)
    register_candidate_scheme()
    app = QApplication([])
    app.setOrganizationName("Kuro synthetic memory replay")
    app.setQuitOnLastWindowClosed(False)
    fixture = ExistingWindowFixture(scratch / "state")
    fixture.start()
    window = None
    stage = "startup"

    def wait(test):
        until = time.monotonic() + 25
        while time.monotonic() < until:
            app.processEvents()
            if test():
                return
            time.sleep(0.01)
        raise TimeoutError("Qt panel condition " + str(test))

    try:
        from kuro_launcher.memory_support import ensure_character_memory_root

        ensure_character_memory_root(fixture.cfg.open_llm_dir)
        for i in range(95):
            add_character_memory("actor", f"SYNTHETIC ceramic specimen {i:04d}")
        with patch.object(qt_app, "QtLauncherController", fixture.make_controller):
            window = qt_app.KuroQtLauncherWindow(fixture.cfg, web_bundle=bundle)
        window._connect_chat()
        stage = "handshake"
        wait(lambda: window.chat_client.history_ready)
        assert window.chat_client.conf_uid == "actor"
        page = window.work_web_candidate.page()

        def js(expr):
            out = []
            page.runJavaScript(expr, out.append)
            wait(lambda: bool(out))
            return out[0]

        stage = "document"
        wait(lambda: js("Boolean(document.querySelector('[data-mode=settings]'))"))
        js("document.querySelector('[data-mode=settings]').click()")
        selector = "Array.from(document.querySelectorAll('.settings-nav-item')).find(x=>x.innerText.includes('對話與記憶'))"
        stage = "settings navigation"
        wait(lambda: js("Boolean(" + selector + ")"))
        js(selector + ".click()")
        stage = "memory controls"
        wait(lambda: js("document.body.innerText.includes('還原至新目錄')"))
        wait(
            lambda: js(
                "document.body.innerText.includes('SYNTHETIC ceramic specimen 0094')"
            )
        )
        initial = True
        js(
            "Array.from(document.querySelectorAll('button')).find(b=>b.innerText==='修訂').click()"
        )
        assert js(
            "Boolean(document.querySelector('textarea[aria-label=修訂記憶內容]'))"
        )
        js(
            "Array.from(document.querySelectorAll('.memory-row button')).find(b=>b.innerText==='取消').click()"
        )
        js(
            "const s=document.querySelector('input[type=search]');s.value='0094';s.dispatchEvent(new Event('input'));"
        )
        filtered = js(
            "document.body.innerText.includes('0094') && !document.body.innerText.includes('0093')"
        )
        controls = js(
            "['儲存記憶模式','重查目前對話索引','匯出所有角色','還原至新目錄'].filter(t=>document.body.innerText.includes(t)).join('|')"
        )
        assert initial and filtered and len(controls.split("|")) == 4, (
            initial,
            filtered,
            controls,
        )
        output.write_text(
            json.dumps(
                dict(
                    fingerprint=built["fingerprint"],
                    widget=type(window).__name__,
                    renderer=type(window.work_web_candidate).__name__,
                    platform=app.platformName(),
                    records=95,
                    search_readback=filtered,
                    revision_editor=True,
                    controls=controls.split("|"),
                    production=False,
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        print("failed stage", stage, flush=True)
        if stage in {"document", "settings navigation", "memory controls"}:
            print("fixture DOM", js("document.body.innerText.slice(-1200)"), flush=True)
        raise
    finally:
        if window:
            window.cleanup()
        fixture.close()


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    if len(sys.argv) > 2:
        replay(output, Path(sys.argv[2]))
    else:
        import subprocess

        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            subprocess.run(
                [sys.executable, "-B", str(Path(__file__).resolve()), str(output), tmp],
                check=True,
                cwd=ROOT,
            )
