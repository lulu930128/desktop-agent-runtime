const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../pet-electron/node_modules/typescript');
const root = path.resolve(__dirname, '../devtools/original-git-web-host-20261010/frontend');
const cache = new Map();
function load(name) {
  const file = path.resolve(root, 'src', name.endsWith('.ts') ? name : name+'.ts');
  if (cache.has(file)) return cache.get(file);
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
  const module = {exports:{}}; cache.set(file,module.exports);
  new Function('require','module','exports',output)((request)=>load(path.relative(path.join(root,'src'),path.resolve(path.dirname(file),request))),module,module.exports);
  return module.exports;
}

test('Core priority order including normal/calendar survives candidate presentation', () => {
  const model = load('canonical-model');
  const data={snapshot:{today:{items:[
    {id:'first',text:'first',source:'calendar',level:'normal'},
    {id:'second',text:'second',source:'study',level:'watch'},
    {id:'third',text:'third',source:'mail',level:'urgent'}]}}};
  assert.deepEqual(model.priorityItems(data).map(v=>v.id),['first','second','third']);
  assert.deepEqual(model.priorityItems(data).map(v=>v.level),['normal','watch','urgent']);
  assert.equal(model.sourceCount(data,'calendar'),1);
  assert.deepEqual(load('work-panel/model').priorityItems(data).map(v=>v.id),['third','second']);
});
test('Core top five is display truncation, never reranking or deduplication', () => {
  const items=Array.from({length:7},(_,i)=>({id:String(i),text:'same',source:'study',level:'normal'}));
  assert.deepEqual(load('canonical-model').priorityItems({snapshot:{today:{items}}}).map(v=>v.id),['0','1','2','3','4']);
});
test('candidate Vite resolver actually replaces only original main model import', async () => {
  const {default:config}=await import(require('node:url').pathToFileURL(path.join(root,'vite.owner.config.mjs')));
  const plugin=config.plugins[0];
  assert.equal(plugin.resolveId('./model',path.join(root,'src/work-panel/main.ts')).replaceAll('\\','/'),path.join(root,'src/canonical-model.ts').replaceAll('\\','/'));
  assert.equal(plugin.resolveId('./work-panel/model',path.join(root,'src/canonical-model.ts')),undefined);
});
test('IME Enter never submits; regular and Shift Enter remain original behavior', () => {
  const {isImeSubmit}=load('owner-presentation');
  assert.equal(isImeSubmit({key:'Enter',isComposing:true,keyCode:13},false),true);
  assert.equal(isImeSubmit({key:'Enter',isComposing:false,keyCode:229},false),true);
  assert.equal(isImeSubmit({key:'Enter',isComposing:false,keyCode:13},true),true);
  assert.equal(isImeSubmit({key:'Enter',isComposing:false,keyCode:13},false),false);
});

test('W7 resize uses CSS viewport bounds for all edges/corners and rejects maximized/invalid geometry', () => {
  const {windowResizeEdge: edge}=load('owner-presentation');
  for (const [x,y,want] of [[0,50,'left'],[99,50,'right'],[50,0,'top'],[50,99,'bottom'],
    [0,0,'top-left'],[99,0,'top-right'],[0,99,'bottom-left'],[99,99,'bottom-right']]) {
    assert.equal(edge(x,y,100,100,false),want);
    assert.equal(edge(x,y,100,100,true),null);
  }
  for(const [x,y,w,h] of [[6,6,100,100],[93,93,100,100],[-1,0,100,100],[100,0,100,100],[0,100,100,100],[NaN,0,100,100],[0,0,Infinity,100],[0,0,0,100]])
    assert.equal(edge(x,y,w,h,false),null);
});

