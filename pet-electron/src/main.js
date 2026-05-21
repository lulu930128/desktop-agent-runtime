const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const {
  app,
  BrowserWindow,
  Tray,
  desktopCapturer,
  ipcMain,
  nativeImage,
  screen,
  session
} = require("electron");

const { cloneDefaultState, loadState, mergeState, saveState } = require("./state");
const {
  buildReaderVisibleInputText,
  normalizeReaderAttachments
} = require("./main-process/reader-attachments");
const { startControlServer: createControlServer } = require("./main-process/control-server");
const { createPetContextMenu, createTrayMenu } = require("./main-process/menus");
const { createPetLogger } = require("./main-process/pet-logger");

const APP_NAME = "Kuro Pet Electron";
const APP_USER_MODEL_ID = "kuro.desktop-agent.pet";
const TEMP_MAX_RENDER_PERFORMANCE = true;
const CONTROL_HOST = process.env.KURO_PET_CONTROL_HOST || "127.0.0.1";
const CONTROL_PORT = Number(process.env.KURO_PET_CONTROL_PORT || "23567");

if (TEMP_MAX_RENDER_PERFORMANCE) {
  app.commandLine.appendSwitch("disable-frame-rate-limit");
  app.commandLine.appendSwitch("disable-background-timer-throttling");
  app.commandLine.appendSwitch("disable-renderer-backgrounding");
  app.commandLine.appendSwitch("disable-backgrounding-occluded-windows");
}

const projectRoot = path.resolve(__dirname, "..");
const rendererEntry = path.join(projectRoot, "renderer-dist", "index.html");
const iconPath = path.join(projectRoot, "src", "assets", "favicon.ico");
const readerEntry = path.join(__dirname, "reader-window.html");
const readerPreloadPath = path.join(__dirname, "reader-preload.js");
const MIN_PET_ZOOM_SCALE = 0.2;
const MAX_PET_ZOOM_SCALE = 8;
const MIN_PET_WINDOW_WIDTH = 280;
const MIN_PET_WINDOW_HEIGHT = 420;
const MIN_READER_WINDOW_WIDTH = 360;
const MIN_READER_WINDOW_HEIGHT = 236;

let mainWindow = null;
let readerWindow = null;
let tray = null;
let appState = cloneDefaultState();
let statePath = "";
let hoveredComponents = new Map();
let activeWindowDrag = null;
let controlServer = null;
const taskbarHiddenNativeHandles = new Set();
let latestFrontendState = {
  wsConnected: false,
  aiState: "idle",
  latestAssistantText: "",
  latestUserText: "",
  wsUrl: process.env.KURO_BACKEND_WS_URL || "",
  baseUrl: process.env.KURO_BACKEND_BASE_URL || "",
  confName: "",
  confUid: "",
  currentHistoryUid: "",
  currentHistoryTitle: "",
  currentOutfitId: "normal",
  currentOutfitParameterId: "Param10",
  currentOutfitParameterIndex: null,
  currentOutfitValue: 0,
  currentExpressionId: "neutral",
  currentExpressionLabel: "一般",
  live2dInspectorOverlayEnabled: false
};

const petLog = createPetLogger(app);

app.setName(APP_NAME);
if (process.platform === "win32") {
  app.setAppUserModelId(APP_USER_MODEL_ID);
}

function normalizePetZoomScale(value) {
  const zoomScale = Number(value);
  if (!Number.isFinite(zoomScale)) {
    return 1;
  }
  return Math.max(MIN_PET_ZOOM_SCALE, Math.min(MAX_PET_ZOOM_SCALE, zoomScale));
}

function saveCurrentState() {
  if (!statePath) {
    return;
  }
  saveState(statePath, appState);
}

function setBoundsForCurrentMode(bounds) {
  if (appState.mode === "pet") {
    saveCurrentState();
    return;
  }

  appState.boundsByMode[appState.mode] = {
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height
  };
  saveCurrentState();
}

function getWindowBoundsForMode(mode) {
  return appState.boundsByMode[mode] || appState.boundsByMode.pet;
}

function getReaderBounds() {
  return appState.readerBounds || cloneDefaultState().readerBounds;
}

function setReaderBounds(bounds) {
  appState.readerBounds = {
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height
  };
  saveCurrentState();
}

function resetPetBoundsToDefault() {
  const defaults = cloneDefaultState().boundsByMode.pet;
  const primaryArea = screen.getPrimaryDisplay().workArea;

  appState.boundsByMode.pet = {
    x: primaryArea.x + defaults.x,
    y: primaryArea.y + defaults.y,
    width: defaults.width,
    height: defaults.height
  };
  appState.petAnchor = getDefaultPetAnchor();
}

function getAllDisplays() {
  return screen.getAllDisplays().sort((a, b) => a.bounds.x - b.bounds.x || a.bounds.y - b.bounds.y);
}

function getVirtualWorkAreaBounds() {
  const displays = getAllDisplays();
  if (!displays.length) {
    return { x: 0, y: 0, width: 1280, height: 720 };
  }

  const areas = displays.map((display) => display.workArea);
  const left = Math.min(...areas.map((area) => area.x));
  const top = Math.min(...areas.map((area) => area.y));
  const right = Math.max(...areas.map((area) => area.x + area.width));
  const bottom = Math.max(...areas.map((area) => area.y + area.height));

  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top)
  };
}

function getPetHostBounds() {
  return getVirtualWorkAreaBounds();
}

function clampPointToVirtualDesktop(point) {
  const area = getVirtualWorkAreaBounds();
  const fallback = {
    x: area.x + area.width / 2,
    y: area.y + area.height / 2
  };
  const x = Number.isFinite(Number(point?.x)) ? Number(point.x) : fallback.x;
  const y = Number.isFinite(Number(point?.y)) ? Number(point.y) : fallback.y;

  return {
    x: Math.round(Math.min(Math.max(x, area.x), area.x + area.width)),
    y: Math.round(Math.min(Math.max(y, area.y), area.y + area.height))
  };
}

