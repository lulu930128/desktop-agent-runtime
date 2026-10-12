"""Negative security-receipt tests; synthetic evidence is never native acceptance."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "devtools/original-git-web-host-20261010"
spec = importlib.util.spec_from_file_location("w6_security", TASK / "w6_security_probe.py")
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


def clean_evidence():
    absent = dict(settled=True, absent=True, threw=True)
    store = dict(settled=True, before=absent, after=absent, writeReturned=False, writeThrew=True)
    return dict(probeHitsBefore=1, probeHitsAfter=1,
        network=dict(settled=True, rejected=True),
        asset=dict(settled=True, rejected=True, elementSettled=True, elementDenied=True, blockedByHost=1, unexpectedReplies=0),
        popup=dict(settled=True, attempts=[dict(settled=True, usableAfterDrain=False, returnNull=False) for _ in range(3)],
                   javascriptOpenDisabled=True, newObjects=0, creationEvents=0, samePage=True),
        storage=dict(settled=True, presentation=store, otherStoresDenied=True, localStorageDisabled=True,
                     offTheRecord=True, presentationAfterReload=absent, nativeFirst=store, nativeReload=store))


class SecurityEvidenceTests(unittest.TestCase):
    def test_js_error_evidence_is_initialized_and_requires_every_reload_sample(self):
        evidence = {"javascriptErrors": [], "javascriptErrorSamples": {}}
        for stage in ("initial", "beforeReload", "nativeFirst", "nativeReload"):
            security.capture_javascript_errors(evidence, stage, [])
            self.assertEqual(evidence["javascriptErrors"], [])
            self.assertEqual(evidence["javascriptErrorsComplete"], stage == "nativeReload")
        security.capture_javascript_errors(evidence, "nativeReload", None)
        self.assertFalse(evidence["javascriptErrorsComplete"])

    def test_post_reload_errors_are_retained_without_raw_message_or_source(self):
        evidence = {"javascriptErrors": [], "javascriptErrorSamples": {}}
        for stage in ("initial", "beforeReload", "nativeFirst", "nativeReload"):
            rows = [{"kind": "javascript-error", "line": 12, "column": 3,
                     "message": "SENSITIVE MESSAGE", "source": "SENSITIVE URL", "stack": "SENSITIVE STACK"}] if stage == "nativeReload" else []
            security.capture_javascript_errors(evidence, stage, rows)
        self.assertTrue(evidence["javascriptErrorsComplete"])
        self.assertEqual(evidence["javascriptErrors"], [{"kind": "javascript-error", "line": 12, "column": 3}])
        self.assertNotIn("SENSITIVE", json.dumps(evidence))

    def test_malformed_error_evidence_is_not_empty_success(self):
        for malformed in (None, {}, "SENSITIVE", ["SENSITIVE"], [{"kind": "javascript-error", "line": "SENSITIVE", "column": 0}]):
            evidence = {"javascriptErrors": [], "javascriptErrorSamples": {}}
            for stage in ("initial", "beforeReload", "nativeFirst"):
                security.capture_javascript_errors(evidence, stage, [])
            security.capture_javascript_errors(evidence, "nativeReload", malformed)
            self.assertFalse(evidence["javascriptErrorsComplete"])
            self.assertNotIn("SENSITIVE", json.dumps(evidence))

    def test_document_creation_listener_captures_errors_on_each_new_document(self):
        code = r"""
