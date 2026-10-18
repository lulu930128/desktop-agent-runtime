const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("../pet-electron/node_modules/typescript");
const shell = require("../pet-electron/src/main-process/pet-fixed-shell");
const { normalizeHostBounds } = require("../pet-electron/src/main-process/pet-host-envelope");
const root = path.join(__dirname, "..");
const displays = [
  {bounds:{x:0,y:0,width:2560,height:1440},scaleFactor:1.25},
  {bounds:{x:2560,y:0,width:2560,height:1440},scaleFactor:1.5}
];
const anchor = Object.freeze({x:3047.24,y:2638.69});
const transform = Object.freeze({revision:3,anchor,zoomScale:1.8308504694065357});
const plain = value => JSON.parse(JSON.stringify(value));

function nativeFixture(accept = bounds => bounds) {
  let bounds = {...displays[0].bounds};
  const calls = [];
  const window = {
    isDestroyed:()=>false,
    getBounds:()=>bounds && {...bounds},
    getContentBounds:()=>bounds && {...bounds},
    setBounds:requested=>{ calls.push({...requested}); bounds=accept(requested); }
  };
  return {window,calls,read:()=>bounds};
}

test("union accepted uses one attempt; clamp falls back once to saved anchor display", () => {
  for (const clamp of [false,true]) {
    const fixture = nativeFixture(b=>clamp && b.width>2560 ? displays[0].bounds : b);
    const result = shell.reconcileFixedPetShell({window:fixture.window,displays,anchor,reason:"startup",applyBounds:fixture.window.setBounds});
    assert.equal(result.state,clamp ? "per-display" : "union");
    assert.equal(fixture.calls.length,clamp ? 2 : 1);
    assert.deepEqual(result.actualBounds,clamp ? displays[1].bounds : {x:0,y:0,width:5120,height:1440});
    assert.deepEqual(anchor,{x:3047.24,y:2638.69});
  }
});

test("persistent clamp and unavailable native readback terminate without retry loops", () => {
  for (const [actual,state] of [[displays[0].bounds,"degraded"],[null,"unknown"]]) {
    const fixture=nativeFixture(()=>actual);
    const result=shell.reconcileFixedPetShell({window:fixture.window,displays,anchor,reason:"display-topology",applyBounds:fixture.window.setBounds});
    assert.equal(result.state,state);
    assert.equal(fixture.calls.length,2);
    assert.deepEqual(result.actualBounds,actual);
  }
});

test("negative-origin mixed-DPI display selection stays in DIPs and rejects unknown inputs", () => {
  const negative={x:-2560,y:-120,width:2560,height:1440};
  const areas=[{bounds:negative,scaleFactor:1.5},displays[0]];
  assert.deepEqual(shell.selectAnchorDisplayBounds(areas,{x:-1000,y:2600}),negative);
  // With vertically offset monitors, the closest rectangle need not contain anchor.x.
  assert.deepEqual(shell.selectAnchorDisplayBounds(areas,{x:-500,y:2600}),displays[0].bounds);
  assert.equal(shell.selectAnchorDisplayBounds(displays,{x:NaN,y:0}),null);
  assert.equal(shell.selectAnchorDisplayBounds([{bounds:{x:0,y:0,width:0,height:1440}}],anchor),null);
  for (const window of [null,{isDestroyed:()=>true},{isDestroyed:()=>false,getContentBounds:()=>{throw Error("fixture");}},
    {isDestroyed:()=>false,getContentBounds:()=>({x:0,y:0,width:NaN,height:1})}]) {
    assert.equal(shell.readNativeContentBounds(window),null);
  }
});

test("reconciliation never grants status, layout, drag, zoom or envelope mutation", () => {
  for (const reason of ["status","pet-layout","drag","zoom","model-envelope"]) {
    assert.equal(shell.canMutateFixedPetShell(reason),false);
    assert.equal(shell.reconcileFixedPetShell({window:null,displays,anchor,reason,
      applyBounds:()=>assert.fail("forbidden mutation")}).state,"denied");
  }
});