function getDefaultPetAnchor() {
  const defaults = cloneDefaultState().boundsByMode.pet;
  const primaryArea = screen.getPrimaryDisplay().workArea;
  return clampPointToVirtualDesktop({
    x: primaryArea.x + defaults.x + defaults.width / 2,
    y: primaryArea.y + defaults.y + defaults.height / 2
  });
}

function ensurePetAnchor() {
  const anchor = clampPointToVirtualDesktop(appState.petAnchor || getDefaultPetAnchor());
  appState.petAnchor = anchor;
  return anchor;
}

function buildPetHostStatePayload(type = "pet-host-set") {
  return {
    type,
    petHostBounds: getPetHostBounds(),
    petAnchor: ensurePetAnchor()
  };
}

function broadcastPetHostState(type = "pet-host-set") {
  broadcast("pet-command", buildPetHostStatePayload(type));
}

function setPetAnchor(x, y, options = {}) {
  appState.petAnchor = clampPointToVirtualDesktop({ x, y });
  saveCurrentState();

  if (options.broadcast !== false) {
    broadcastPetHostState("pet-anchor-set");
  }

  return appState.petAnchor;
}

function findDisplayForBounds(bounds) {
  const point = {
    x: bounds.x + Math.round(bounds.width / 2),
    y: bounds.y + Math.round(bounds.height / 2)
  };
  return screen.getDisplayNearestPoint(point);
}

function clampBoundsToDisplay(bounds, display) {
  const area = display.workArea;
  const width = Math.min(bounds.width, area.width);
  const height = Math.min(bounds.height, area.height);

  return {
    x: Math.min(Math.max(bounds.x, area.x), area.x + area.width - width),
    y: Math.min(Math.max(bounds.y, area.y), area.y + area.height - height),
    width,
    height
  };
}

function clampBoundsToVirtualDesktopWithOverflow(bounds, visibleMargin = 120) {
  const area = getVirtualWorkAreaBounds();
  const width = Math.max(1, Math.round(bounds.width));
  const height = Math.max(1, Math.round(bounds.height));
  const minVisibleX = Math.max(64, Math.min(visibleMargin, width));
  const minVisibleY = Math.max(64, Math.min(visibleMargin, height));

  return {
    x: Math.min(
      Math.max(bounds.x, area.x - width + minVisibleX),
      area.x + area.width - minVisibleX
    ),
    y: Math.min(
      Math.max(bounds.y, area.y - height + minVisibleY),
      area.y + area.height - minVisibleY
    ),
    width,
    height
  };
}

function clampReaderBounds(bounds) {
  return clampBoundsToVirtualDesktopWithOverflow(
    {
      ...bounds,
      width: Math.max(MIN_READER_WINDOW_WIDTH, Number(bounds.width) || MIN_READER_WINDOW_WIDTH),
      height: Math.max(MIN_READER_WINDOW_HEIGHT, Number(bounds.height) || MIN_READER_WINDOW_HEIGHT)
    },
    160
  );
}

function resolveTargetBoundsForMode(mode) {
  const requestedBounds = getWindowBoundsForMode(mode);
  if (mode === "pet") {
    ensurePetAnchor();
    return getPetHostBounds();
  }

  return clampBoundsToDisplay(requestedBounds, findDisplayForBounds(requestedBounds));
}

function applyIgnoreMouseState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const shouldIgnore =
    appState.mode === "pet" &&
    (
      appState.petGameMode ||
      (
        appState.forceIgnoreMouse &&
        !Array.from(hoveredComponents.values()).some(Boolean)
      )
    );

  mainWindow.setIgnoreMouseEvents(shouldIgnore, { forward: true });
}

function applyPetFocusPolicy() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  mainWindow.setFocusable(appState.mode !== "pet");
}

function applyTaskbarPolicy() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.setSkipTaskbar(true);
    hideWindowFromTaskbarNative(mainWindow);
  }
  if (readerWindow && !readerWindow.isDestroyed()) {
    readerWindow.setSkipTaskbar(true);
    hideWindowFromTaskbarNative(readerWindow);
  }
}

function getNativeWindowHandleId(targetWindow) {
  const handleBuffer = targetWindow.getNativeWindowHandle();
  if (!Buffer.isBuffer(handleBuffer) || handleBuffer.length < 4) {
    return "";
  }

  if (handleBuffer.length >= 8) {
    return handleBuffer.readBigUInt64LE(0).toString();
  }

  return String(handleBuffer.readUInt32LE(0));
}

