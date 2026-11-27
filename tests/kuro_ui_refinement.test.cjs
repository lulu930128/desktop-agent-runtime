const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../pet-electron/node_modules/typescript');
const root = path.resolve('devtools/original-git-web-host-20261010/frontend/src');
function load(name) {
  const file = path.resolve(root, name+'.ts');
  const code = ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
  const m={exports:{}};
  new Function('require','module','exports',code)(r=>load(path.relative(root,path.resolve(path.dirname(file),r))),m,m.exports);
  return m.exports;
}
test('priority metadata preserves source summary and due date without raw reasons or mutation',()=>{
  const {todayItems}=load('canonical-model');
  const raw={id:'one',source:'japanese_study',text:'Synthetic review',date:'2026-10-23T09:30:00+08:00',
    summary:'Review the source-provided example.',meta:'source_partial · due_review',reasonCodes:['source_partial','due_review'],evidence:'original-json'};
  const before=JSON.stringify(raw);
  const [view]=todayItems({snapshot:{today:{items:[raw]}}});
  assert.match(view.meta,/Review the source-provided example/);
  assert.match(view.meta,/期限/); assert.doesNotMatch(view.meta,/source_partial|due_review/);
  assert.equal(view.evidence,'original-json'); assert.equal(JSON.stringify(raw),before);
  assert.equal(todayItems({snapshot:{today:{items:[{id:'none',text:'No invented date'}]}}})[0].meta,'');
});
test('useful human metadata is kept and long summary only truncated in presentation',()=>{
  const {todayItems}=load('canonical-model');
  const items=[{id:'one',text:'Title',meta:'Chapter 3 practice'}, {id:'two',text:'Title',summary:'界'.repeat(120)}];
  const views=todayItems({snapshot:{today:{items}}});
  assert.equal(views[0].meta,'Chapter 3 practice');
  assert.equal(views[1].meta,'界'.repeat(90)+'…'); assert.equal(views[1].raw.summary.length,120);
});
test('compact status preserves partial, stale, auth, missing and OMI blocked distinctions',()=>{
  const {sourceStatusLabel: label}=load('owner-presentation');
  const base={sourceId:'english_study',enabled:true,availability:'available',freshness:'current',evidenceCount:0};
  assert.equal(label(base),'本次無待辦');
  assert.equal(label({...base,availability:'partial'}),'本次無待辦 · 資料有限制');
  assert.equal(label({...base,availability:'partial',freshness:'unknown'}),'本次無待辦 · 資料有限制 · 時效未知');
  assert.equal(label({...base,availability:'partial',evidenceCount:1}),'部分資料');
  assert.match(label({...base,freshness:'stale'}),/資料過期/);
  assert.match(label({...base,freshness:'unknown'}),/時效未知/);
  assert.match(label({...base,connection:'auth_required'}),/需要授權/);
  assert.match(label({...base,availability:'missing'}),/尚無資料/);
  for (const availability of ['missing','auth_required','offline'])
    assert.doesNotMatch(label({...base,availability,evidenceCount:null}),/無待辦/);
  assert.equal(label({...base,enabled:false}),'已停用');
  assert.equal(label({...base,sourceId:'omi',executionAvailable:false}),'自動觀測未開放');
});
