// Isolated Electron smoke: production renderer/helpers, no private data or providers.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { once } = require("node:events");
const { app, BrowserWindow, screen } = require("electron");
const { startControlServer } = require("../pet-electron/src/main-process/control-server");
const { probeWindow, revealWindow } = require("../pet-electron/src/main-process/work-panel-window");
const root = path.resolve(__dirname, "..");
const evidence = path.join(root, "launcher_logs", "work-panel-validation");
fs.mkdirSync(evidence, { recursive: true });
app.setPath("userData", fs.mkdtempSync(path.join(evidence, "profile-")));
app.disableHardwareAcceleration();
let window, server;
const checks = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const timeout = setTimeout(() => { console.error("Work Panel smoke timed out"); app.exit(1); }, 45000);

function clamp(bounds) {
  const area = screen.getDisplayNearestPoint({ x: bounds.x, y: bounds.y }).workArea;
  const width = Math.min(bounds.width, area.width), height = Math.min(bounds.height, area.height);
  return { width, height, x: Math.max(area.x, Math.min(bounds.x, area.x + area.width - width)),
    y: Math.max(area.y, Math.min(bounds.y, area.y + area.height - height)) };
}
function reveal() { return revealWindow(window, { app, screen, clampBounds: clamp }); }
async function create() {
  window = new BrowserWindow({ width: 1100, height: 760, show: false, frame: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  window.on("close", (event) => { event.preventDefault(); window.hide(); });
  await window.loadFile(path.join(root, "pet-electron", "renderer-dist", "work-panel.html"));
}
async function ready() {
  for (let attempt = 0; attempt < 30; attempt++) {
    const state = await probeWindow(window, screen);
    if (state.visible && !state.minimized && state.displayMatch && state.rendererReady && state.responsive) return state;
    await delay(100);
  }
  throw new Error("Work Panel did not reach ready");
}

app.whenReady().then(async () => {
  await create(); reveal(); await ready(); checks.push("cold window and built renderer ready");
  window.close(); assert.equal(window.isDestroyed(), false); assert.equal(window.isVisible(), false);
  reveal(); await ready(); checks.push("close-hide-reopen");
  window.minimize(); await delay(120); assert.equal(window.isMinimized(), true);
  reveal(); await ready(); checks.push("minimize-restore");
  window.setBounds({ x: 50000, y: 50000, width: 1100, height: 760 });
  reveal(); await ready(); checks.push("offscreen-clamp");
  for (let i = 0; i < 10; i++) reveal();
  assert.equal(BrowserWindow.getAllWindows().length, 1); checks.push("repeated reveal retains one window");
  await window.webContents.executeJavaScript("document.querySelector('[data-mode=today]').click()");
  await delay(200);
  assert.equal(await window.webContents.executeJavaScript("Boolean(document.querySelector('[data-mode=today].is-active'))"), true);
  checks.push("offline sources do not block navigation");
  server = startControlServer({ host: "127.0.0.1", port: 0,
    readRendererStatus: () => new Promise(() => {}), readWorkPanelStatus: () => probeWindow(window, screen),
    getShellStatus: () => ({ service: "kuro-pet-control", protocolVersion: 1, pid: process.pid,
      instanceId: "isolated-smoke", sourceRoot: root }),
    isReaderVisible: () => false, isBriefingVisible: () => window.isVisible() && !window.isMinimized(),
    handleControlAction: async () => { reveal(); return { ok: true }; }, log: () => {} });
  await once(server, "listening");
  const status = await (await fetch(`http://127.0.0.1:${server.address().port}/status`, { signal: AbortSignal.timeout(2000) })).json();
  assert.equal(status.renderer.available, false); assert.equal(status.workPanel.rendererReady, true);
  checks.push("HTTP ready independent of hung Pet renderer");
  fs.writeFileSync(path.join(evidence, "work-panel.png"), (await window.webContents.capturePage()).toPNG());
  window.webContents.forcefullyCrashRenderer(); await delay(200);
  assert.equal((await probeWindow(window, screen)).rendererReady, false);
  checks.push("crashed renderer fails readiness");
  window.destroy(); await create(); reveal(); await ready(); checks.push("destroyed window recreated");
  fs.writeFileSync(path.join(evidence, "result.json"), JSON.stringify({ ok: true, checkedAt: new Date().toISOString(),
    scope: "isolated Electron window and production renderer/helpers; not live Launcher/VBS acceptance", checks }, null, 2));
  console.log(JSON.stringify({ ok: true, checks, evidence }));
  server.closeAllConnections(); await new Promise((resolve) => server.close(resolve));
  window.destroy(); clearTimeout(timeout); app.exit(0);
}).catch((error) => { console.error(error); clearTimeout(timeout); app.exit(1); });
app.on("window-all-closed", () => {});
