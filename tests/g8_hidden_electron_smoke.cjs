// Hidden Electron process smoke: real renderer/preload/HTTP, no model or media input.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { app, BrowserWindow } = require("electron");
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "kuro-g8-electron-"));
app.setPath("userData", profile);
app.disableHardwareAcceleration();
// Keep the production window hidden throughout this isolated acceptance fixture.
BrowserWindow.prototype.show = function () {};
BrowserWindow.prototype.showInactive = function () {};
BrowserWindow.prototype.focus = function () {};
BrowserWindow.prototype.moveTop = function () {};
Object.assign(process.env, { KURO_DESKTOP_OWNER: "qt", KURO_PET_CONTROL_PORT: "0",
  KURO_BACKEND_BASE_URL: "http://127.0.0.1:1", KURO_BACKEND_WS_URL: "ws://127.0.0.1:1/client-ws" });
for (const key of ["KURO_PRESENTATION","KURO_CORE_TOKEN","KURO_LAUNCHER_CONTROL_TOKEN",
                   "KURO_MAIL_STATUS_FILE","KURO_MAIL_WORK_FILE"]) delete process.env[key];
const control = require("../pet-electron/src/main-process/control-server");
const start = control.startControlServer;
let server;
control.startControlServer = options => (server = start(options));
require("../pet-electron/src/main.js");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const limit = setTimeout(() => { console.error("G8 hidden Electron timed out"); app.exit(1); }, 25000);
async function run() {
  let win;
  for (let i=0;i<100;i++) {
    win=BrowserWindow.getAllWindows()[0];
    if (win && server?.listening && await win.webContents.executeJavaScript("Boolean(window.__kuroPetRendererState)")) break;
    await delay(100);
  }
  assert.equal(BrowserWindow.getAllWindows().length, 1);
  assert.equal(win.isVisible(), false);
  assert.ok(await win.webContents.executeJavaScript("Boolean(window.kuroPetElectron && window.__kuroPetCaptureInput)"));
  assert.equal(await win.webContents.executeJavaScript("typeof window.__kuroPetSendTextInput"), "undefined");
  const url="http://127.0.0.1:"+server.address().port;
  const status=await (await fetch(url+"/status")).json();
  assert.equal(status.service, "kuro-pet-control");
  assert.equal(status.renderer.wsConnected, false);
  assert.equal(status.renderer.available, true);
  assert.equal(status.capabilities.pet.state, "missing");
  assert.equal("workPanel" in status, false);
  for (const route of ["/briefing","/work-panel","/v1/runtime"]) assert.equal((await fetch(url+route)).status,404);
  assert.equal((await fetch(url+"/command",{method:"POST",body:JSON.stringify({action:"send-text",text:"synthetic"})})).status,400);
  console.log(JSON.stringify({contract:"kuro.g8.hidden-electron.v1",ok:true,windows:1,
    visible:false,renderer:true,petLocalStatus:"missing",legacyRoutes:404,conversationAction:400,
    limitations:["no model","no device input","no tray","not desktop acceptance"]}));
  clearTimeout(limit);
  server.close();
  win.destroy();
  app.exit(0);
}
app.whenReady().then(run).catch(error=>{console.error(error.stack);clearTimeout(limit);app.exit(1);});
