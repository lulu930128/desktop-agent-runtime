// Electron child fixture for the real Launcher controller. All state is in the test cwd.
const { app, BrowserWindow, screen } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { startControlServer } = require("../pet-electron/src/main-process/control-server");
const { probeWindow, revealWindow } = require("../pet-electron/src/main-process/work-panel-window");
const root = path.resolve(__dirname, "..");
app.setPath("userData", path.join(process.cwd(), "profile"));
app.disableHardwareAcceleration();
let window;
function reveal() {
  return revealWindow(window, { app, screen, clampBounds: (bounds) => {
    const area = screen.getPrimaryDisplay().workArea;
    return { x: area.x + 40, y: area.y + 40, width: Math.min(bounds.width, area.width - 80),
      height: Math.min(bounds.height, area.height - 80) };
  } });
}
app.whenReady().then(async () => {
  window = new BrowserWindow({ show: false, width: 1000, height: 720,
    webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
  window.on("close", (event) => { event.preventDefault(); window.hide(); });
  await window.loadFile(path.join(root, "pet-electron", "renderer-dist", "work-panel.html"));
  const marker = path.join(process.cwd(), "first-child-crashed");
  if (!fs.existsSync(marker)) {
    fs.writeFileSync(marker, "test renderer crash, replacement must recover");
    window.webContents.forcefullyCrashRenderer();
  }
  startControlServer({ host: "127.0.0.1", port: Number(process.env.KURO_PET_CONTROL_PORT),
    readRendererStatus: async () => ({}), readWorkPanelStatus: () => probeWindow(window, screen),
    getShellStatus: () => ({ service: "kuro-pet-control", protocolVersion: 1, pid: process.pid,
      instanceId: process.env.KURO_PET_INSTANCE_ID, sourceRoot: root }),
    isReaderVisible: () => false, isBriefingVisible: () => window.isVisible() && !window.isMinimized(),
    handleControlAction: async (_action, payload) => {
      if (payload.enabled) reveal(); else window.hide();
      return { ok: true };
    }, log: (...args) => console.log(...args) });
}).catch((error) => { console.error(error); app.exit(1); });
app.on("window-all-closed", () => {});