function hideWindowFromTaskbarNative(targetWindow) {
  if (process.platform !== "win32" || !targetWindow || targetWindow.isDestroyed()) {
    return;
  }

  const handleId = getNativeWindowHandleId(targetWindow);
  if (!handleId || taskbarHiddenNativeHandles.has(handleId)) {
    return;
  }
  taskbarHiddenNativeHandles.add(handleId);

  const script = `
Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class KuroWindowStyles {
  private const int GWL_EXSTYLE = -20;
  private const long WS_EX_APPWINDOW = 0x00040000L;
  private const long WS_EX_TOOLWINDOW = 0x00000080L;
  private const UInt32 SWP_NOSIZE = 0x0001;
  private const UInt32 SWP_NOMOVE = 0x0002;
  private const UInt32 SWP_NOZORDER = 0x0004;
  private const UInt32 SWP_NOACTIVATE = 0x0010;
  private const UInt32 SWP_FRAMECHANGED = 0x0020;

  [DllImport("user32.dll", EntryPoint = "GetWindowLong", SetLastError = true)]
  private static extern int GetWindowLong32(IntPtr hWnd, int nIndex);

  [DllImport("user32.dll", EntryPoint = "SetWindowLong", SetLastError = true)]
  private static extern int SetWindowLong32(IntPtr hWnd, int nIndex, int dwNewLong);

  [DllImport("user32.dll", EntryPoint = "GetWindowLongPtr", SetLastError = true)]
  private static extern IntPtr GetWindowLongPtr64(IntPtr hWnd, int nIndex);

  [DllImport("user32.dll", EntryPoint = "SetWindowLongPtr", SetLastError = true)]
  private static extern IntPtr SetWindowLongPtr64(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

  [DllImport("user32.dll", SetLastError = true)]
  private static extern bool SetWindowPos(
    IntPtr hWnd,
    IntPtr hWndInsertAfter,
    int X,
    int Y,
    int cx,
    int cy,
    UInt32 uFlags
  );

  public static void HideFromTaskbar(IntPtr hWnd) {
    long exStyle = IntPtr.Size == 8
      ? GetWindowLongPtr64(hWnd, GWL_EXSTYLE).ToInt64()
      : GetWindowLong32(hWnd, GWL_EXSTYLE);
    exStyle = (exStyle & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW;
    if (IntPtr.Size == 8) {
      SetWindowLongPtr64(hWnd, GWL_EXSTYLE, new IntPtr(exStyle));
    } else {
      SetWindowLong32(hWnd, GWL_EXSTYLE, unchecked((int)exStyle));
    }
    SetWindowPos(
      hWnd,
      IntPtr.Zero,
      0,
      0,
      0,
      0,
      SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
    );
  }
}
"@
[KuroWindowStyles]::HideFromTaskbar([IntPtr]::new([Int64]$env:KURO_WINDOW_HANDLE))
`;

  const child = spawn(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
    {
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: {
        ...process.env,
        KURO_WINDOW_HANDLE: handleId
      }
    }
  );
  child.unref();
}

function scheduleTaskbarPolicyRefresh() {
  applyTaskbarPolicy();
  setTimeout(applyTaskbarPolicy, 0);
  setTimeout(applyTaskbarPolicy, 250);
}

function setPetGameMode(enabled) {
  appState.petGameMode = Boolean(enabled);
  saveCurrentState();
  applyPetFocusPolicy();
  applyIgnoreMouseState();
  updateTrayMenu();
  return appState.petGameMode;
}

function togglePetGameMode() {
  return setPetGameMode(!appState.petGameMode);
}

function showPetWindow({ focus = true } = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  if (appState.mode === "pet") {
    applyPetFocusPolicy();
    scheduleTaskbarPolicyRefresh();
    mainWindow.showInactive();
    return;
  }

  applyPetFocusPolicy();
  scheduleTaskbarPolicyRefresh();
  mainWindow.show();
  if (focus) {
    mainWindow.focus();
  }
}

function setPetWindowZoom(zoomScale) {
  return setPetModelZoom(zoomScale);
}

function setPetModelZoom(zoomScale, options = {}) {
  appState.petZoomScale = normalizePetZoomScale(zoomScale);
  saveCurrentState();

  if (options.broadcast !== false) {
    broadcast("pet-command", {
      type: "pet-zoom-set",
      zoomScale: appState.petZoomScale
    });
  }

  return true;
}

function adjustPetWindowScale(scaleRatio) {
  const ratio = Number.isFinite(scaleRatio) ? Number(scaleRatio) : 1;
  if (ratio <= 0) {
    return false;
  }

  return setPetModelZoom(normalizePetZoomScale(appState.petZoomScale) * ratio);
}

function getReaderStatePayload() {
  return {
    ok: true,
    aiState: latestFrontendState.aiState || "idle",
    wsConnected: Boolean(latestFrontendState.wsConnected),
    latestAssistantText: latestFrontendState.latestAssistantText || "",
    latestUserText: latestFrontendState.latestUserText || "",
    wsUrl: latestFrontendState.wsUrl || "",
    baseUrl: latestFrontendState.baseUrl || "",
    confName: latestFrontendState.confName || "",
    confUid: latestFrontendState.confUid || "",
    currentHistoryUid: latestFrontendState.currentHistoryUid || "",
    currentHistoryTitle: latestFrontendState.currentHistoryTitle || "",
    readerVisible: Boolean(readerWindow && !readerWindow.isDestroyed() && readerWindow.isVisible())
  };
}

function broadcastReaderState() {
  if (!readerWindow || readerWindow.isDestroyed()) {
    return;
  }
  try {
    readerWindow.webContents.send("reader-state", getReaderStatePayload());
  } catch (error) {
    petLog("reader-state-broadcast-failed", error);
  }
}

function updateFrontendState(patch = {}) {
  latestFrontendState = {
    ...latestFrontendState,
    ...(patch || {})
  };
  broadcastReaderState();
}

function broadcast(channel, payload) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send(channel, payload);
}

async function executeRenderer(code) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return null;
  }
  try {
    return await mainWindow.webContents.executeJavaScript(code, true);
  } catch (error) {
    petLog("execute-renderer-failed", error);
    return null;
  }
}

async function readRendererStatus() {
  const rendererStatus =
    (await executeRenderer(`(() => {
      if (window.__kuroPetRendererState) {
        return {
          mode: "custom-renderer",
          ...window.__kuroPetRendererState
        };
      }

      const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
      const parseStored = (key) => {
        const raw = window.localStorage.getItem(key);
        if (!raw) return "";
        try {
          return String(JSON.parse(raw) || "");
        } catch {
          return String(raw || "");
        }
      };

      const visibleTextNodes = Array.from(document.querySelectorAll("body *"))
        .map((node) => normalize(node.innerText || node.textContent || ""))
        .filter(Boolean);

      const buttonTexts = Array.from(document.querySelectorAll("button"))
        .map((button) => normalize(button.innerText || button.textContent || ""))
        .filter(Boolean)
        .slice(0, 24);

      const knownStates = new Set([
        "idle",
        "thinking/speaking",
        "interrupted",
        "loading",
        "listening",
        "waiting",
        "空闲",
        "空閒",
        "思考/说话中",
        "思考/說話中",
        "已打断",
        "已打斷",
        "加载中",
        "載入中",
        "聆听中",
        "聆聽中",
        "等待中"
      ]);

      const knownWs = new Set([
        "Connected",
        "Connecting",
        "Click to Reconnect",
        "已连接",
        "已連接",
        "连接中",
        "連線中",
        "点击重新连接",
        "點擊重新連線"
      ]);

      const aiState = visibleTextNodes.find((text) => knownStates.has(text)) || "";
      const wsBadge = visibleTextNodes.find((text) => knownWs.has(text)) || "";

      return {
        href: location.href,
        baseUrl: parseStored("baseUrl"),
        wsUrl: parseStored("wsUrl"),
        aiState,
        wsBadge,
        buttonTexts
      };
    })();`)) || {};

  return {
    ...rendererStatus,
    petGameMode: appState.petGameMode
  };
}

