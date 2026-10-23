// Consume real isolated Qt Port -> HTTP Core results in the production frontend.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('../pet-electron/node_modules/typescript');
const source = fs.readFileSync('devtools/original-git-web-host-20261010/frontend/src/owner-presentation.ts', 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
const loaded = {exports:{}};
new Function('exports','module', compiled)(loaded.exports,loaded);
const {validAssistantSettings,saveAssistantSettings} = loaded.exports;
(async () => {
  const [initial,written,readback] = JSON.parse(fs.readFileSync(0, 'utf8'));
  for (const value of [initial,written,readback]) assert.equal(validAssistantSettings(value),true);
  assert.equal(validAssistantSettings({...initial,ok:undefined}),false);
  const calls=[];
  const transport={call:async(method,payload)=>{
    calls.push([method,payload]);
    if(method==='updateAssistantSettings') {
      assert.equal(payload.expectedRevision,initial.revision);
      assert.equal(payload.confirmed,undefined);
      return written;
    }
    return readback;
  }};
  assert.deepEqual(await saveAssistantSettings(transport,initial,written.settings),readback);
  assert.deepEqual(calls.map(c=>c[0]),['updateAssistantSettings','getAssistantSettings']);
  let count=0;
  assert.equal((await saveAssistantSettings({call:async()=>{count++;return {ok:false,cancelled:true};}},initial,written.settings)).cancelled,true);
  assert.equal(count,1);
  assert.equal((await saveAssistantSettings({call:async method=>method==='updateAssistantSettings'?written:{...readback,revision:'0'.repeat(64)}},initial,written.settings)).error,'settings_readback_unverified');
  assert.ok(source.includes('觀測間隔（分鐘，5–1440）'));
  assert.equal(source.includes('\ufffd'),false);
  console.log('PASS real Qt envelope/frontend validation, save/readback, cancel, stale-readback, UTF-8');
})().catch(error=>{console.error(error);process.exitCode=1;});
