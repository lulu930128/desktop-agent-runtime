const assert = require("node:assert/strict");
const test = require("node:test");
const { once } = require("node:events");
const { readWindowState, probeWindow, revealWindow } = require("../pet-electron/src/main-process/work-panel-window");
const { startControlServer } = require("../pet-electron/src/main-process/control-server");

const screen = { getAllDisplays: () => [{ id: 1, workArea: { x: 0, y: 0, width: 1920, height: 1080 } },
  { id: 2, workArea: { x: 3000, y: 0, width: 1920, height: 1080 } }] };
function fakeWindow() {
  const state = { visible: false, minimized: true, focused: false, destroyed: false,
    bounds: { x: 2200, y: 0, width: 800, height: 600 }, calls: [] };
  return { state, isDestroyed: () => state.destroyed, getBounds: () => ({ ...state.bounds }),
    isVisible: () => state.visible, isMinimized: () => state.minimized, isFocused: () => state.focused,
    restore() { state.calls.push("restore"); state.minimized = false; },
    setBounds(bounds) { state.calls.push("bounds"); state.bounds = bounds; },
    show() { state.calls.push("show"); state.visible = true; },
    moveTop() { state.calls.push("moveTop"); }, focus() { state.calls.push("focus"); state.focused = true; },
    webContents: { isDestroyed: () => false, isLoadingMainFrame: () => false, executeJavaScript: async () => true }
  };
}

test("reveal restores, clamps to a real display, and reads actual state", async () => {
  const window = fakeWindow();
  assert.equal(readWindowState(window, screen).displayMatch, false); // virtual desktop gap
  const result = revealWindow(window, { screen, app: { focus: () => window.state.calls.push("appFocus") },
    platform: "win32", clampBounds: () => ({ x: 30, y: 40, width: 800, height: 600 }) });
  assert.deepEqual(window.state.calls, ["restore", "bounds", "show", "moveTop", "appFocus", "focus"]);
  assert.equal(result.visible, true);
  assert.equal(result.minimized, false);
  assert.equal(result.boundsClamped, true);
  assert.equal(result.displayMatch, true);
  assert.equal((await probeWindow(window, screen)).rendererReady, true);
});

test("visible window cannot pass when renderer loading, crashed, or hung", async () => {
  const window = fakeWindow();
  window.state.visible = true;
  window.webContents.isLoadingMainFrame = () => true;
  assert.equal((await probeWindow(window, screen)).rendererReady, false);
  window.webContents.isLoadingMainFrame = () => false;
  window.webContents.executeJavaScript = () => { throw new Error("destroyed synchronously"); };
  assert.equal((await probeWindow(window, screen)).responsive, false);
  window.webContents.executeJavaScript = async () => { throw new Error("crashed"); };
  assert.equal((await probeWindow(window, screen)).responsive, false);
  window.webContents.executeJavaScript = () => new Promise(() => {});
  assert.equal((await probeWindow(window, screen, 15)).responsive, false);
});

test("missing/destroyed windows and failed show return actual failure", async () => {
  assert.equal(readWindowState(null, screen).exists, false);
  const window = fakeWindow();
  window.state.destroyed = true;
  assert.equal((await probeWindow(window, screen)).exists, false);
  window.state.destroyed = false;
  window.show = () => {};
  assert.equal(revealWindow(window, { screen, app: {}, platform: "linux", clampBounds: (x) => x }).visible, false);
});

test("control status stays bounded with hung Pet renderer and checks instance before reveal", async () => {
  let commands = 0;
  const server = startControlServer({ host: "127.0.0.1", port: 0,
    readRendererStatus: () => new Promise(() => {}),
    readWorkPanelStatus: async () => ({ contractVersion: 1, exists: true, rendererReady: true }),
    getShellStatus: () => ({ service: "kuro-pet-control", instanceId: "owned" }),
    isReaderVisible: () => false, isBriefingVisible: () => true,
    handleControlAction: async () => { commands++; return { ok: true }; }, log: () => {} });
  await once(server, "listening");
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const status = await (await fetch(`${base}/status`, { signal: AbortSignal.timeout(1500) })).json();
    assert.equal(status.renderer.available, false);
    assert.equal(status.workPanel.rendererReady, true);
    const mismatch = await (await fetch(`${base}/command`, { method: "POST",
      body: JSON.stringify({ action: "set-briefing-visible", expectedInstanceId: "wrong" }) })).json();
    assert.equal(mismatch.error, "WP_PET_IDENTITY_MISMATCH");
    assert.equal(commands, 0);
    const response = await (await fetch(`${base}/command`, { method: "POST",
      body: JSON.stringify({ action: "set-briefing-visible", expectedInstanceId: "owned" }),
      signal: AbortSignal.timeout(1500) })).json();
    assert.equal(response.ok, true);
    assert.equal(response.workPanel.exists, true);
    assert.equal(commands, 1);
  } finally { server.closeAllConnections(); await new Promise((resolve) => server.close(resolve)); }
});
