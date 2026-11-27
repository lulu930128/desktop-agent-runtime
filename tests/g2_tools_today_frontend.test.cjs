const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('../pet-electron/node_modules/typescript');
const source = fs.readFileSync('devtools/original-git-web-host-20261010/frontend/src/owner-presentation.ts','utf8');
const compiled = ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
const loaded = {exports:{}};
new Function('exports','module',compiled)(loaded.exports,loaded);
const {sourceCopy,reasonLabel,saveToolSetting,validToolSettings} = loaded.exports;
const policy = JSON.parse(fs.readFileSync('Open-LLM-VTuber/tool_policy.json','utf8'));
const initial = {ok:true,contract:'kuro.tool-policy-settings.v1',digest:'a'.repeat(64),runtime_adoption:'UNVERIFIED',confirmation_available:false,
  catalog:{toolNames:Object.keys(policy.tools),groups:Object.fromEntries(Object.keys(policy.tools).map(name=>[name.split('::')[0],'測試服務']))},
  tools:Object.entries(policy.tools).map(([name,row])=>({name,label:'測試功能',description:'合成用途',service:name.split('::')[0],serviceLabel:'測試服務',mode:row.mode,enabled:true,allowed:row.mode==='read_only'}))};

test('source overview distinguishes empty limited missing offline auth stale and auto blocked',()=>{
  const base={sourceId:'english_study',enabled:true,availability:'available',connection:'connected',freshness:'current',evidenceCount:0};
  assert.match(sourceCopy(base),/沒有待辦/);
  assert.match(sourceCopy({...base,availability:'partial'}),/仍有限制/);
  assert.match(sourceCopy({...base,availability:'missing',evidenceCount:null}),/不代表零筆/);
  assert.match(sourceCopy({...base,connection:'disconnected'}),/未連線/);
  assert.match(sourceCopy({...base,availability:'auth_required'}),/需要授權/);
  assert.match(sourceCopy({...base,freshness:'stale'}),/已過期/);
  assert.match(sourceCopy({...base,enabled:false}),/已停用/);
  assert.match(sourceCopy({...base,sourceId:'omi',enabled:false,executionAvailable:false}),/不會排程/);
  assert.match(reasonLabel('source_observed_at_missing'),/未提供觀察時間/);
  assert.match(reasonLabel('future_unknown_reason'),/診斷/);
});

test('policy UI writes only boolean plus CAS and verifies GET without adoption claim',async()=>{
  assert.equal(validToolSettings(initial),true);
  const name=initial.tools[0].name;
  const written={...initial,digest:'b'.repeat(64),persisted:true,tools:initial.tools.map(r=>({...r,enabled:r.name!==name}))};
  const calls=[];
  const result=await saveToolSetting({call:async(method,payload)=>{calls.push([method,payload]);return written;}},initial,name,false);
  assert.equal(result.digest,written.digest);
  assert.deepEqual(calls.map(r=>r[0]),['updateToolPolicy','getTools']);
  assert.deepEqual(calls[0][1],{name,enabled:false,expectedDigest:initial.digest});
  assert.equal(validToolSettings({...initial,runtime_adoption:'VERIFIED'}),false);
});

test('policy UI accepts the canonical inventory without a fixed legacy count',()=>{
  assert.equal(initial.tools.length,Object.keys(policy.tools).length);
  assert.ok(Object.keys(initial.catalog.groups).length>=5);
  assert.equal(validToolSettings({...initial,tools:initial.tools.slice(1)}),false);
  assert.equal(validToolSettings({...initial,catalog:{...initial.catalog,groups:{}}}),false);
  const dynamic = Array.from({length:181},(_,i)=>({...initial.tools[0],service:'project-workspace',
    serviceLabel:'專案',name:'project-workspace::tool_'+i,mode:'owner'}));
  assert.equal(validToolSettings({...initial,tools:dynamic,catalog:{toolNames:dynamic.map(r=>r.name),
    groups:{'project-workspace':'專案'}}}),true);
  assert.equal(initial.tools.filter(r=>r.service==='kuro-filesystem').length,1);
  assert.equal(validToolSettings({...initial,tools:[]}),false);
  assert.equal(validToolSettings({...initial,tools:[initial.tools[0],initial.tools[0]]}),false);
  assert.equal(validToolSettings({...initial,tools:Array.from({length:129},(_,i)=>({...initial.tools[0],name:'fixture::'+i}))}),false);
});

test('cancel no retry, stale readback and permission upgrade in reply never look saved',async()=>{
  let calls=0;
  assert.equal((await saveToolSetting({call:async()=>{calls++;return {ok:false,cancelled:true};}},initial,initial.tools[0].name,false)).cancelled,true);
  assert.equal(calls,1);
  const changed={...initial,persisted:true,digest:'b'.repeat(64)};
  assert.equal((await saveToolSetting({call:async method=>method==='updateToolPolicy'?changed:initial},initial,initial.tools[0].name,false)).unknownResult,true);
  const name='kuro-mail::mail.auth_start';
  const bad={...changed,tools:initial.tools.map(r=>r.name===name?{...r,mode:'read_only'}:r)};
  assert.equal((await saveToolSetting({call:async()=>bad},initial,name,true)).unknownResult,true);
});

test('new source preferences are process local and cannot store policy',()=>{
  const code=ts.transpileModule(fs.readFileSync('devtools/original-git-web-host-20261010/frontend/src/owner-preferences.ts','utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
  const m={exports:{}};new Function('exports','module',code)(m.exports,m);
  const store=m.exports.presentationPreferences();
  for(const value of ['japanese_study','english_study','omi']) {
    store.setItem('kuro.work-panel.source',value);assert.equal(store.getItem('kuro.work-panel.source'),value);
  }
  assert.throws(()=>store.setItem('tool_policy','enabled'));
});
