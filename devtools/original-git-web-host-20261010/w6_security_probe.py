"""Fail-closed native security evidence for the disposable W6 owner only.

No security setting, resource, owner transport or browser return is replaced.
Receipts contain booleans/counters, never storage values or arbitrary URLs.
"""
from __future__ import annotations

import json

ERROR_CAPTURE_SCRIPT = """window.w6Errors=[];
addEventListener('error',e=>{
  if(e instanceof ErrorEvent)w6Errors.push({kind:'javascript-error',line:e.lineno,column:e.colno});
});
"""


def capture_javascript_errors(evidence, stage, value):
    """Keep only bounded location metadata; absent evidence cannot mean no errors."""
    valid = isinstance(value, list)
    if valid:
        for row in value:
            if (not isinstance(row, dict) or row.get("kind") != "javascript-error"
                    or any(type(row.get(k)) is not int or not 0 <= row[k] <= 2**31-1 for k in ("line", "column"))):
                valid = False
                continue
            evidence["javascriptErrors"].append({"kind": "javascript-error", "line": row["line"], "column": row["column"]})
    samples = evidence["javascriptErrorSamples"]
    # Once malformed, a later empty sample cannot erase that missing evidence.
    samples[stage] = valid and samples.get(stage, True)
    evidence["javascriptErrorsComplete"] = all(samples.get(k) is True
        for k in ("initial", "beforeReload", "nativeFirst", "nativeReload"))


STORAGE_PROBE = r"""(key => {
  const read = () => {
    try { return {settled:true, absent:localStorage.getItem(key) === null, threw:false}; }
    catch (_) { return {settled:true, absent:true, threw:true}; }
  };
  const r = {before:read(), writeReturned:false, writeThrew:false};
  try { localStorage.setItem(key, 'SYNTHETIC'); r.writeReturned=true; }
  catch (_) { r.writeThrew=true; }
  r.after=read(); r.settled=true;
  return r;
})"""


def _absent(value):
    return isinstance(value, dict) and value.get("settled") is True and value.get("absent") is True


def _no_storage(value):
    return (isinstance(value, dict) and value.get("settled") is True
            and _absent(value.get("before")) and _absent(value.get("after"))
            and (value.get("writeReturned") is True or value.get("writeThrew") is True))


def evaluate_security(evidence):
    """Unknown/missing/timeout is never denial; evaluate each axis independently."""
    network = evidence.get("network", {})
    asset = evidence.get("asset", {})
    popup = evidence.get("popup", {})
    storage = evidence.get("storage", {})
    before, after = evidence.get("probeHitsBefore"), evidence.get("probeHitsAfter")
    no_hit = type(before) is int and before > 0 and type(after) is int and after == before
    attempts = popup.get("attempts", [])
    return {
        "network": network.get("settled") is True and network.get("rejected") is True and no_hit,
        "asset": (asset.get("settled") is True and asset.get("rejected") is True
                  and asset.get("elementSettled") is True and asset.get("elementDenied") is True
                  and asset.get("blockedByHost", 0) > 0 and asset.get("unexpectedReplies") == 0),
        "popup": (popup.get("settled") is True and len(attempts) == 3
                  and all(a.get("settled") is True and a.get("usableAfterDrain") is False for a in attempts)
                  and popup.get("javascriptOpenDisabled") is True and popup.get("newObjects") == 0
                  and popup.get("creationEvents") == 0 and popup.get("samePage") is True and no_hit),
        "storage": (storage.get("settled") is True and _no_storage(storage.get("presentation"))
                    and storage.get("otherStoresDenied") is True
                    and storage.get("localStorageDisabled") is True and storage.get("offTheRecord") is True
                    and _absent(storage.get("presentationAfterReload"))
                    and _no_storage(storage.get("nativeFirst")) and _no_storage(storage.get("nativeReload"))),
    }