test('W7 trusted header presses, double-click, controls and rail share exactly one transport', async () => {
  const previous={document:global.document,window:global.window,Element:global.Element};
  const listeners={}, events={}, calls=[];
  class Target {
    constructor(kind) { this.kind=kind; }
    closest(selector) {
      if(selector==='.chrome') return this.kind==='header' ? this : null;
      if(selector==='.rail') return this.kind==='rail' ? this : null;
      return selector.includes(this.kind) && !['header','rail','content'].includes(this.kind) ? this : null;
    }
  }
  global.Element=Target;
  global.document={documentElement:{style:{},dataset:{}},addEventListener:(name,fn)=>listeners[name]=fn};
  global.window={innerWidth:1000,innerHeight:700,addEventListener:(name,fn)=>listeners[name]=fn};
  const transport={on:(name,fn)=>events[name]=fn,call:async(method,payload)=>{
    calls.push([method,payload]); return {ok:true,maximized:false,doubleClickInterval:400,startDragDistance:10};
  }};
  try {
    load('owner-presentation').installWindowGestures(transport);
    await Promise.resolve(); calls.length=0;
    const press=(kind='header',patch={})=>{
      const event={isTrusted:true,pointerType:'mouse',isPrimary:true,button:0,buttons:1,target:new Target(kind),
        clientX:500,clientY:25,screenX:600,screenY:100,timeStamp:1000,
        preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...patch};
      listeners.pointerdown(event);return event;
    };
    const first=press(); assert.ok(first.prevented && first.stopped);
    press('header',{timeStamp:1200});
    assert.deepEqual(calls.map(x=>x[0]),['startWindowMove','toggleMaximizeWindow']);
    calls.length=0;
    for(const kind of ['button','input','textarea','select','a','label','[contenteditable]','.privacy-indicators','.window-actions','rail','content'])
      assert.equal(press(kind).prevented,undefined);
    for(const patch of [{isTrusted:false},{button:2},{buttons:3},{pointerType:'touch'},{isPrimary:false},{ctrlKey:true}]) press('header',patch);
    assert.equal(calls.length,0);
    press('button',{clientX:0}); assert.equal(calls.length,0);
    press('content',{clientX:0,clientY:0});
    assert.deepEqual(calls,[['startWindowResize',{edge:'top-left'}]]);
    calls.length=0; events.onWindowState({maximized:true});
    press('content',{clientX:0}); assert.equal(calls.length,0);
    press(); listeners.blur(); press('header',{timeStamp:1200});
    assert.deepEqual(calls.map(x=>x[0]),['startWindowMove','startWindowMove']);
  } finally {Object.assign(global,previous);}
});

test('presentation preferences cannot store arbitrary content or survive a new view', () => {
  const {presentationPreferences, installPresentationPreferences}=load('owner-preferences');
  const store=presentationPreferences();
  store.setItem('kuro.work-panel.mode','settings');
  assert.equal(store.getItem('kuro.work-panel.mode'),'settings');
  for (const [key,value] of [['token','private'],['kuro.work-panel.mode','private content'],['__proto__','x']])
    assert.throws(()=>store.setItem(key,value));
  assert.equal(presentationPreferences().length,0);
  const target={};installPresentationPreferences(target);
  for (const key of ['sessionStorage','indexedDB','caches']) assert.throws(()=>target[key],/unavailable/);
  assert.throws(()=>Object.defineProperty(target,'localStorage',{value:{}}));
});

