const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { once } = require("node:events");
const ts = require("../pet-electron/node_modules/typescript");
const { startControlServer } = require("../pet-electron/src/main-process/control-server");
const { petCapability, withTimeout } = require("../pet-electron/src/main-process/pet-status");
const { readNativeContentBounds } = require("../pet-electron/src/main-process/pet-fixed-shell");
const source = fs.readFileSync(path.join(__dirname, "../pet-electron/src/main.js"), "utf8");
const tree = ts.createSourceFile("main.js", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
const functions = new Map(tree.statements.filter(ts.isFunctionDeclaration).map(n => [n.name.text, n.getText(tree)]));

const firstDisplay = { x: 0, y: 0, width: 2560, height: 1440 };
const secondDisplay = { x: 2560, y: 0, width: 2560, height: 1440 };
const displays = [{ bounds: firstDisplay, scaleFactor: 1.25 }, { bounds: secondDisplay, scaleFactor: 1.5 }];
const inspector = { ready: true, transformRevision: 3,
  modelScreenBounds: { left: 2772.335046, top: 844.35, right: 3447.55, bottom: 2643.20 } };

test("pet-local status preserves missing/loading/failed and unknown geometry", async () => {
  assert.equal(petCapability(null, null, 0, [], null).state, "missing");
  assert.equal(petCapability(null, {}, 1, [], null).state, "loading");
  assert.equal(petCapability(null, {}, 21000, [], null).state, "failed");
  assert.equal(petCapability({ready:true}, {}, 21000, displays, firstDisplay, true).state, "unknown");
  assert.equal(petCapability(inspector, {}, 21000, displays, null, true).state, "unknown");
  assert.equal(await withTimeout(Promise.reject(Error("fixture")), 20, null), null);
  assert.equal(await withTimeout(new Promise(() => {}), 20, "unavailable"), "unavailable");
});
test("real production probe uses only renderer and never reports a Launcher failure", async () => {
  const ctx = { capabilityRefreshPending:false, localPresentation:{}, modelRequestedAt:0,
    runtimeCapabilities:null, latestPetCapabilityInspector:null, latestPetCapabilityObservedAt:0,
    mainWindow:{isDestroyed:()=>false, getContentBounds:()=>secondDisplay},
    readLive2DInspectorSnapshot:async () => inspector, readNativeContentBounds,
    isPetNativeWindowVisible:()=>true, getAllDisplays:() => displays, withTimeout, petCapability, Date };
  const refresh = vm.runInNewContext(functions.get("refreshRuntimeCapabilities") + "\nrefreshRuntimeCapabilities", ctx);
  await refresh();
  assert.equal(ctx.runtimeCapabilities.pet.state, "ready");
  assert.equal("launcher" in ctx.runtimeCapabilities, false);
  ctx.readLive2DInspectorSnapshot = async () => { throw Error("fixture inspector failed"); };
  await refresh();
  assert.equal(ctx.runtimeCapabilities.pet.visible, false);
  assert.equal(ctx.latestPetCapabilityInspector, null);
});

test("renderer-ready second-screen model is offscreen in first-screen native content", () => {
  const result = petCapability(inspector, {}, 21000, displays, firstDisplay, true);
  assert.equal(result.modelReady, true);
  assert.equal(result.visibleOnDisplay, true);
  assert.equal(result.visibleWithinNativeContent, false);
  assert.equal(result.state, "offscreen");
  assert.equal(result.hostClip, "full");
  assert.equal(result.visible, false);
  const partial = petCapability(inspector, {}, 21000, displays, secondDisplay, true);
  assert.equal(partial.state, "ready");
  assert.equal(partial.hostClip, "partial");
});

test("visibility requires a usable triple intersection, not separate pairwise overlaps", () => {
  const model = { ready:true, modelScreenBounds:{left:0, top:0, right:300, bottom:100} };
  const result = petCapability(model, {}, 21000,
    [{bounds:{x:0,y:0,width:100,height:100}}], {x:200,y:0,width:100,height:100}, true);
  assert.equal(result.visibleOnDisplay, true);
  assert.equal(result.visibleWithinNativeContent, true);
  assert.equal(result.visible, false);
});

test("negative DIPs and minimum visible area are preserved without scale multiplication", () => {
  const native = {x:-2560,y:-120,width:2560,height:1440};
  const areas = [{bounds:native,scaleFactor:1.5}];
  for (const [bounds, visible] of [
    [{left:-200,top:0,right:-100,bottom:100},true],
    [{left:-64,top:0,right:400,bottom:100},true],
    [{left:-63,top:0,right:400,bottom:100},false],
    [{left:-20,top:0,right:-10,bottom:10},true]
  ]) {
    assert.equal(petCapability({ready:true,modelScreenBounds:bounds}, {}, 21000, areas, native, true).visible, visible);
  }
});

test("hidden, missing displays and malformed geometry never report ready", () => {
  assert.equal(petCapability(inspector, {}, 21000, displays, secondDisplay, false).state, "hidden");
  assert.equal(petCapability(inspector, {}, 21000, [], secondDisplay, true).state, "unknown");
  for (const frame of [null, {}, {...secondDisplay,width:0}, {...secondDisplay,x:NaN}, {...secondDisplay,y:null}]) {
    assert.equal(petCapability(inspector, {}, 21000, displays, frame, true).visible, false);
  }
  for (const bounds of [null, {}, {left:0,top:0,right:0,bottom:1}, {left:NaN,top:0,right:1,bottom:1}]) {
    assert.equal(petCapability({ready:true,modelScreenBounds:bounds}, {}, 21000, displays, secondDisplay, true).state, "unknown");
  }
});

test("production status observation reads current native geometry without moving or saving", () => {
  let frame = secondDisplay;
  let visible = true;
  const transform = Object.freeze({revision:3,anchor:Object.freeze({x:3047.24,y:2638.69}),zoomScale:1.8308504694065357});
  const ctx = { latestPetCapabilityObservedAt:10000, latestPetCapabilityInspector:inspector,
    petTransformState:transform, localPresentation:{}, modelRequestedAt:0,
    Date:{now:()=>10001}, getAllDisplays:()=>displays, petCapability, readNativeContentBounds,
    mainWindow:{isDestroyed:()=>false,getContentBounds:()=>frame,isVisible:()=>visible,isMinimized:()=>false,
      setBounds:()=>assert.fail("status moved native window")},
    saveCurrentState:()=>assert.fail("status saved state"),
    ensurePetTransformState:()=>assert.fail("status changed transform") };
  const observe = vm.runInNewContext(functions.get("isPetNativeWindowVisible") + "\n" + functions.get("observePetCapability") + "\nobservePetCapability", ctx);
  assert.equal(observe().state, "ready");
  frame = firstDisplay;
  assert.equal(observe().state, "offscreen");
  visible = false;
  assert.equal(observe().state, "hidden");
  ctx.latestPetCapabilityObservedAt = 0;
  assert.equal(observe().visible, false);
  ctx.latestPetCapabilityObservedAt = 10000;
  ctx.latestPetCapabilityInspector = {...inspector,transformRevision:2};
  assert.equal(observe().visible, false);
  assert.equal(ctx.petTransformState, transform);
});
test("presentation push updates bootstrap before renderer readiness, without a second source", async () => {
  const sent = [];
  const ctx = { localPresentation:null, modelRequestedAt:0, repoRoot:"fixture", path, Date,
    normalizePresentation:(_root, value) => value && {modelUrl:value.modelPath},
    broadcast:(...args) => sent.push(args) };
  const invoke = vm.runInNewContext(functions.get("handleControlAction") + "\nhandleControlAction", ctx);
  const payload = {presentation:{modelPath:"synthetic.model3.json"}};
  assert.equal((await invoke("set-presentation", payload)).ok, true);
  await invoke("set-presentation", payload);
  assert.equal(sent.length, 1);
  assert.equal(ctx.localPresentation.modelUrl, "synthetic.model3.json");
  assert.equal((await invoke("set-presentation", {})).ok, false);
});
test("Electron has one BrowserWindow and no non-pet startup/IPC/owner fallback", () => {
  assert.equal((source.match(/new BrowserWindow\(/g) || []).length, 1);
  assert.doesNotMatch(source, /23568|launcherControlRequest|work-panel|briefing|readerWindow|new Tray|Notification|createCoreClient|createMailBriefingService/i);
  assert.doesNotMatch(source, /KURO_DESKTOP_OWNER\s*===/);
  assert.doesNotMatch(functions.get("registerIpc"), /reader-|briefing-|work-panel-|schedule-/);
  assert.doesNotMatch(fs.readFileSync(path.join(__dirname, "../pet-electron/vite.renderer.config.ts"), "utf8"), /workPanel|work-panel/);
});
test("context menu affects only pet, with no app quit, business, or conversation commands", () => {
  const menuSource = fs.readFileSync(path.join(__dirname, "../pet-electron/src/main-process/menus.js"), "utf8");
  const module = {exports:{}};
  vm.runInNewContext(menuSource, {module, require:() => ({Menu:{buildFromTemplate:x=>x}})});
  const calls=[];
  const actions = Object.fromEntries(["interruptOutput","toggleIgnoreMouse","toggleGameMode","moveNextDisplay","resetPosition","reloadFrontend","hidePet"].map(k=>[k,()=>calls.push(k)]));
  const menu=module.exports.createPetContextMenu({},actions);
  for(const item of menu) if(item.click) item.click();
  assert.deepEqual(calls,Object.keys(actions));
});
async function fixture(t, overrides={}) {
  const actions=[];
  const server=startControlServer({host:"127.0.0.1",port:0,
    readRendererStatus:async()=>({available:true,wsConnected:false}),
    getShellStatus:()=>({service:"kuro-pet-control",protocolVersion:1,instanceId:"fixture"}),
    handleControlAction:async(action)=>{actions.push(action);return {ok:true};},
    applyRendererBackendConfig:async()=>({ok:false,error:"renderer-unavailable"}),
    log:()=>{}, ...overrides});
  await once(server,"listening");
  t.after(()=>new Promise(resolve=>{server.close(resolve);server.closeAllConnections();}));
  const url="http://127.0.0.1:"+server.address().port;
  return {actions, request:async(route,payload)=>{
    const response=await fetch(url+route,payload===undefined?{}:{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});
    return {status:response.status,body:await response.json()};
  }};
}
test("actual loopback status remains responsive when renderer hangs", async t=>{
  const {request}=await fixture(t,{readRendererStatus:()=>new Promise(()=>{})});
  const result=await request("/status");
  assert.equal(result.status,200);
  assert.equal(result.body.renderer.available,false);
  assert.equal("workPanel" in result.body,false);
});
test("deleted routes have no consumers or fallback", async t=>{
  const {request,actions}=await fixture(t);
  for(const route of ["/briefing","/briefing/mail/status","/mail","/work-panel","/v1/runtime","/v1/schedule/view"]){
    assert.equal((await request(route)).status,404,route);
    assert.equal((await request(route,{})).status,404,route);
  }
  assert.deepEqual(actions,[]);
});
test("conversation/business actions are rejected before dispatch", async t=>{
  const {request,actions}=await fixture(t);
  for(const action of ["send-text","interrupt","set-briefing-visible","toggle-browser","refresh-mail","restart-launcher","add-briefing-memory-candidate"]){
    assert.equal((await request("/command",{action})).status,400,action);
  }
  assert.deepEqual(actions,[]);
});
test("pet commands preserve instance fencing and explicit renderer failure", async t=>{
  const {request,actions}=await fixture(t);
  assert.equal((await request("/command",{action:"set-outfit",expectedInstanceId:"stale"})).body.ok,false);
  assert.deepEqual(actions,[]);
  assert.equal((await request("/command",{action:"set-outfit",expectedInstanceId:"fixture"})).body.ok,true);
  assert.deepEqual(actions,["set-outfit"]);
  assert.equal((await request("/backend-config",{baseUrl:"http://localhost",wsUrl:"ws://localhost"})).body.ok,false);
});
test("remote bind is forbidden",()=>{
  assert.throws(()=>startControlServer({host:"0.0.0.0",port:0}),/loopback/);
});
