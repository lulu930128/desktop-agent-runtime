const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../../pet-electron/node_modules/typescript');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'frontend/src/synthetic.json'), 'utf8'));
const source = fs.readFileSync(path.join(__dirname, 'frontend/src/preview-bridge.ts'), 'utf8');
const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true}}).outputText;
const exportsObject = {};
vm.runInNewContext(output, {exports: exportsObject, require(name) {
  assert.equal(name, './synthetic.json'); return fixture;
}});

test('read fixture is detached; prototype keys cannot become capabilities', async () => {
  const profile = await exportsObject.syntheticRequest('getProfile');
  profile.models.length = 0;
  assert.equal((await exportsObject.syntheticRequest('getProfile')).models.length, 1);
  assert.equal((await exportsObject.syntheticRequest('__proto__')).ok, false);
  assert.equal((await exportsObject.syntheticRequest('getHistories', {historyUid: 'private'})).ok, false);
});

test('all frontend mutators fail closed without entering native request transport', async () => {
  let calls = 0;
  const bridge = exportsObject.makeBridge(async () => { calls++; throw Error('unexpected transport'); });
  for (const method of ['applyProfile', 'createHistory', 'selectHistory', 'deleteHistory', 'memoryAction', 'sendText', 'refreshMail', 'getMailMessage', 'control']) {
    const result = await bridge[method]('synthetic', []);
    assert.equal(result.ok, false, method);
    assert.match(result.error, /unavailable/);
  }
  assert.equal(calls, 0);
});

test('schedule writes cannot mutate fixture or report success', async () => {
  const before = JSON.stringify(fixture);
  const bridge = exportsObject.makeBridge(exportsObject.syntheticRequest);
  for (const action of ['mutate', 'materialize', 'prepare', 'notification-action']) {
    assert.equal((await bridge.schedule(action, {action: 'delete'})).ok, false);
  }
  assert.equal(JSON.stringify(fixture), before);
});