async function readLive2DInspectorSnapshot() {
  return (
    (await executeRenderer(`(() => {
      if (window.__kuroLive2DInspector && typeof window.__kuroLive2DInspector.getSnapshot === "function") {
        return window.__kuroLive2DInspector.getSnapshot();
      }
      return null;
    })();`)) || null
  );
}

async function applyRendererBackendConfig(baseUrl, wsUrl, reload = true) {
  const payload = await executeRenderer(`((baseUrlValue, wsUrlValue, shouldReconnect) => {
    if (typeof window.__kuroPetApplyBackendConfig === "function") {
      return window.__kuroPetApplyBackendConfig(baseUrlValue, wsUrlValue, shouldReconnect);
    }

    const writeValue = (key, value) => {
      if (!value) return;
      window.localStorage.setItem(key, JSON.stringify(String(value)));
    };
    writeValue("baseUrl", baseUrlValue);
    writeValue("wsUrl", wsUrlValue);
    return {
      baseUrl: baseUrlValue || "",
      wsUrl: wsUrlValue || ""
    };
  })(${JSON.stringify(baseUrl || "")}, ${JSON.stringify(wsUrl || "")}, ${JSON.stringify(Boolean(reload))});`);

  updateFrontendState({
    baseUrl: baseUrl || latestFrontendState.baseUrl,
    wsUrl: wsUrl || latestFrontendState.wsUrl
  });
  return payload || {};
}

async function sendTextToFrontend(text, attachments = []) {
  const normalized = String(text || "").trim();
  const normalizedAttachments = normalizeReaderAttachments(attachments);
  const visibleText = buildReaderVisibleInputText(normalized, normalizedAttachments.attachments);
  if (!normalized && !normalizedAttachments.attachments.length) {
    return { ok: false, error: "empty-text" };
  }
  if (normalizedAttachments.errors.length && !normalizedAttachments.attachments.length) {
    return {
      ok: false,
      error: normalizedAttachments.errors.join("; ")
    };
  }

  const result =
    (await executeRenderer(`((rawText, rawAttachments) => {
      const text = String(rawText || "").trim();
      const attachments = Array.isArray(rawAttachments) ? rawAttachments : [];
      if (!text && attachments.length === 0) {
        return { ok: false, error: "empty-text" };
      }

      if (typeof window.__kuroPetSendTextInput === "function") {
        return window.__kuroPetSendTextInput(text, attachments);
      }

      return { ok: false, error: "frontend-bridge-missing" };
    })(${JSON.stringify(normalized)}, ${JSON.stringify(normalizedAttachments.attachments)});`)) || { ok: false, error: "renderer-unavailable" };

  if (result.ok) {
    updateFrontendState({
      latestUserText: visibleText || "[附件]",
      aiState: "thinking"
    });
  }

  if (normalizedAttachments.errors.length) {
    result.warnings = normalizedAttachments.errors;
  }
  return result;
}

function setReaderVisible(visible) {
  appState.readerVisible = Boolean(visible);
  if (!readerWindow || readerWindow.isDestroyed()) {
    if (appState.readerVisible) {
      createReaderWindow();
    }
  } else if (appState.readerVisible) {
    readerWindow.show();
    scheduleTaskbarPolicyRefresh();
    readerWindow.focus();
  } else {
    readerWindow.hide();
  }
  updateTrayMenu();
  broadcastReaderState();
  return {
    ok: true,
    route: "window",
    action: "set-reader-visible",
    readerVisible: appState.readerVisible
  };
}