test('all original preferences work while secret/token/PII inputs are refused', () => {
  const {presentationPreferences}=load('owner-preferences');const store=presentationPreferences();
  const values={mode:['chat','today','settings'],source:load('work-panel/model').SOURCE_ORDER.filter(x=>x!=='calendar'),
    'settings-section':['assistant','conversation','perception','tools','pet','diagnostics'],compact:['true','false'],'reduce-motion':['true','false']};
  for (const [name,choices] of Object.entries(values)) for (const value of choices) {
    store.setItem('kuro.work-panel.'+name,value);assert.equal(store.getItem('kuro.work-panel.'+name),value);
  }
  for (const key of [...Object.keys(values).map(k=>'kuro.work-panel.'+k),'secret','token','history','memory','email','authorization'])
    for (const content of ['SYNTHETIC_SECRET_CANARY','Bearer SYNTHETIC_TOKEN','private@example.invalid','SYNTHETIC private message'])
      assert.throws(()=>store.setItem(key,content),e=>e.name==='SecurityError');
  assert.equal(store.length,5);
  const bootstrap=fs.readFileSync(path.join(root,'src/owner-bootstrap.ts'),'utf8');
  assert.ok(bootstrap.indexOf('installPresentationPreferences(window)')<bootstrap.indexOf('await import("./work-panel/main")'));
  const main=fs.readFileSync(path.join(root,'src/work-panel/main.ts'),'utf8');
  const keys=[...new Set([...main.matchAll(/localStorage\.(?:getItem|setItem)\("([^"]+)"/g)].map(m=>m[1]))].sort();
  assert.deepEqual(keys,Object.keys(values).map(k=>'kuro.work-panel.'+k).sort());
  for (const name of ['owner-bootstrap.ts','owner-bridge.ts','owner-presentation.ts','canonical-model.ts'])
    assert.doesNotMatch(fs.readFileSync(path.join(root,'src',name),'utf8'),/localStorage\.(?:setItem|getItem)|QSettings/);
});

function harness(timeout=100) {
  const sent=[]; let response, event;
  const t = new (load('owner-bridge').OwnerTransport)({submit(raw){sent.push(JSON.parse(raw));},response:{connect(cb){response=cb;}},event:{connect(cb){event=cb;}}},timeout);
  const identity={client:'c',actor:'a',history:'h',context:'x',revision:0};
  function reply(result, extra={}) {const req=sent.at(-1); response(JSON.stringify({contract:'kuro.qt.work.v1',id:req.id,expected:req.expected,identity,result,...extra}));}
  return {t,sent,reply,identity,event:value=>event(JSON.stringify(value))};
}

test('real original renderChrome Pet-ready branch requires lifecycle voice contract', () => {
  const file=ts.createSourceFile('main.ts',fs.readFileSync(path.join(root,'src/work-panel/main.ts'),'utf8'),ts.ScriptTarget.Latest,true);
  const cls=file.statements.find(n=>ts.isClassDeclaration(n));
  const method=cls.members.find(n=>n.name?.getText(file)==='renderChrome');
  const js=ts.transpileModule(`class Probe { ${method.getText(file)} }`,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText;
  const status={replaceChildren(){},appendChild(){}};
  const appRoot={querySelector:s=>s==='[data-runtime-status]'?status:null,querySelectorAll:()=>[]};
  const Probe=new Function('appRoot','createElement','button','text',js+'; return Probe;')(appRoot,()=>({}),()=>({}),(v,f)=>String(v??f));
  const probe=new Probe();probe.mode='chat';probe.chat={};probe.capabilitySummary=()=>'';
  const pet={state:'unavailable'};
  probe.runtime={wsConnected:true,capabilities:{pet,launcher:{ok:false,state:'unavailable'}}};
  probe.renderChrome(); // Exact pre-fix projection: first state succeeds.
  pet.state='ready';
  assert.throws(()=>probe.renderChrome(),TypeError); // Same branch as native second state.
  probe.runtime.capabilities.launcher={voice:{state:'unknown'},restartRequired:false};
  probe.renderChrome();
  assert.equal(status.hidden,false); // Unknown voice must remain visible.
});

test('throwing state listener cannot orphan the already accepted owner reply', async () => {
  const h=harness(5);const hello=h.t.hello();h.reply({ok:true});await hello;
  h.t.on('onState',()=>{throw new TypeError('SYNTHETIC listener');});
  const pending=h.t.call('getState');
  assert.throws(()=>h.reply({ok:true}),TypeError); // Error is still observable, never swallowed.
  const result=await Promise.race([pending,new Promise(resolve=>setTimeout(()=>resolve({orphaned:true}),30))]);
  assert.equal(result.orphaned,undefined);
  assert.equal(result.ok,true);
  assert.equal(h.sent.length,2); // No retry.
});
test('bootstrap handshake precedes every owner method; no fallback', async () => {
  const h=harness();
  assert.equal((await h.t.call('getState')).error,'owner_not_ready');
  const p=h.t.hello();h.reply({ok:true});await p;
  const bridge=load('owner-bridge').makeOwnerBridge(h.t);
  const result=bridge.schedule('materialize',{through:'2026-10-11'});
  assert.deepEqual(h.sent.at(-1).payload,{action:'materialize',payload:{through:'2026-10-11'}});
  h.reply({ok:false,error:'materialize_owned_by_core_scheduler'});
  assert.equal((await result).ok,false);
});
test('every WorkPanelBridge method is explicitly bound', () => {
  const declared=fs.readFileSync(path.join(root,'src/work-panel/types.ts'),'utf8').split('export interface WorkPanelBridge {')[1].split('\n}')[0];
  const names=Array.from(declared.matchAll(/^  (\w+)\(/gm),m=>m[1]);
  const bridge=load('owner-bridge').makeOwnerBridge({call(){},on(){}});
  assert.deepEqual(Object.keys(bridge).sort(),names.sort());
});

test('notification writes require advertised Core contract and a fresh revision', async () => {
  const h=harness();const hello=h.t.hello();h.reply({ok:true});await hello;
  const bridge=load('owner-bridge').makeOwnerBridge(h.t);
  const command={action:'dismiss',id:'fixture',confirmed:true};
  assert.equal((await bridge.schedule('notification-action',command)).ok,false);
  assert.equal(h.sent.length,1);
  const read=bridge.schedule('notifications');
  h.reply({ok:true,consumerWriteContract:'kuro.core.notification-command.v1',items:[{id:'fixture',revision:'a'.repeat(64)}]});await read;
  const write=bridge.schedule('notification-action',command);
  assert.equal(h.sent.at(-1).payload.payload.expectedRevision,'a'.repeat(64));
  assert.ok(h.sent.at(-1).payload.payload.idempotencyKey);
  h.reply({ok:false,unknownResult:true,retry:false});await write;
  const count=h.sent.length;
  assert.equal((await bridge.schedule('notification-action',command)).ok,false);
  assert.equal(h.sent.length,count);
});
test('timeout returns unknown without retransmission', async () => {
  const h=harness(5);const hello=h.t.hello();h.reply({ok:true});await hello;
  const result=await h.t.call('sendText',{text:'SYNTHETIC',attachments:[]});
  assert.equal(result.unknownResult,true);assert.equal(h.sent.length,2);
});
test('stale mutation response retains backend unknown-result semantics', async () => {
  const h=harness();const hello=h.t.hello();h.reply({ok:true});await hello;
  const pending=h.t.call('sendText',{text:'SYNTHETIC',attachments:[]});
  h.reply({ok:false,error:'context_changed_during_operation',unknownResult:true,retry:false},
    {identity:{...h.identity,context:'new',revision:1}});
  const result=await pending;
  assert.equal(result.error,'stale_context');assert.equal(result.unknownResult,true);assert.equal(result.retry,false);
});
test('polled Today failure retains same-scope data with a transport-stale marker', async () => {
  const h=harness();const hello=h.t.hello();h.reply({ok:true});await hello;
  const seen=[];h.t.on('onData',v=>seen.push(v));
  h.event({contract:'kuro.qt.work.v1',identity:h.identity,name:'onData',value:{ok:true,canonical:{generatedAt:'SYNTHETIC'}}});
  h.event({contract:'kuro.qt.work.v1',identity:h.identity,name:'onData',value:{ok:false,error:'offline'}});
  assert.equal(seen.at(-1).transportStale,true);assert.equal(seen.at(-1).ok,false);
  assert.equal(seen.at(-1).canonical.generatedAt,'SYNTHETIC');
  h.event({contract:'kuro.qt.work.v1',identity:{...h.identity,context:'new',revision:1},name:'onData',value:{ok:false,error:'offline'}});
  assert.equal(seen.at(-1).canonical,undefined);
});
test('old responses cannot overwrite a newer event identity', async () => {
  const h=harness();const hello=h.t.hello();h.reply({ok:true});await hello;
  const request=h.t.call('getData');
  h.event({contract:'kuro.qt.work.v1',name:'onChatState',identity:{...h.identity,actor:'new',revision:1},value:{}});
  h.reply({ok:true});assert.equal((await request).error,'stale_response');assert.equal(h.t.identity.actor,'new');
});
test('callback unsubscribe and malformed events are bounded', async () => {
  const h=harness();let calls=0;const stop=h.t.on('onState',()=>calls++);
  const e={contract:'kuro.qt.work.v1',name:'onState',identity:h.identity,value:{ok:true}};
  h.event(e);stop();h.event(e);h.event({...e,identity:{}});assert.equal(calls,1);
});

test('Today failure preserves same-context stale evidence but never another context cache', async () => {
  const h=harness();const hello=h.t.hello();h.reply({ok:true});await hello;
  let request=h.t.call('getData');h.reply({ok:true,canonical:{fixture:'SYNTHETIC'}});await request;
  request=h.t.call('getData');h.reply({ok:false,error:'offline'});
  assert.equal((await request).transportStale,true);
  const changed={...h.identity,actor:'new',revision:1};
  h.event({contract:'kuro.qt.work.v1',name:'onChatState',identity:changed,value:{}});
  request=h.t.call('getData');h.reply({ok:false,error:'offline'},{identity:changed});
  assert.equal((await request).canonical,undefined);
});

test('notification review expires when owner context changes', async () => {
  const h=harness();const hello=h.t.hello();h.reply({ok:true});await hello;
  const bridge=load('owner-bridge').makeOwnerBridge(h.t);
  const read=bridge.schedule('notifications');
  h.reply({ok:true,consumerWriteContract:'kuro.core.notification-command.v1',items:[{id:'fixture',revision:'a'.repeat(64)}]});await read;
  h.event({contract:'kuro.qt.work.v1',name:'onChatState',identity:{...h.identity,context:'new',revision:1},value:{}});
  const count=h.sent.length;
  const result=await bridge.schedule('notification-action',{action:'dismiss',id:'fixture'});
  assert.equal(result.ok,false);assert.equal(h.sent.length,count);
});
