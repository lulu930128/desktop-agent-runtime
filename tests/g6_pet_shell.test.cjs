const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { once } = require("node:events");
const ts = require("../pet-electron/node_modules/typescript");
const { startControlServer } = require("../pet-electron/src/main-process/control-server");
const { petCapability, withTimeout } = require("../pet-electron/src/main-process/pet-status");
const source = fs.readFileSync(path.join(__dirname, "../pet-electron/src/main.js"), "utf8");
const tree = ts.createSourceFile("main.js", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
const functions = new Map(tree.statements.filter(ts.isFunctionDeclaration).map(n => [n.name.text, n.getText(tree)]));

test("pet-local status is independent of Launcher and preserves missing/loading/failed/offscreen", async () => {
  assert.equal(petCapability(null, null, 0, [], () => false).state, "missing");
  assert.equal(petCapability(null, {}, 1, [], () => false).state, "loading");
  assert.equal(petCapability(null, {}, 21000, [], () => false).state, "failed");
  assert.equal(petCapability({ready:true}, {}, 21000, [], () => false).state, "offscreen");
  assert.equal(petCapability({ready:true}, {}, 21000, [], () => true).state, "ready");
  assert.equal(await withTimeout(Promise.reject(Error("fixture")), 20, null), null);
  assert.equal(await withTimeout(new Promise(() => {}), 20, "unavailable"), "unavailable");
});
test("real production probe uses only renderer and never reports a Launcher failure", async () => {
  const ctx = { capabilityRefreshPending:false, localPresentation:{}, modelRequestedAt:0,
    runtimeCapabilities:null, readLive2DInspectorSnapshot:async () => ({ready:true}),
    getAllDisplays:() => [], modelIsVisible:() => true, withTimeout, petCapability, Date };
  await vm.runInNewContext(functions.get("refreshRuntimeCapabilities") + "\nrefreshRuntimeCapabilities()", ctx);
  assert.equal(ctx.runtimeCapabilities.pet.state, "ready");
  assert.equal("launcher" in ctx.runtimeCapabilities, false);
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