async function handleControlAction(action, payload = {}) {
  switch (action) {
    case "mic-toggle":
      broadcast("pet-command", { type: "mic-toggle", enabled: Boolean(payload.enabled) });
      return { ok: true, route: "ipc", action };
    case "interrupt":
      broadcast("pet-command", { type: "interrupt" });
      return { ok: true, route: "ipc", action };
    case "set-reader-visible":
      return setReaderVisible(Boolean(payload.enabled));
    case "set-outfit": {
      const outfitId = String(payload.outfitId || "normal");
      const rawParameterId = String(payload.parameterId || "Param10");
      const parameterId = rawParameterId === "\u5e3dT" ? "Param10" : rawParameterId;
      const parameterIndex = parameterId === "Param10"
        ? null
        : Number.isInteger(payload.parameterIndex) && payload.parameterIndex >= 0
          ? payload.parameterIndex
          : null;
      const value = Math.max(0, Math.min(1, Number(payload.value) || 0));
      appState.outfit = { outfitId, parameterId, parameterIndex, value };
      saveCurrentState();
      latestFrontendState.currentOutfitId = outfitId;
      latestFrontendState.currentOutfitParameterId = parameterId;
      latestFrontendState.currentOutfitParameterIndex = parameterIndex;
      latestFrontendState.currentOutfitValue = value;
      broadcast("pet-command", {
        type: "outfit-set",
        outfitId,
        parameterId,
        parameterIndex,
        value
      });
      return { ok: true, route: "ipc", action };
    }
    case "set-expression": {
      const expressionId = String(payload.expressionId || "neutral");
      const expressionLabel = String(payload.expressionLabel || expressionId);
      const parameters = {};
      if (payload.parameters && typeof payload.parameters === "object") {
        for (const [key, value] of Object.entries(payload.parameters)) {
          const parameterId = String(key || "").trim();
          const numberValue = Number(value);
          if (!parameterId || !Number.isFinite(numberValue)) {
            continue;
          }
          parameters[parameterId] = Math.max(-1, Math.min(1, numberValue));
        }
      }
      appState.expression = { expressionId, expressionLabel, parameters };
      saveCurrentState();
      latestFrontendState.currentExpressionId = expressionId;
      latestFrontendState.currentExpressionLabel = expressionLabel;
      broadcast("pet-command", {
        type: "expression-set",
        expressionId,
        expressionLabel,
        parameters
      });
      return { ok: true, route: "ipc", action };
    }
    case "play-motion": {
      const group = String(payload.group || "Idle");
      const motionIndex = Number.isInteger(payload.motionIndex) && payload.motionIndex >= 0
        ? payload.motionIndex
        : null;
      const priority = Number.isInteger(payload.priority)
        ? payload.priority
        : undefined;
      broadcast("pet-command", {
        type: "motion-play",
        group,
        motionIndex,
        priority
      });
      return { ok: true, route: "ipc", action };
    }
    case "set-live2d-inspector":
    case "set-live2d-debug-overlay": {
      const enabled = Boolean(payload.enabled);
      updateFrontendState({ live2dInspectorOverlayEnabled: enabled });
      broadcast("pet-command", {
        type: "live2d-inspector-set",
        enabled
      });
      return {
        ok: true,
        route: "ipc",
        action,
        live2dInspectorOverlayEnabled: enabled
      };
    }
    case "toggle-live2d-inspector":
    case "toggle-live2d-debug-overlay": {
      const enabled = !Boolean(latestFrontendState.live2dInspectorOverlayEnabled);
      updateFrontendState({ live2dInspectorOverlayEnabled: enabled });
      broadcast("pet-command", {
        type: "live2d-inspector-set",
        enabled
      });
      return {
        ok: true,
        route: "ipc",
        action,
        live2dInspectorOverlayEnabled: enabled
      };
    }
    case "toggle-subtitle":
      return setReaderVisible(!(readerWindow && !readerWindow.isDestroyed() && readerWindow.isVisible()));
    case "toggle-camera":
      broadcast("pet-command", { type: "camera-toggle", enabled: Boolean(payload.enabled) });
      return { ok: true, route: "ipc", action };
    case "toggle-screen":
      broadcast("pet-command", { type: "screen-toggle", enabled: Boolean(payload.enabled) });
      return { ok: true, route: "ipc", action };
    case "toggle-browser":
      broadcast("pet-command", { type: "browser-toggle", enabled: Boolean(payload.enabled) });
      return { ok: true, route: "ipc", action };
    case "reload-frontend":
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.reloadIgnoringCache();
      }
      if (readerWindow && !readerWindow.isDestroyed()) {
        readerWindow.webContents.reloadIgnoringCache();
      }
      return { ok: true, action };
    case "show-pet":
      if (mainWindow && !mainWindow.isDestroyed()) {
        showPetWindow();
      }
      return { ok: true, action };
    case "move-next-display":
      moveWindowToNextDisplay();
      return { ok: true, action };
    case "set-game-mode":
      return {
        ok: true,
        action,
        petGameMode: setPetGameMode(Boolean(payload.enabled))
      };
    case "toggle-game-mode":
      return {
        ok: true,
        action,
        petGameMode: togglePetGameMode()
      };
    default:
      return { ok: false, error: `Unknown action: ${action}` };
  }
}

function applyWindowMode(mode, { force = false } = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const nextMode = mode === "window" ? "window" : "pet";
  if (!force && appState.mode === nextMode) {
    return;
  }

  appState.mode = nextMode;
  const targetBounds = resolveTargetBoundsForMode(nextMode);

  if (nextMode === "pet") {
    ensurePetAnchor();
    mainWindow.setAlwaysOnTop(true, "screen-saver");
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    mainWindow.setSkipTaskbar(true);
    mainWindow.setResizable(false);
    mainWindow.setMinimumSize(1, 1);
  } else {
    mainWindow.setAlwaysOnTop(false);
    mainWindow.setVisibleOnAllWorkspaces(false);
    mainWindow.setSkipTaskbar(true);
    mainWindow.setResizable(true);
    mainWindow.setMinimumSize(960, 640);
  }

  mainWindow.setBounds(targetBounds, false);
  applyPetFocusPolicy();
  applyTaskbarPolicy();
  if (nextMode === "pet") {
    broadcastPetHostState("pet-host-set");
  }
  saveCurrentState();
  applyIgnoreMouseState();
  updateTrayMenu();
}

function refreshLayoutForDisplayTopology(reason = "display-metrics-changed") {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const targetBounds = resolveTargetBoundsForMode(appState.mode);
  mainWindow.setBounds(targetBounds, false);

  if (appState.mode === "pet") {
    ensurePetAnchor();
    broadcastPetHostState("pet-host-set");
    saveCurrentState();
  } else {
    setBoundsForCurrentMode(targetBounds);
  }

  petLog("display-topology-refresh", {
    reason,
    mode: appState.mode,
    targetBounds,
    petAnchor: appState.petAnchor
  });
}