def run_security_probe(*, app, view, fixture, js, pump, until, namespace, record):
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtGui import QWindow
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    import shiboken6

    page = view.page()
    key = "w6.security." + namespace
    probe_url = f"http://127.0.0.1:{fixture.probe_port}/w6-probe"
    evidence = {"contract": "kuro.w6.security.v1", "synthetic": True,
                "probeHitsBefore": fixture.probe_hits, "network": {}, "asset": {}, "popup": {}, "storage": {},
                "javascriptErrors": [], "javascriptErrorSamples": {}, "javascriptErrorsComplete": False}
    def save():
        evidence["probeHitsAfter"] = fixture.probe_hits
        evidence["axes"] = evaluate_security(evidence)
        record(evidence)
    def read(expression):
        return json.loads(js("JSON.stringify(" + expression + ")"))
    def objects():
        return {int(shiboken6.getCppPointer(obj)[0]) for obj in shiboken6.getAllValidWrappers()
                if isinstance(obj, (QWebEnginePage, QWebEngineView, QWindow))}

    baseline = objects()
    creation_events = set()
    class ObserveCreation(QObject):
        def eventFilter(self, watched, event):
            # Observe transient windows as well as the final object inventory.
            if event.type() in (QEvent.Type.Show, QEvent.Type.ChildAdded, QEvent.Type.ChildPolished):
                target = event.child() if event.type() != QEvent.Type.Show else watched
                if isinstance(target, (QWebEnginePage, QWebEngineView, QWindow)):
                    pointer = int(shiboken6.getCppPointer(target)[0])
                    if pointer not in baseline: creation_events.add(pointer)
            return False
    observer = ObserveCreation()
    app.installEventFilter(observer)
    counts = view.security_snapshot()
    save()
    try:
        capture_javascript_errors(evidence, "initial", read("window.w6Errors"))
        # Each operation catches independently so one unexpected API result cannot
        # prevent the other axes from settling and being written to the receipt.
        js("window.__w6security={network:{settled:false},asset:{settled:false},popup:{attempts:[]}}; true")
        for axis, url in (("network", probe_url), ("asset", "kuro-work://app/denied")):
            js(f"try {{ fetch({json.dumps(url)}).then(() => Object.assign(__w6security.{axis},{{settled:true,rejected:false}}),"
               f"() => Object.assign(__w6security.{axis},{{settled:true,rejected:true}})); }}"
               f"catch (_) {{ Object.assign(__w6security.{axis},{{settled:true,rejected:true,syncThrow:true}}); }}; true")
        # connect-src blocks fetch before the handler. Also exercise a same-origin
        # script subresource through the actual resource allowlist, with CSP intact.
        js("{const s=document.createElement('script');s.src='kuro-work://app/denied.js';"
           "s.onload=()=>Object.assign(__w6security.asset,{elementSettled:true,elementDenied:false});"
           "s.onerror=()=>Object.assign(__w6security.asset,{elementSettled:true,elementDenied:true});"
           "document.head.appendChild(s)};true")
        for url in ("kuro-work://denied/popup", "about:blank", probe_url):
            js("{const a={settled:false};__w6security.popup.attempts.push(a);"
               "try { const p=window.open(" + json.dumps(url) + ");a.returnNull=p===null;a.returnUndefined=p===undefined;"
               "a.handle=p;a.threw=false; } catch (_) {a.threw=true;} a.settled=true;} true")
        presentation = read(STORAGE_PROBE + "(" + json.dumps(key) + ")")
        other_denied = js("['sessionStorage','indexedDB','caches'].every(k=>{try{void window[k];return false}catch(_){return true}})")
        settled = until(lambda: js("__w6security.network.settled&&__w6security.asset.settled&&__w6security.asset.elementSettled"), 5)
        pump(.5)  # bounded delivery drain; no timeout/retry or security override
        js("for(const a of __w6security.popup.attempts){a.usableAfterDrain=false;"
           "try{if(a.handle)a.usableAfterDrain=a.handle.closed!==true}catch(_){a.usableAfterDrain=true}delete a.handle} true")
        observed = read("__w6security")
        final_counts = view.security_snapshot()
        evidence["network"] = observed["network"]
        evidence["asset"] = dict(observed["asset"],
            blockedByHost=final_counts.get("assetBlocked", 0)-counts.get("assetBlocked", 0)
                          + final_counts.get("handlerDenied", 0)-counts.get("handlerDenied", 0),
            unexpectedReplies=final_counts.get("assetReplied", 0)-counts.get("assetReplied", 0))
        evidence["popup"] = dict(observed["popup"], settled=True,
            javascriptOpenDisabled=not page.settings().testAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows),
            newObjects=len(objects()-baseline), creationEvents=len(creation_events),
            samePage=page.url().toString() == "kuro-work://app/work-panel.html",
            deniedCallbacks=final_counts.get("popupDenied", 0)-counts.get("popupDenied", 0),
            discardedRequests=final_counts.get("popupRequestDiscarded", 0)-counts.get("popupRequestDiscarded", 0))
        evidence["storage"] = dict(presentation=presentation, otherStoresDenied=other_denied,
            localStorageDisabled=not page.settings().testAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled),
            offTheRecord=page.profile().isOffTheRecord(), settled=False)
        evidence["asyncSettled"] = settled
        evidence["hostCountersBefore"] = counts
        evidence["hostCountersAfter"] = final_counts
        capture_javascript_errors(evidence, "beforeReload", read("window.w6Errors"))
        evidence["legacyPredicates"] = dict(network=observed["network"].get("rejected"),
            asset=observed["asset"].get("rejected"), popup=observed["popup"]["attempts"][0].get("returnNull"),
            storage=presentation.get("writeThrew"))
        save()
    except Exception as exc:
        evidence["probeErrorType"] = type(exc).__name__
        save()
    finally:
        app.removeEventFilter(observer)

    # Run before owner-bootstrap replaces window.localStorage. Only the synthetic
    # marker is touched; the second reload tests same-profile persistence. Parent
    # and restart use the same marker and each independently requires absence.
    script = QWebEngineScript()
    script.setName("w6-synthetic-storage-evidence")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    script.setSourceCode(ERROR_CAPTURE_SCRIPT +
        "window.__w6NativeStorage=" + STORAGE_PROBE + "(" + json.dumps(key) + ");")
    page.scripts().insert(script)
    try:
        for field in ("nativeFirst", "nativeReload"):
            loads = []
            connection = page.loadFinished.connect(loads.append)
            try:
                page.triggerAction(QWebEnginePage.WebAction.Reload)
                if not until(lambda: bool(loads), 10) or loads[-1] is not True:
                    raise RuntimeError("Security storage reload unavailable")
                if not until(lambda: js("!!window.kuroWorkPanel&&!!document.querySelector('.rail')"), 10):
                    raise RuntimeError("Security storage bootstrap unavailable")
                evidence["storage"][field] = read("window.__w6NativeStorage")
                capture_javascript_errors(evidence, field, read("window.w6Errors"))
                if field == "nativeFirst":
                    evidence["storage"]["presentationAfterReload"] = read(
                        "(()=>{try{return {settled:true,absent:localStorage.getItem(" + json.dumps(key)
                        + ")===null,threw:false}}catch(_){return {settled:true,absent:true,threw:true}}})()")
                save()
            finally:
                QObject.disconnect(connection)
        evidence["storage"]["settled"] = True
    except Exception as exc:
        evidence["storage"]["errorType"] = type(exc).__name__
    finally:
        page.scripts().remove(script)
        save()
    return evidence