const mainSource=fs.readFileSync(path.join(root,"pet-electron/src/main.js"),"utf8");
const mainTree=ts.createSourceFile("main.js",mainSource,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
const functions=new Map(mainTree.statements.filter(ts.isFunctionDeclaration).map(n=>[n.name.text,n.getText(mainTree)]));
function mainFixture() {
  const native=nativeFixture(b=>b.width>2560 ? displays[0].bounds : b);
  const sent=[];
  const handlers=new Map();
  const ctx={...shell,normalizeHostBounds,mainWindow:native.window,
    PET_FIXED_DESKTOP_SHELL:true,PET_HOST_MODE:"fixture",appState:{mode:"pet",outfit:{},expression:{}},
    currentFixedPetShellBounds:null,pendingFixedPetShellTopology:false,fixedPetShellReconciliation:null,
    fixedPetShellBoundsWriteCount:0,fixedPetShellBoundsRejectedCount:0,
    lastFixedPetShellBoundsWriteReason:null,lastFixedPetShellBoundsRejectedReason:null,
    petInteractionState:{dragActive:false,zoomActive:false},latestPetModelScreenBounds:null,
    ensurePetTransformState:()=>transform,getAllDisplays:()=>displays,
    resolvePetDisplayContext:()=>({displayId:2,scaleFactor:1.5,workArea:displays[1].bounds}),
    broadcast:(_channel,payload)=>sent.push(plain(payload)),petLog:()=>{},
    saveCurrentState:()=>assert.fail("native reconciliation saved state"),
    ipcMain:{on:(name,callback)=>handlers.set(name,callback),handle:()=>{}},
    process:{env:{}},localPresentation:null,screen:{getCursorScreenPoint:()=>({x:0,y:0})}};
  const names=["rebuildFixedPetShellBounds","getFixedPetShellBounds","getPetHostBounds","getPetHostSizingMode",
    "applyMainWindowBounds","buildPetHostStatePayload","broadcastPetHostState","isPetInteractionActive",
    "reconcilePetNativeShell","flushPendingFixedPetShellTopology","setPetDragInteractionActive","registerIpc"];
  vm.runInNewContext(names.map(name=>functions.get(name)).join("\n"),ctx);
  return {ctx,native,sent,handlers};
}

test("production startup/topology readback reaches bootstrap and host-set without changing transform", () => {
  const {ctx,native,sent,handlers}=mainFixture();
  ctx.reconcilePetNativeShell("startup");
  assert.equal(native.calls.length,2);
  assert.equal(ctx.fixedPetShellBoundsWriteCount,1); // Clamped union did not change the real native frame.
  assert.deepEqual(sent.at(-1).petHostBounds,displays[1].bounds);
  assert.deepEqual(sent.at(-1).petShellBounds,displays[1].bounds);
  ctx.registerIpc();
  const event={};
  handlers.get("get-bootstrap-config")(event);
  assert.deepEqual(plain(event.returnValue.petShellBounds),displays[1].bounds);
  assert.deepEqual(plain(event.returnValue.petAnchor),anchor);
  assert.equal(event.returnValue.zoomScale,transform.zoomScale);
  ctx.mainWindow.getContentBounds=()=>null;
  handlers.get("get-bootstrap-config")(event);
  assert.equal(event.returnValue.petShellBounds,null);
  assert.equal(event.returnValue.petHostBounds,null);
  assert.match(functions.get("createWindow"),/reconcilePetNativeShell\("startup"\)/);
});

test("production topology waits for both drag and zoom, then broadcasts readback once", () => {
  const {ctx,native,sent}=mainFixture();
  ctx.petInteractionState.dragActive=true;
  ctx.petInteractionState.zoomActive=true;
  ctx.reconcilePetNativeShell("display-topology");
  assert.equal(native.calls.length,0);
  assert.equal(ctx.pendingFixedPetShellTopology,true);
  ctx.setPetDragInteractionActive(false);
  assert.equal(native.calls.length,0);
  ctx.petInteractionState.zoomActive=false;
  ctx.flushPendingFixedPetShellTopology();
  assert.equal(native.calls.length,2);
  assert.equal(sent.length,1);
  ctx.flushPendingFixedPetShellTopology();
  assert.equal(native.calls.length,2);
  assert.equal(sent[0].transformRevision,3);
});

function loadRenderer(relative,imports={},globals={}) {
  const exports={};
  const code=ts.transpileModule(fs.readFileSync(path.join(root,"pet-electron/renderer/src",relative),"utf8"),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
  vm.runInNewContext(code,{exports,module:{exports},require:name=>{
    assert.ok(name in imports,`Unexpected import ${name}`); return imports[name];
  },...globals});
  return exports;
}

test("actual command router and main callback recover a null shell only on valid current frame", () => {
  const geometry=loadRenderer("geometry/pet-render-surface-geometry.ts");
  const {PetRenderSurfaceController}=loadRenderer("live2d/pet-render-surface-controller.ts",
    {"../geometry/pet-render-surface-geometry":geometry});
  const element={style:{},parentElement:{classList:{add(){}}}};
  const surface=new PetRenderSurfaceController(element,{enabled:true,shellBounds:null,anchorScreenPoint:anchor,transformRevision:3});
  let receive;
  const commands=loadRenderer("commands/pet-command-geometry.ts");
  const {bindPetCommands}=loadRenderer("commands/pet-command-router.ts",
    {"./pet-command-geometry":commands,"../model-zoom":{storeModelZoomScale:()=>assert.fail("host changed zoom")}},
    {window:{kuroPetElectron:{onCommand:callback=>{receive=callback;return ()=>{};}}}});
  const rendererSource=fs.readFileSync(path.join(root,"pet-electron/renderer/src/main.ts"),"utf8");
  const rendererTree=ts.createSourceFile("main.ts",rendererSource,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS);
  let callback;
  function visit(node) {
    if(ts.isPropertyAssignment(node) && node.name.getText(rendererTree)==="onHostAccepted") callback=node.initializer.getText(rendererTree);
    ts.forEachChild(node,visit);
  }
  visit(rendererTree);
  assert.ok(callback,"production main callback exists");
  let setters=0;
  bindPetCommands({renderer:{getTransformRevision:()=>3,setExpectedHostBounds:()=>setters++},
    onHostAccepted:vm.runInNewContext(`(${callback})`,{renderSurface:surface})});
  for(const petHostBounds of [null,{...displays[1].bounds,width:0}]) receive({type:"pet-host-set",transformRevision:3,petHostBounds});
  receive({type:"pet-host-set",transformRevision:2,petHostBounds:displays[1].bounds});
  assert.equal(setters,0);
  assert.equal(surface.flushPending(),false);
  receive({type:"pet-host-set",transformRevision:3,petHostBounds:displays[1].bounds});
  assert.equal(setters,1);
  assert.equal(surface.flushPending(),true);
  const state=surface.getSnapshot();
  assert.deepEqual(plain(state.shellBounds),displays[1].bounds);
  assert.deepEqual(plain(state.applied.anchorScreenPoint),anchor);
  assert.equal(state.applied.transformRevision,3);
  assert.ok(element.style.transform.includes("107.24px"));
});

test("unknown shell retains newest transform and rejects stale or invalid transforms", () => {
  const geometry=loadRenderer("geometry/pet-render-surface-geometry.ts");
  const {PetRenderSurfaceController}=loadRenderer("live2d/pet-render-surface-controller.ts",{"../geometry/pet-render-surface-geometry":geometry});
  const surface=new PetRenderSurfaceController({style:{}},{enabled:true,shellBounds:null,anchorScreenPoint:anchor,transformRevision:3});
  assert.equal(surface.scheduleTransform({x:3000,y:2500},4),false);
  assert.equal(surface.scheduleTransform({x:0,y:0},3),false);
  assert.equal(surface.scheduleTransform({x:NaN,y:0},5),false);
  assert.equal(surface.scheduleShellBounds(displays[1].bounds),true);
  assert.equal(surface.flushPending(),true);
  assert.equal(surface.getSnapshot().applied.transformRevision,4);
  assert.deepEqual(plain(surface.getSnapshot().applied.anchorScreenPoint),{x:3000,y:2500});
  assert.equal(surface.getSnapshot().applied.localBounds.x,60);
});