function moveWindowToNextDisplay() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const displays = getAllDisplays();
  if (displays.length < 2) {
    return;
  }

  if (appState.mode === "pet") {
    const currentAnchor = ensurePetAnchor();
    const currentDisplay = screen.getDisplayNearestPoint(currentAnchor);
    const currentIndex = displays.findIndex((item) => item.id === currentDisplay.id);
    const nextDisplay = displays[(currentIndex + 1) % displays.length];
    const currentArea = currentDisplay.workArea;
    const nextArea = nextDisplay.workArea;
    const ratioX = currentArea.width > 0
      ? (currentAnchor.x - currentArea.x) / currentArea.width
      : 0.5;
    const ratioY = currentArea.height > 0
      ? (currentAnchor.y - currentArea.y) / currentArea.height
      : 0.5;

    setPetAnchor(
      nextArea.x + nextArea.width * Math.min(Math.max(ratioX, 0), 1),
      nextArea.y + nextArea.height * Math.min(Math.max(ratioY, 0), 1)
    );
    mainWindow.setBounds(getPetHostBounds(), false);
    return;
  }

  const currentDisplay = findDisplayForBounds(mainWindow.getBounds());
  const currentIndex = displays.findIndex((item) => item.id === currentDisplay.id);
  const nextDisplay = displays[(currentIndex + 1) % displays.length];
  const currentBounds = mainWindow.getBounds();

  const offsetX = currentBounds.x - currentDisplay.workArea.x;
  const offsetY = currentBounds.y - currentDisplay.workArea.y;
  const nextBounds = clampBoundsToDisplay(
    {
      x: nextDisplay.workArea.x + offsetX,
      y: nextDisplay.workArea.y + offsetY,
      width: currentBounds.width,
      height: currentBounds.height
    },
    nextDisplay
  );

  mainWindow.setBounds(nextBounds, false);
  setBoundsForCurrentMode(nextBounds);
}

function showMainWindow() {
  if (!mainWindow) {
    return;
  }
  showPetWindow();
}

function toggleForceIgnoreMouse() {
  appState.forceIgnoreMouse = !appState.forceIgnoreMouse;
  saveCurrentState();
  applyIgnoreMouseState();
  broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
  updateTrayMenu();
}

function toggleReaderWindow() {
  if (!readerWindow || readerWindow.isDestroyed()) {
    appState.readerVisible = true;
    createReaderWindow();
    return;
  }
  if (readerWindow.isVisible()) {
    readerWindow.hide();
  } else {
    readerWindow.show();
    scheduleTaskbarPolicyRefresh();
    readerWindow.focus();
  }
}

function reloadMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.reloadIgnoringCache();
  }
}

function getMenuState() {
  return {
    forceIgnoreMouse: appState.forceIgnoreMouse,
    petGameMode: appState.petGameMode,
    readerVisible: appState.readerVisible
  };
}

function getMenuActions() {
  return {
    showPet: showMainWindow,
    toggleIgnoreMouse: toggleForceIgnoreMouse,
    toggleGameMode: togglePetGameMode,
    toggleReader: toggleReaderWindow,
    moveNextDisplay: moveWindowToNextDisplay,
    reloadFrontend: reloadMainWindow,
    quit: () => app.quit()
  };
}

function updateTrayMenu() {
  if (!tray) {
    return;
  }

  tray.setContextMenu(createTrayMenu(getMenuState(), getMenuActions()));
  tray.setToolTip(`${APP_NAME} (${appState.mode})`);
}

function showPetContextMenu() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  createPetContextMenu(getMenuState(), getMenuActions()).popup({ window: mainWindow });
}

function startControlServer() {
  if (controlServer) {
    return;
  }

  controlServer = createControlServer({
    host: CONTROL_HOST,
    port: CONTROL_PORT,
    readRendererStatus,
    readLive2DInspectorSnapshot,
    getShellStatus: () => ({
      mode: appState.mode,
      forceIgnoreMouse: appState.forceIgnoreMouse,
      petGameMode: appState.petGameMode,
      petSpanAllDisplays: appState.petSpanAllDisplays,
      petHostBounds: getPetHostBounds(),
      petAnchor: ensurePetAnchor(),
      bounds: mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : null
    }),
    isReaderVisible: () => Boolean(appState.readerVisible),
    handleControlAction,
    applyRendererBackendConfig,
    log: petLog
  });
}

function createTray() {
  if (tray) {
    return;
  }

  const trayIcon = nativeImage.createFromPath(iconPath);
  tray = new Tray(trayIcon);
  tray.on("double-click", () => {
    showMainWindow();
  });
  updateTrayMenu();
}

function createReaderWindow() {
  if (readerWindow && !readerWindow.isDestroyed()) {
    if (appState.readerVisible) {
      readerWindow.show();
      scheduleTaskbarPolicyRefresh();
      readerWindow.focus();
    }
    return;
  }

  const bounds = clampReaderBounds(getReaderBounds());
  readerWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    minWidth: MIN_READER_WINDOW_WIDTH,
    minHeight: MIN_READER_WINDOW_HEIGHT,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    resizable: true,
    maximizable: false,
    minimizable: false,
    skipTaskbar: true,
    fullscreenable: false,
    alwaysOnTop: true,
    title: `${APP_NAME} Reader`,
    icon: iconPath,
    autoHideMenuBar: true,
    webPreferences: {
      preload: readerPreloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false
    }
  });

  readerWindow.setMenuBarVisibility(false);
  readerWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  readerWindow.setSkipTaskbar(true);
  readerWindow.on("show", scheduleTaskbarPolicyRefresh);
  readerWindow.on("restore", scheduleTaskbarPolicyRefresh);

  readerWindow.on("move", () => {
    if (!readerWindow || readerWindow.isDestroyed()) {
      return;
    }
    setReaderBounds(readerWindow.getBounds());
  });

  readerWindow.on("resize", () => {
    if (!readerWindow || readerWindow.isDestroyed()) {
      return;
    }
    setReaderBounds(readerWindow.getBounds());
  });

  readerWindow.on("show", () => {
    appState.readerVisible = true;
    saveCurrentState();
    broadcastReaderState();
    updateTrayMenu();
  });

  readerWindow.on("hide", () => {
    appState.readerVisible = false;
    saveCurrentState();
    broadcastReaderState();
    updateTrayMenu();
  });

  readerWindow.on("closed", () => {
    readerWindow = null;
  });

  readerWindow.webContents.on("did-finish-load", () => {
    broadcastReaderState();
    if (appState.readerVisible) {
      readerWindow.show();
      readerWindow.focus();
    }
  });

  readerWindow.loadFile(readerEntry).catch((error) => {
    petLog("Failed to load reader window", error);
  });
}

