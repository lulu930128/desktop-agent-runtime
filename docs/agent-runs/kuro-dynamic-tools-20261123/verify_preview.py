"""Exercise the portable Tools preview in isolated Qt WebEngine. No desktop profile."""
import json
import os
from pathlib import Path

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView

here = Path(__file__).resolve().parent
app = QApplication([])
view = QWebEngineView()
view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
view.resize(1024, 800)
result = {}
def inspect():
    script = """(() => {
      const groups = [...document.querySelectorAll('[data-tool-service]')];
      const jp = groups.find(n => n.dataset.toolService === 'japanese-study');
      if (!jp) return '';
      const history = document.querySelector('[data-tool-groups] > details');
      history.open = true;
      const events = history.querySelectorAll('pre').length;
      history.open = false;
      jp.open = true;
      return JSON.stringify({groups:groups.map(g=>g.querySelector('summary').textContent),
        japaneseRows:jp.querySelectorAll('[data-tool-toggle]').length, events,
        togglesDisabled:[...document.querySelectorAll('[data-tool-toggle]')].every(t=>t.disabled),
        workspace:groups.find(n=>n.dataset.toolService==='project-workspace')?.querySelector('summary')?.textContent,
        workspaceScope:groups.find(n=>n.dataset.toolService==='project-workspace')?.querySelector(':scope > p')?.textContent,
        overflow:document.documentElement.scrollWidth > innerWidth, agentReason:history.textContent.includes('actual_success')});
    })()"""
    def done(raw):
        if not raw:
            QTimer.singleShot(100, inspect)
            return
        result.update(json.loads(raw))
        QTimer.singleShot(250, app.quit)
    view.page().runJavaScript(script, done)

view.loadFinished.connect(lambda ok: inspect() if ok else app.quit())
view.setUrl(QUrl.fromLocalFile(str(here / "preview.html")))
view.show()
QTimer.singleShot(12000, app.quit)
app.exec()
assert len(result.get("groups", [])) == 5, result
assert result["japaneseRows"] == 37 and result["events"] > 20, result
assert "發現" in result["workspace"] and result["agentReason"], result
assert "not_configured" in result["workspaceScope"] or "來源已授權寫入" in result["workspaceScope"], result
assert result["togglesDisabled"] and not result["overflow"], result
capture = view.grab().toImage()
assert len({capture.pixelColor(x, y).name() for x in range(0, capture.width(), 5)
            for y in range(0, capture.height(), 5)}) > 16, "Qt paint incomplete"
assert capture.save(str(here / "tools-preview.png"))
(here / "preview-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("Qt WebEngine preview verified")