const vm=require('vm'),assert=require('assert');
const script=process.argv[1];
for (const inject of [false,true]) {
  const listeners=[];
  class ErrorEvent { constructor(){this.lineno=7;this.colno=9;this.message='SENSITIVE';this.filename='SENSITIVE';this.error=Error('SENSITIVE')} }
  const context={ErrorEvent,addEventListener:(name,listener)=>{assert.equal(name,'error');listeners.push(listener)}};
  context.window=context;vm.createContext(context);vm.runInContext(script,context);
  if(inject)listeners[0](new ErrorEvent());
  // A resource error is not a JS exception. Expected denied assets stay separate.
  listeners[0]({message:'SENSITIVE RESOURCE'});
  const errors=JSON.parse(JSON.stringify(context.w6Errors));
  assert.deepStrictEqual(errors,inject?[{kind:'javascript-error',line:7,column:9}]:[]);
  assert.ok(!JSON.stringify(errors).includes('SENSITIVE'));
}
"""
        process = subprocess.run(["node", "-e", code, security.ERROR_CAPTURE_SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_first_receipt_has_explicit_errors_and_native_gate_requires_completeness(self):
        tree = ast.parse((TASK / "w6_security_probe.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_security_probe")
        assignment = next(n for n in function.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "evidence" for t in n.targets))
        keys = {k.value: v for k, v in zip(assignment.value.keys, assignment.value.values)}
        self.assertIsInstance(keys['javascriptErrors'], ast.List)
        self.assertEqual(keys['javascriptErrors'].elts, [])
        self.assertIs(keys['javascriptErrorsComplete'].value, False)
        native = ast.parse((TASK / 'w6_existing_window.py').read_text(encoding='utf-8'))
        gate = next(n for n in ast.walk(native) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == 'check' and n.args
                    and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'presentation-listeners-no-error')
        self.assertIn("security.get('javascriptErrorsComplete') is True", ast.unparse(gate.args[1]))

    def test_non_null_return_is_not_popup_creation_evidence(self):
        self.assertTrue(all(security.evaluate_security(clean_evidence()).values()))

    def test_missing_or_unsettled_axis_cannot_pass(self):
        self.assertFalse(any(security.evaluate_security({}).values()))
        for axis in ("network", "asset", "popup", "storage"):
            for broken in ({}, dict(settled=False)):
                evidence = clean_evidence(); evidence[axis] = broken
                self.assertFalse(security.evaluate_security(evidence)[axis], axis)

    def test_network_rejection_after_real_hit_still_fails(self):
        for hits in (2, None, True):
            evidence = clean_evidence(); evidence["probeHitsAfter"] = hits
            result = security.evaluate_security(evidence)
            self.assertFalse(result["network"]); self.assertFalse(result["popup"])

    def test_asset_fetch_rejection_alone_cannot_pass(self):
        for key, value in (("elementDenied", False), ("elementSettled", False), ("blockedByHost", 0), ("unexpectedReplies", 1)):
            evidence = clean_evidence(); evidence["asset"][key] = value
            self.assertFalse(security.evaluate_security(evidence)["asset"], key)

    def test_popup_null_with_actual_side_effect_cannot_pass(self):
        for key, value in (("newObjects", 1), ("creationEvents", 1), ("samePage", False), ("javascriptOpenDisabled", False)):
            evidence = clean_evidence(); evidence["popup"][key] = value
            for attempt in evidence["popup"]["attempts"]: attempt["returnNull"] = True
            self.assertFalse(security.evaluate_security(evidence)["popup"], key)
        evidence = clean_evidence(); evidence["popup"]["attempts"][0]["usableAfterDrain"] = True
        self.assertFalse(security.evaluate_security(evidence)["popup"])

    def test_storage_write_then_throw_and_reload_leaks_cannot_pass(self):
        for field in ("presentation", "nativeFirst", "nativeReload"):
            for phase in ("before", "after"):
                evidence = copy.deepcopy(clean_evidence())
                evidence["storage"][field][phase]["absent"] = False
                self.assertFalse(security.evaluate_security(evidence)["storage"], (field, phase))
        for field in ("otherStoresDenied", "localStorageDisabled", "offTheRecord"):
            evidence = clean_evidence(); evidence["storage"][field] = False
            self.assertFalse(security.evaluate_security(evidence)["storage"])

    def test_actual_storage_probe_detects_noop_throw_and_write_then_throw(self):
        # Execute the exact JS probe plus the real preference implementation.
        code = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ts=require('./pet-electron/node_modules/typescript');
const probe=eval(process.argv[1]);
let value=null;
global.localStorage={getItem:()=>value,setItem:()=>{value='SYNTHETIC';throw Error('after write')}};
assert.equal(probe('secret').after.absent,false);
value=null;global.localStorage={getItem:()=>null,setItem:()=>{}};
assert.equal(probe('secret').after.absent,true);
Object.defineProperty(global,'localStorage',{configurable:true,get(){throw Error('denied')}});
assert.equal(probe('secret').writeThrew,true);
delete global.localStorage;
const source=fs.readFileSync('devtools/original-git-web-host-20261010/frontend/src/owner-preferences.ts','utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const exports={};vm.runInNewContext(compiled,{exports,DOMException,Map,Set,Object,String});
global.localStorage=exports.presentationPreferences();
assert.equal(probe('secret').writeThrew,true);assert.equal(probe('secret').after.absent,true);
localStorage.setItem('kuro.work-panel.mode','settings');
assert.equal(localStorage.getItem('kuro.work-panel.mode'),'settings');
assert.equal(exports.presentationPreferences().getItem('kuro.work-panel.mode'),null);
console.log('actual probe and owner preferences: PASS');
"""
        process = subprocess.run(["node", "-e", code, security.STORAGE_PROBE], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_actual_host_denial_methods_and_counters_preserve_decisions(self):
        # Run the exact small Qt callbacks without constructing WebEngine.
        tree = ast.parse((ROOT / "kuro_launcher/qt_web_host.py").read_text(encoding="utf-8"))
        classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        counts = []; blocked = []
        env = dict(security_count=counts.append, audit=lambda *a, **k: None,
                   ENTRY="kuro-work://app/work-panel.html", bundle=SimpleNamespace(allowed=lambda _: False),
                   QWebEngineUrlRequestJob=SimpleNamespace(Error=SimpleNamespace(RequestDenied="DENIED")))
        def callback(cls, name):
            method = next(n for n in classes[cls].body if isinstance(n, ast.FunctionDef) and n.name == name)
            module = ast.Module(body=[method], type_ignores=[])
            exec(compile(module, '<actual-host-callback>', 'exec'), env)
            return env[name]
        url = SimpleNamespace(toString=lambda: 'kuro-work://app/denied', scheme=lambda: 'kuro-work')
        callback('Requests', 'interceptRequest')(None, SimpleNamespace(requestUrl=lambda: url, block=blocked.append))
        self.assertEqual(blocked, [True]); self.assertIn('assetBlocked', counts)
        failures = []
        callback('LocalFiles', 'requestStarted')(None, SimpleNamespace(requestUrl=lambda: url, requestMethod=lambda: b'GET', fail=failures.append))
        self.assertEqual(failures, ['DENIED']); self.assertIn('handlerDenied', counts)
        self.assertIsNone(callback('Page', 'createWindow')(None, None)); self.assertIn('popupDenied', counts)
        self.assertFalse(callback('Page', 'acceptNavigationRequest')(None, url, None, True))
        self.assertIn('navigationDenied', counts)


if __name__ == '__main__': unittest.main()