function createWindow() {
  const bounds = resolveTargetBoundsForMode(appState.mode);
  const entryPath = rendererEntry;
  const rendererBuildAvailable = fs.existsSync(entryPath);

  mainWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    minWidth: MIN_PET_WINDOW_WIDTH,
    minHeight: MIN_PET_WINDOW_HEIGHT,
    transparent: true,
    backgroundColor: "#00000000",
    frame: false,
    show: false,
    resizable: false,
    skipTaskbar: true,
    focusable: false,
    fullscreenable: false,
    title: APP_NAME,
    icon: iconPath,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false
    }
  });

  petLog("Creating window", {
    entryPath,
    rendererBuildAvailable,
    mode: appState.mode,
    bounds,
    petSpanAllDisplays: appState.petSpanAllDisplays,
    petAnchor: ensurePetAnchor(),
    backendBaseUrl: process.env.KURO_BACKEND_BASE_URL || null,
    backendWsUrl: process.env.KURO_BACKEND_WS_URL || null
  });

  mainWindow.setMenuBarVisibility(false);
  applyWindowMode(appState.mode, { force: true });
  scheduleTaskbarPolicyRefresh();
  mainWindow.on("show", scheduleTaskbarPolicyRefresh);
  mainWindow.on("restore", scheduleTaskbarPolicyRefresh);

  mainWindow.on("move", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      setBoundsForCurrentMode(mainWindow.getBounds());
    }
  });

  mainWindow.on("resize", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      setBoundsForCurrentMode(mainWindow.getBounds());
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.on("maximize", () => broadcast("window-maximized-change", true));
  mainWindow.on("unmaximize", () => broadcast("window-maximized-change", false));
  mainWindow.on("enter-full-screen", () => broadcast("window-fullscreen-change", true));
  mainWindow.on("leave-full-screen", () => broadcast("window-fullscreen-change", false));

  mainWindow.webContents.on("did-finish-load", () => {
    petLog("did-finish-load");
    mainWindow.webContents
      .executeJavaScript(
        `JSON.stringify({
          href: location.href,
          readyState: document.readyState,
          hasApi: !!window.api,
          hasElectron: !!window.electron,
          wsUrl: window.localStorage.getItem("wsUrl"),
          baseUrl: window.localStorage.getItem("baseUrl")
        })`,
        true
      )
      .then((result) => petLog("renderer-diagnostics", result))
      .catch((error) => petLog("renderer-diagnostics-failed", error));

    appState.mode = "pet";
    applyWindowMode("pet", { force: true });
    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        showPetWindow({ focus: false });
      }
    }, 180);
  });

  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    petLog("did-fail-load", { errorCode, errorDescription, validatedURL });
    if (!rendererBuildAvailable) {
      mainWindow.loadURL(
        `data:text/html;charset=utf-8,${encodeURIComponent(
          "<!doctype html><title>Kuro Pet</title><body style=\"margin:0;background:transparent;color:white;font:14px sans-serif\">Renderer build missing. Run npm run build:renderer.</body>"
        )}`
      ).catch((error) => petLog("Failed to load renderer missing page", error));
      setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          showPetWindow({ focus: false });
        }
      }, 180);
    }
  });

  mainWindow.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    petLog("renderer-console", { level, message, line, sourceId });
  });

  mainWindow.webContents.on(
    "did-fail-provisional-load",
    (_event, errorCode, errorDescription, validatedURL) => {
      petLog("did-fail-provisional-load", { errorCode, errorDescription, validatedURL });
    }
  );

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    petLog("render-process-gone", details);
  });

  mainWindow.webContents.on("unresponsive", () => {
    petLog("renderer-unresponsive");
  });

  mainWindow.webContents.on("before-input-event", (_event, input) => {
    if (input.type !== "keyDown") {
      return;
    }

    if (input.key === "F10") {
      appState.forceIgnoreMouse = !appState.forceIgnoreMouse;
      saveCurrentState();
      applyIgnoreMouseState();
      broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
      updateTrayMenu();
    }

    if (input.key === "F11") {
      moveWindowToNextDisplay();
    }
  });

  mainWindow.loadFile(entryPath).catch((error) => {
    petLog("Failed to load renderer entry", error);
  });
}

function registerIpc() {
  ipcMain.on("get-bootstrap-config", (event) => {
    event.returnValue = {
      baseUrl: process.env.KURO_BACKEND_BASE_URL || "http://127.0.0.1:23456",
      wsUrl: process.env.KURO_BACKEND_WS_URL || "ws://127.0.0.1:23456/client-ws",
      zoomScale: normalizePetZoomScale(appState.petZoomScale),
      petHostBounds: getPetHostBounds(),
      petAnchor: ensurePetAnchor(),
      outfit: appState.outfit,
      expression: appState.expression
    };
  });

  ipcMain.on("pet-frontend-state", (_event, payload) => {
    if (!payload || typeof payload !== "object") {
      return;
    }
    updateFrontendState(payload);
  });

  ipcMain.on("set-mode", (_event, mode) => {
    const nextMode = mode === "window" ? "window" : "pet";
    applyWindowMode(nextMode);
    saveCurrentState();
  });

  ipcMain.on("toggle-force-ignore-mouse", () => {
    appState.forceIgnoreMouse = !appState.forceIgnoreMouse;
    saveCurrentState();
    applyIgnoreMouseState();
    broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
    updateTrayMenu();
  });

  ipcMain.on("set-ignore-mouse-event", (_event, ignore) => {
    hoveredComponents.set("live2d-hit-test", !ignore);
    applyIgnoreMouseState();
  });

  ipcMain.on("window-close", () => {
    mainWindow?.close();
  });

  ipcMain.on("window-minimize", () => {
    mainWindow?.minimize();
  });

  ipcMain.on("window-maximize", () => {
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  });

  ipcMain.on("window-unfullscreen", () => {
    mainWindow?.setFullScreen(false);
  });

  ipcMain.on("show-context-menu", () => {
    showPetContextMenu();
  });

  ipcMain.handle("reader-get-state", () => getReaderStatePayload());

  ipcMain.handle("reader-send-text", async (_event, text, attachments) => {
    return sendTextToFrontend(text, attachments);
  });

  ipcMain.on("reader-close", () => {
    if (readerWindow && !readerWindow.isDestroyed()) {
      readerWindow.hide();
    }
  });

  ipcMain.on("update-component-hover", (_event, componentName, hovered) => {
    if (typeof componentName !== "string" || !componentName) {
      return;
    }
    hoveredComponents.set(componentName, Boolean(hovered));
    applyIgnoreMouseState();
  });

  ipcMain.on("start-window-drag", (_event, payload) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    if (appState.mode === "pet") {
      return;
    }

    if (!hoveredComponents.get("live2d-model")) {
      return;
    }

    const screenX = Number(payload?.screenX);
    const screenY = Number(payload?.screenY);
    if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) {
      return;
    }

    activeWindowDrag = {
      startCursor: { x: screenX, y: screenY },
      startBounds: mainWindow.getBounds()
    };

    hoveredComponents.set("pet-window-drag", true);
    applyIgnoreMouseState();
  });

  ipcMain.on("update-window-drag", (_event, payload) => {
    if (!mainWindow || mainWindow.isDestroyed() || !activeWindowDrag) {
      return;
    }

    if (appState.mode === "pet") {
      return;
    }

    const screenX = Number(payload?.screenX);
    const screenY = Number(payload?.screenY);
    if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) {
      return;
    }

    const deltaX = screenX - activeWindowDrag.startCursor.x;
    const deltaY = screenY - activeWindowDrag.startCursor.y;
    const startBounds = activeWindowDrag.startBounds;

    const nextBounds = clampBoundsToVirtualDesktopWithOverflow({
      x: startBounds.x + deltaX,
      y: startBounds.y + deltaY,
      width: startBounds.width,
      height: startBounds.height
    });

    mainWindow.setBounds(nextBounds, false);
    setBoundsForCurrentMode(nextBounds);
  });

  ipcMain.on("adjust-pet-window-scale", (_event, payload) => {
    adjustPetWindowScale(Number(payload?.scaleRatio));
  });

  ipcMain.on("set-pet-window-zoom", (_event, payload) => {
    setPetWindowZoom(Number(payload?.zoomScale));
  });

  ipcMain.on("set-pet-model-zoom", (_event, payload) => {
    setPetModelZoom(Number(payload?.zoomScale));
  });

  ipcMain.on("set-pet-anchor", (_event, payload) => {
    setPetAnchor(Number(payload?.x), Number(payload?.y), { broadcast: false });
  });

  ipcMain.on("end-window-drag", () => {
    activeWindowDrag = null;
    hoveredComponents.set("pet-window-drag", false);
    applyIgnoreMouseState();
  });

  ipcMain.handle("get-screen-capture", async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender) || mainWindow;
    const bounds = win ? win.getBounds() : getWindowBoundsForMode(appState.mode);
    const currentDisplay =
      appState.mode === "pet"
        ? screen.getDisplayNearestPoint(ensurePetAnchor())
        : findDisplayForBounds(bounds);
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: { width: 0, height: 0 }
    });

    const exactMatch = sources.find((source) => {
      if (source.display_id && Number(source.display_id) === currentDisplay.id) {
        return true;
      }
      return false;
    });

    return (exactMatch || sources[0] || {}).id || "";
  });
}

const singleInstanceLock = app.requestSingleInstanceLock();
if (!singleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    showPetWindow();
  });

  app.whenReady().then(() => {
    session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
      callback(permission === "media" || permission === "display-capture");
    });
    statePath = path.join(app.getPath("userData"), "pet-shell-state.json");
    appState = mergeState(loadState(statePath));
    latestFrontendState.currentOutfitId = appState.outfit.outfitId;
    latestFrontendState.currentOutfitParameterId = appState.outfit.parameterId;
    latestFrontendState.currentOutfitParameterIndex = appState.outfit.parameterIndex;
    latestFrontendState.currentOutfitValue = appState.outfit.value;
    latestFrontendState.currentExpressionId = appState.expression.expressionId;
    latestFrontendState.currentExpressionLabel = appState.expression.expressionLabel;
    appState.mode = "pet";
    appState.forceIgnoreMouse = true;
    appState.petSpanAllDisplays = true;
    appState.petZoomScale = normalizePetZoomScale(appState.petZoomScale);
    ensurePetAnchor();
    saveCurrentState();
    petLog("app-ready", { statePath, appState });

    registerIpc();
    startControlServer();
    createTray();
    createWindow();
    createReaderWindow();

    screen.on("display-added", () => refreshLayoutForDisplayTopology("display-added"));
    screen.on("display-removed", () => refreshLayoutForDisplayTopology("display-removed"));
    screen.on("display-metrics-changed", () =>
      refreshLayoutForDisplayTopology("display-metrics-changed")
    );
  });

  app.on("activate", () => {
    if (!mainWindow) {
      createWindow();
    }
    if (!readerWindow) {
      createReaderWindow();
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("before-quit", () => {
    if (controlServer) {
      try {
        controlServer.close();
      } catch (error) {
        petLog("control-server-close-error", error);
      }
      controlServer = null;
    }
  });
}

