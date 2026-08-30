const path = require("path");
const fs = require("fs");
const http = require("http");
const https = require("https");
const { spawn } = require("child_process");
const {
  app,
  BrowserWindow,
  Tray,
  desktopCapturer,
  dialog,
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
const { createBriefingStore } = require("./main-process/briefing-store");
const { createMailBriefingService } = require("./main-process/mail-briefing-service");
const { startControlServer: createControlServer } = require("./main-process/control-server");
const { createPetContextMenu, createTrayMenu } = require("./main-process/menus");
const { createPetLogger } = require("./main-process/pet-logger");
const {
  resolvePetDisplayContext,
  resolvePetLayout,
  resolveZoomAwarePetHostSize
} = require("./main-process/pet-layout");
const {
  hostContainsBounds,
  normalizeHostBounds,
  normalizeScreenBounds,
  resolveHostResizeAction,
  resolvePetHostBounds,
  shouldFreezePetHostRelocation
} = require("./main-process/pet-host-envelope");
const {
  advancePetTransformState,
  applyPetTransformRequest,
  createPetTransformState,
  isCurrentTransformRevision
} = require("./main-process/pet-transform-state");
const { resolvePetMousePolicy } = require("./main-process/pet-mouse-policy");
const { resolvePetWindowPolicy } = require("./main-process/pet-window-policy");
const {
  canMutateFixedPetShell,
  resolveFixedDesktopShellBounds
} = require("./main-process/pet-fixed-shell");

const APP_NAME = "Kuro Pet Electron";
const APP_USER_MODEL_ID = "kuro.desktop-agent";
const CONTROL_SERVICE = "kuro-pet-control";
const CONTROL_PROTOCOL_VERSION = 1;
const APP_STARTED_AT = new Date().toISOString();
const APP_INSTANCE_ID = `${process.pid}-${Date.now().toString(36)}`;
const TEMP_MAX_RENDER_PERFORMANCE = false;
const CONTROL_HOST = process.env.KURO_PET_CONTROL_HOST || "127.0.0.1";
const CONTROL_PORT = Number(process.env.KURO_PET_CONTROL_PORT || "23567");
const LAUNCHER_CONTROL_URL = process.env.KURO_LAUNCHER_CONTROL_URL || "http://127.0.0.1:23568";
const LAUNCHER_CONTROL_TOKEN = process.env.KURO_LAUNCHER_CONTROL_TOKEN || "";
const MAX_LAUNCHER_RESPONSE_BYTES = 2 * 1024 * 1024;
const PET_CURSOR_POLL_MS = 50;
const PET_CURSOR_HEARTBEAT_MS = 750;
const PET_INTERACTION_LEASE_TIMEOUT_MS = 1800;
const PET_INTERACTION_LEASE_WATCHDOG_MS = 250;
const PET_ANCHOR_SAVE_DELAY_MS = 240;
const PET_HOST_SHRINK_DELAY_MS = 360;
const PET_FIXED_DESKTOP_SHELL = process.env.KURO_PET_FIXED_DESKTOP_SHELL !== "0";
const PET_HOST_MODE = PET_FIXED_DESKTOP_SHELL
  ? "fixed-desktop-shell-v1"
  : "model-bounds-follow-v6";
const PET_INTERACTION_ZOOM_IDLE_MS = 180;
const PET_INTERACTION_FREEZE_HOST =
  !PET_FIXED_DESKTOP_SHELL &&
  process.env.KURO_PET_INTERACTION_FREEZE_HOST === "1";

if (TEMP_MAX_RENDER_PERFORMANCE) {
  app.commandLine.appendSwitch("disable-frame-rate-limit");
  app.commandLine.appendSwitch("disable-background-timer-throttling");
  app.commandLine.appendSwitch("disable-renderer-backgrounding");
  app.commandLine.appendSwitch("disable-backgrounding-occluded-windows");
}

const projectRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(projectRoot, "..");
const rendererEntry = path.join(projectRoot, "renderer-dist", "index.html");
const workPanelEntry = path.join(projectRoot, "renderer-dist", "work-panel.html");
const iconPath = path.join(projectRoot, "src", "assets", "favicon.ico");
const readerEntry = path.join(__dirname, "reader-window.html");
const readerPreloadPath = path.join(__dirname, "reader-preload.js");
const briefingPreloadPath = path.join(__dirname, "briefing-preload.js");
const studySnapshotPath = path.join(repoRoot, "Open-LLM-VTuber", "private", "study", "study_snapshot.json");
const MIN_PET_ZOOM_SCALE = 0.2;
const MAX_PET_ZOOM_SCALE = 8;
const MIN_PET_WINDOW_WIDTH = 280;
const MIN_PET_WINDOW_HEIGHT = 420;
const MIN_READER_WINDOW_WIDTH = 360;
const MIN_READER_WINDOW_HEIGHT = 236;
const MIN_BRIEFING_WINDOW_WIDTH = 820;
const MIN_BRIEFING_WINDOW_HEIGHT = 540;

let mainWindow = null;
let readerWindow = null;
let briefingWindow = null;
let tray = null;
let appState = cloneDefaultState();
let statePath = "";
let briefingStore = null;
let briefingStorePath = "";
let hoveredComponents = new Map();
let componentHoverLeaseAt = new Map();
let activeWindowDrag = null;
let lastPetMousePolicy = null;
let lastPetWindowPolicy = null;
let petWindowLayerRefreshGeneration = 0;
let petWindowLayerRepairScheduled = false;
let controlServer = null;
let mailBriefingService = null;
let studySnapshotWatcher = null;
let studySnapshotBroadcastTimer = null;
let petCursorBroadcastTimer = null;
let petInteractionLeaseTimer = null;
let lastPetCursorPoint = null;
let petAnchorSaveTimer = null;
let petHostShrinkTimer = null;
let pendingPetHostShrinkBounds = null;
let currentPetHostBounds = null;
let currentFixedPetShellBounds = null;
let fixedPetShellBoundsWriteCount = 0;
let fixedPetShellBoundsRejectedCount = 0;
let lastFixedPetShellBoundsWriteReason = null;
let lastFixedPetShellBoundsRejectedReason = null;
let latestPetModelScreenBounds = null;
let latestPetEnvelopeRevision = 0;
let petTransformState = null;
let petInteractionZoomTimer = null;
let pendingInteractionHostBounds = null;
let petHostRelocationSuppressedCount = 0;
let petHostRelocationAppliedCount = 0;
let lastPetHostRelocationSuppressedReason = null;
let lastPetHostRelocationAppliedReason = null;
let petInteractionState = {
  dragActive: false,
  zoomActive: false,
  lastZoomRequestAt: null
};
let live2dPreviewCaptureInFlight = null;
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
  micEnabled: false,
  micPaused: false,
  cameraEnabled: false,
  screenEnabled: false,
  browserPanelEnabled: false,
  live2dInspectorOverlayEnabled: false
};
let appIsQuitting = false;

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

function schedulePetAnchorSave() {
  if (petAnchorSaveTimer) {
    clearTimeout(petAnchorSaveTimer);
  }
  petAnchorSaveTimer = setTimeout(() => {
    petAnchorSaveTimer = null;
    saveCurrentState();
  }, PET_ANCHOR_SAVE_DELAY_MS);
  petAnchorSaveTimer.unref?.();
}

function flushPetAnchorSave() {
  if (petAnchorSaveTimer) {
    clearTimeout(petAnchorSaveTimer);
    petAnchorSaveTimer = null;
  }
  saveCurrentState();
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

function getDefaultBriefingBounds() {
  const area = getVirtualWorkAreaBounds();
  const width = Math.min(
    1280,
    Math.max(MIN_BRIEFING_WINDOW_WIDTH, Math.round(area.width * 0.74))
  );
  const height = Math.min(
    820,
    Math.max(MIN_BRIEFING_WINDOW_HEIGHT, Math.round(area.height * 0.72))
  );

  return {
    x: area.x + Math.max(20, Math.round((area.width - width) / 2)),
    y: area.y + Math.max(20, Math.round((area.height - height) / 2)),
    width,
    height
  };
}

function getBriefingBounds() {
  return appState.briefingBounds || getDefaultBriefingBounds();
}

function setBriefingBounds(bounds) {
  appState.briefingBounds = {
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
  const defaultAnchor = getDefaultPetAnchor();
  resetPetHostEnvelope(defaultAnchor);
  setPetAnchor(defaultAnchor.x, defaultAnchor.y);
  showPetWindow();
  return { ...ensurePetTransformState().anchor };
}

function getAllDisplays() {
  return screen.getAllDisplays().sort((a, b) => a.bounds.x - b.bounds.x || a.bounds.y - b.bounds.y);
}

function rebuildFixedPetShellBounds() {
  currentFixedPetShellBounds = resolveFixedDesktopShellBounds(getAllDisplays());
  return { ...currentFixedPetShellBounds };
}

function getFixedPetShellBounds() {
  if (!currentFixedPetShellBounds) {
    return rebuildFixedPetShellBounds();
  }
  return { ...currentFixedPetShellBounds };
}

function getPetHostSizingMode() {
  if (PET_FIXED_DESKTOP_SHELL) {
    return "compact-render-surface";
  }
  return latestPetModelScreenBounds ? "model-bounds" : "bootstrap-fallback";
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
  if (PET_FIXED_DESKTOP_SHELL) {
    return getFixedPetShellBounds();
  }
  if (!currentPetHostBounds) {
    currentPetHostBounds = { ...getFallbackPetLayout().hostBounds };
  }
  return { ...currentPetHostBounds };
}

function applyMainWindowBounds(bounds, reason) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return false;
  }
  const normalized = normalizeHostBounds(bounds);
  if (!normalized) {
    return false;
  }
  if (
    PET_FIXED_DESKTOP_SHELL &&
    appState.mode === "pet" &&
    !canMutateFixedPetShell(reason)
  ) {
    fixedPetShellBoundsRejectedCount += 1;
    lastFixedPetShellBoundsRejectedReason = String(reason || "unspecified");
    petLog("fixed-pet-shell-bounds-rejected", {
      reason: lastFixedPetShellBoundsRejectedReason,
      requestedBounds: normalized
    });
    return false;
  }

  const current = mainWindow.getBounds();
  const unchanged =
    current.x === normalized.x &&
    current.y === normalized.y &&
    current.width === normalized.width &&
    current.height === normalized.height;
  if (!unchanged) {
    mainWindow.setBounds(normalized, false);
  }
  if (PET_FIXED_DESKTOP_SHELL && appState.mode === "pet") {
    fixedPetShellBoundsWriteCount += unchanged ? 0 : 1;
    lastFixedPetShellBoundsWriteReason = String(reason || "unspecified");
  }
  return !unchanged;
}

function getDefaultPetAnchorRequest() {
  const defaults = cloneDefaultState().boundsByMode.pet;
  const primaryArea = screen.getPrimaryDisplay().workArea;
  return {
    x: primaryArea.x + defaults.x + defaults.width / 2,
    y: primaryArea.y + primaryArea.height - 24
  };
}

function getFallbackPetLayout(point = null) {
  return resolvePetLayout(
    point || appState.petAnchor || getDefaultPetAnchorRequest(),
    getAllDisplays(),
    resolveZoomAwarePetHostSize(appState.petZoomScale)
  );
}

function getDefaultPetAnchor() {
  return getFallbackPetLayout(getDefaultPetAnchorRequest()).anchor;
}

function ensurePetAnchor() {
  if (petTransformState) {
    return { ...petTransformState.anchor };
  }
  const fallback = getDefaultPetAnchorRequest();
  const anchor = {
    x: Number.isFinite(Number(appState.petAnchor?.x))
      ? Number(appState.petAnchor.x)
      : fallback.x,
    y: Number.isFinite(Number(appState.petAnchor?.y))
      ? Number(appState.petAnchor.y)
      : fallback.y
  };
  appState.petAnchor = anchor;
  return { ...anchor };
}

function ensurePetTransformState() {
  if (!petTransformState) {
    petTransformState = createPetTransformState(
      {
        revision: 1,
        anchor: ensurePetAnchor(),
        zoomScale: appState.petZoomScale
      },
      {
        minZoomScale: MIN_PET_ZOOM_SCALE,
        maxZoomScale: MAX_PET_ZOOM_SCALE
      }
    );
  }
  appState.petAnchor = { ...petTransformState.anchor };
  appState.petZoomScale = petTransformState.zoomScale;
  return {
    revision: petTransformState.revision,
    anchor: { ...petTransformState.anchor },
    zoomScale: petTransformState.zoomScale
  };
}

function buildPetTransformStatePayload(sourceRequestId = null) {
  const transform = ensurePetTransformState();
  return {
    type: "pet-transform-set",
    transformRevision: transform.revision,
    petAnchor: { ...transform.anchor },
    zoomScale: transform.zoomScale,
    sourceRequestId:
      Number.isSafeInteger(Number(sourceRequestId)) && Number(sourceRequestId) >= 0
        ? Number(sourceRequestId)
        : null
  };
}

function broadcastPetTransformState(sourceRequestId = null) {
  broadcast("pet-command", buildPetTransformStatePayload(sourceRequestId));
}

function acceptPetTransformState(nextState, options = {}) {
  petTransformState = createPetTransformState(
    nextState,
    {
      minZoomScale: MIN_PET_ZOOM_SCALE,
      maxZoomScale: MAX_PET_ZOOM_SCALE
    }
  );
  appState.petAnchor = { ...petTransformState.anchor };
  appState.petZoomScale = petTransformState.zoomScale;
  clearPetHostShrinkTimer();
  latestPetModelScreenBounds = null;
  latestPetEnvelopeRevision = 0;

  if (options.deferSave === true) {
    schedulePetAnchorSave();
  } else {
    flushPetAnchorSave();
  }
  if (options.broadcast !== false) {
    broadcastPetTransformState(options.sourceRequestId);
  }
  return ensurePetTransformState();
}

function commitPetTransformValues(nextValues, options = {}) {
  const result = advancePetTransformState(
    ensurePetTransformState(),
    nextValues,
    {
      minZoomScale: MIN_PET_ZOOM_SCALE,
      maxZoomScale: MAX_PET_ZOOM_SCALE
    }
  );
  if (!result.changed) {
    if (options.broadcast === true) {
      broadcastPetTransformState(options.sourceRequestId);
    }
    return ensurePetTransformState();
  }
  return acceptPetTransformState(result.state, options);
}

function buildPetHostStatePayload(type = "pet-host-set") {
  const transform = ensurePetTransformState();
  const anchor = transform.anchor;
  const displayContext = resolvePetDisplayContext(anchor, getAllDisplays());
  return {
    type,
    transformRevision: transform.revision,
    petHostMode: PET_HOST_MODE,
    petHostSizing: getPetHostSizingMode(),
    petFixedDesktopShell: PET_FIXED_DESKTOP_SHELL,
    petShellBounds: PET_FIXED_DESKTOP_SHELL ? getFixedPetShellBounds() : null,
    petHostBounds: getPetHostBounds(),
    petModelScreenBounds: latestPetModelScreenBounds
      ? { ...latestPetModelScreenBounds }
      : null,
    petDisplayId: displayContext.displayId,
    petDisplayScaleFactor: displayContext.scaleFactor,
    petWorkArea: displayContext.workArea
  };
}

function broadcastPetHostState(type = "pet-host-set") {
  broadcast("pet-command", buildPetHostStatePayload(type));
}

function setPetAnchor(x, y, options = {}) {
  const currentAnchor = ensurePetTransformState().anchor;
  const requestedAnchor = {
    x: Number.isFinite(Number(x)) ? Number(x) : currentAnchor.x,
    y: Number.isFinite(Number(y)) ? Number(y) : currentAnchor.y
  };
  return commitPetTransformValues(
    { anchor: requestedAnchor },
    {
      deferSave: options.deferSave === true,
      broadcast: options.broadcast !== false,
      sourceRequestId: options.sourceRequestId
    }
  ).anchor;
}

function clearPetHostShrinkTimer() {
  if (petHostShrinkTimer) {
    clearTimeout(petHostShrinkTimer);
    petHostShrinkTimer = null;
  }
  pendingPetHostShrinkBounds = null;
}

function isPetInteractionActive() {
  return petInteractionState.dragActive || petInteractionState.zoomActive;
}

function shouldFreezeCurrentPetHostRelocation() {
  return shouldFreezePetHostRelocation({
    enabled: PET_INTERACTION_FREEZE_HOST,
    mode: appState.mode,
    dragActive: petInteractionState.dragActive,
    zoomActive: petInteractionState.zoomActive
  });
}

function setPetDragInteractionActive(active) {
  petInteractionState.dragActive = Boolean(active);
}

function markPetZoomInteractionActive() {
  petInteractionState.zoomActive = true;
  petInteractionState.lastZoomRequestAt = Date.now();
  if (petInteractionZoomTimer) {
    clearTimeout(petInteractionZoomTimer);
  }
  petInteractionZoomTimer = setTimeout(() => {
    petInteractionZoomTimer = null;
    petInteractionState.zoomActive = false;
  }, PET_INTERACTION_ZOOM_IDLE_MS);
  petInteractionZoomTimer.unref?.();
}

function clearPetInteractionTimer() {
  if (petInteractionZoomTimer) {
    clearTimeout(petInteractionZoomTimer);
    petInteractionZoomTimer = null;
  }
  petInteractionState.zoomActive = false;
}

function suppressPetHostRelocation(bounds, reason) {
  pendingInteractionHostBounds = { ...bounds };
  petHostRelocationSuppressedCount += 1;
  lastPetHostRelocationSuppressedReason = String(reason || "model-envelope");
}

function applyPetHostBounds(bounds, reason = "model-envelope") {
  const normalized = normalizeHostBounds(bounds);
  if (!normalized) {
    return false;
  }

  if (PET_FIXED_DESKTOP_SHELL) {
    fixedPetShellBoundsRejectedCount += 1;
    lastFixedPetShellBoundsRejectedReason = String(reason || "model-envelope");
    return false;
  }

  if (shouldFreezeCurrentPetHostRelocation()) {
    suppressPetHostRelocation(normalized, reason);
    return false;
  }

  const current = currentPetHostBounds;
  const unchanged =
    current &&
    current.x === normalized.x &&
    current.y === normalized.y &&
    current.width === normalized.width &&
    current.height === normalized.height;
  currentPetHostBounds = normalized;
  if (unchanged) {
    pendingInteractionHostBounds = null;
    return false;
  }

  if (mainWindow && !mainWindow.isDestroyed() && appState.mode === "pet") {
    applyMainWindowBounds(normalized, reason);
    petHostRelocationAppliedCount += 1;
    lastPetHostRelocationAppliedReason = String(reason || "model-envelope");
  }
  pendingInteractionHostBounds = null;
  broadcastPetHostState("pet-host-set");
  return true;
}

function resetPetHostEnvelope(anchor = null) {
  clearPetHostShrinkTimer();
  latestPetModelScreenBounds = null;
  latestPetEnvelopeRevision = 0;
  pendingInteractionHostBounds = null;
  if (PET_FIXED_DESKTOP_SHELL) {
    currentPetHostBounds = getFixedPetShellBounds();
    broadcastPetHostState("pet-host-set");
    return;
  }
  const fallbackBounds = getFallbackPetLayout(anchor || ensurePetAnchor()).hostBounds;
  currentPetHostBounds = null;
  applyPetHostBounds(fallbackBounds, "envelope-reset");
}

function handlePetModelEnvelope(payload) {
  const transform = ensurePetTransformState();
  if (!isCurrentTransformRevision(transform, Number(payload?.transformRevision))) {
    return false;
  }

  const modelScreenBounds = normalizeScreenBounds(payload?.modelScreenBounds);
  const desiredHostBounds = resolvePetHostBounds(modelScreenBounds, {
    minWidth: MIN_PET_WINDOW_WIDTH,
    minHeight: MIN_PET_WINDOW_HEIGHT
  });
  if (!modelScreenBounds || !desiredHostBounds) {
    return false;
  }

  latestPetModelScreenBounds = modelScreenBounds;
  latestPetEnvelopeRevision = transform.revision;
  if (PET_FIXED_DESKTOP_SHELL) {
    clearPetHostShrinkTimer();
    pendingInteractionHostBounds = null;
    return true;
  }
  const action = resolveHostResizeAction(currentPetHostBounds, desiredHostBounds);

  if (
    shouldFreezeCurrentPetHostRelocation() &&
    (action === "apply" || action === "shrink")
  ) {
    clearPetHostShrinkTimer();
    suppressPetHostRelocation(desiredHostBounds, `interaction-${action}`);
    return true;
  }

  if (action === "apply") {
    clearPetHostShrinkTimer();
    return applyPetHostBounds(desiredHostBounds, "envelope-expanded");
  }

  if (action === "shrink") {
    pendingPetHostShrinkBounds = desiredHostBounds;
    if (!petHostShrinkTimer) {
      petHostShrinkTimer = setTimeout(() => {
        petHostShrinkTimer = null;
        const pendingBounds = pendingPetHostShrinkBounds;
        pendingPetHostShrinkBounds = null;
        if (pendingBounds) {
          applyPetHostBounds(pendingBounds, "envelope-shrunk");
        }
      }, PET_HOST_SHRINK_DELAY_MS);
      petHostShrinkTimer.unref?.();
    }
    return true;
  }

  clearPetHostShrinkTimer();
  return true;
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

function clampBriefingBounds(bounds) {
  return clampBoundsToVirtualDesktopWithOverflow(
    {
      ...bounds,
      width: Math.max(
        MIN_BRIEFING_WINDOW_WIDTH,
        Number(bounds.width) || MIN_BRIEFING_WINDOW_WIDTH
      ),
      height: Math.max(
        MIN_BRIEFING_WINDOW_HEIGHT,
        Number(bounds.height) || MIN_BRIEFING_WINDOW_HEIGHT
      )
    },
    220
  );
}

function resolveTargetBoundsForMode(mode) {
  const requestedBounds = getWindowBoundsForMode(mode);
  if (mode === "pet") {
    ensurePetAnchor();
    if (PET_FIXED_DESKTOP_SHELL) {
      return getFixedPetShellBounds();
    }
    return getPetHostBounds();
  }

  return clampBoundsToDisplay(requestedBounds, findDisplayForBounds(requestedBounds));
}

function applyIgnoreMouseState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const now = Date.now();
  const interactiveHover = Array.from(hoveredComponents.entries()).some(
    ([componentName, hovered]) => {
      if (!hovered) return false;
      if (!PET_FIXED_DESKTOP_SHELL || appState.mode !== "pet") return true;
      const leaseAt = componentHoverLeaseAt.get(componentName) || 0;
      return now - leaseAt <= PET_INTERACTION_LEASE_TIMEOUT_MS;
    }
  );
  lastPetMousePolicy = resolvePetMousePolicy({
    mode: appState.mode,
    petGameMode: appState.petGameMode,
    forceIgnoreMouse: appState.forceIgnoreMouse,
    interactiveHover
  });
  mainWindow.setIgnoreMouseEvents(lastPetMousePolicy.ignoreMouseEvents, {
    forward: lastPetMousePolicy.forwardMouseMoves
  });
}

function updateComponentHoverLease(componentName, hovered) {
  const normalizedName = String(componentName || "").trim();
  if (!normalizedName) return;
  hoveredComponents.set(normalizedName, Boolean(hovered));
  if (hovered) {
    componentHoverLeaseAt.set(normalizedName, Date.now());
  } else {
    componentHoverLeaseAt.delete(normalizedName);
  }
}

function failClosedPetInteraction(reason) {
  const hadInteractiveState = Array.from(hoveredComponents.values()).some(Boolean);
  activeWindowDrag = null;
  hoveredComponents.clear();
  componentHoverLeaseAt.clear();
  petInteractionState.dragActive = false;
  if (hadInteractiveState) {
    petLog("pet-interaction-fail-closed", { reason });
  }
  applyIgnoreMouseState();
}

function startPetInteractionLeaseWatchdog() {
  if (petInteractionLeaseTimer) return;
  petInteractionLeaseTimer = setInterval(() => {
    if (!PET_FIXED_DESKTOP_SHELL || appState.mode !== "pet") return;
    const now = Date.now();
    const staleInteractive = Array.from(hoveredComponents.entries()).some(
      ([componentName, hovered]) =>
        hovered &&
        now - (componentHoverLeaseAt.get(componentName) || 0) >
          PET_INTERACTION_LEASE_TIMEOUT_MS
    );
    if (staleInteractive) {
      failClosedPetInteraction("interaction-lease-expired");
    }
  }, PET_INTERACTION_LEASE_WATCHDOG_MS);
  petInteractionLeaseTimer.unref?.();
}

function stopPetInteractionLeaseWatchdog() {
  if (petInteractionLeaseTimer) {
    clearInterval(petInteractionLeaseTimer);
    petInteractionLeaseTimer = null;
  }
}

function clearPetInteractionState() {
  activeWindowDrag = null;
  hoveredComponents.clear();
  componentHoverLeaseAt.clear();
  petInteractionState.dragActive = false;
}

function setForceIgnoreMouse(enabled) {
  appState.forceIgnoreMouse = Boolean(enabled);
  clearPetInteractionState();
  saveCurrentState();
  applyIgnoreMouseState();
  broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
  updateTrayMenu();
  broadcastBriefingState();
  return appState.forceIgnoreMouse;
}

function applyPetFocusPolicy() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const policy = resolvePetWindowPolicy({ mode: appState.mode });
  if (mainWindow.isFocusable() !== policy.focusable) {
    mainWindow.setFocusable(policy.focusable);
  }
}

function applyPetWindowLayerPolicy({ reason = "unspecified", moveTop = false } = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    lastPetWindowPolicy = null;
    return null;
  }

  const policy = resolvePetWindowPolicy({ mode: appState.mode });

  // Focusability can mutate native window styles on Windows. Apply it before
  // asserting the topmost band so the final operation owns the z-order.
  if (mainWindow.isFocusable() !== policy.focusable) {
    mainWindow.setFocusable(policy.focusable);
  }
  mainWindow.setAlwaysOnTop(policy.alwaysOnTop, policy.alwaysOnTopLevel);
  mainWindow.setVisibleOnAllWorkspaces(policy.visibleOnAllWorkspaces, {
    visibleOnFullScreen: policy.visibleOnFullScreen
  });
  mainWindow.setSkipTaskbar(policy.skipTaskbar);

  if (moveTop && policy.moveTopOnShow && mainWindow.isVisible()) {
    mainWindow.moveTop();
  }

  lastPetWindowPolicy = {
    mode: policy.mode,
    expectedAlwaysOnTop: policy.alwaysOnTop,
    actualAlwaysOnTop: mainWindow.isAlwaysOnTop(),
    expectedFocusable: policy.focusable,
    actualFocusable: mainWindow.isFocusable(),
    visible: mainWindow.isVisible(),
    reason
  };

  if (
    lastPetWindowPolicy.actualAlwaysOnTop !== lastPetWindowPolicy.expectedAlwaysOnTop ||
    lastPetWindowPolicy.actualFocusable !== lastPetWindowPolicy.expectedFocusable
  ) {
    petLog("pet-window-layer-policy-mismatch", lastPetWindowPolicy);
  }

  return lastPetWindowPolicy;
}

function schedulePetWindowLayerRefresh(reason, { moveTop = false } = {}) {
  const generation = ++petWindowLayerRefreshGeneration;
  const refresh = () => {
    if (generation !== petWindowLayerRefreshGeneration) {
      return;
    }
    applyPetWindowLayerPolicy({ reason, moveTop });
  };

  refresh();
  setTimeout(refresh, 0);
  setTimeout(refresh, 250);
  setTimeout(refresh, 1000);
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
  clearPetInteractionState();
  saveCurrentState();
  applyPetFocusPolicy();
  applyIgnoreMouseState();
  updateTrayMenu();
  broadcastBriefingState();
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
    scheduleTaskbarPolicyRefresh();
    mainWindow.showInactive();
    schedulePetWindowLayerRefresh("show-pet-window", { moveTop: true });
    return;
  }

  applyPetWindowLayerPolicy({ reason: "show-window" });
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
  const current = ensurePetTransformState();
  const nextZoomScale = normalizePetZoomScale(zoomScale);
  const pivotScreenPoint =
    Number.isFinite(Number(options.pivotScreenPoint?.x)) &&
    Number.isFinite(Number(options.pivotScreenPoint?.y))
      ? {
          x: Number(options.pivotScreenPoint.x),
          y: Number(options.pivotScreenPoint.y)
        }
      : screen.getCursorScreenPoint();
  const scaleFactor = nextZoomScale / current.zoomScale;
  const result = applyPetTransformRequest(
    current,
    { kind: "zoom", scaleFactor, pivotScreenPoint },
    {
      minZoomScale: MIN_PET_ZOOM_SCALE,
      maxZoomScale: MAX_PET_ZOOM_SCALE
    }
  );
  if (result.changed) {
    acceptPetTransformState(result.state, {
      deferSave: options.deferSave === true,
      broadcast: options.broadcast !== false,
      sourceRequestId: options.sourceRequestId
    });
  } else if (options.broadcast === true) {
    broadcastPetTransformState(options.sourceRequestId);
  }
  return result.accepted;
}

function handlePetTransformRequest(payload) {
  const current = ensurePetTransformState();
  const kind = String(payload?.kind || "").trim().toLowerCase();
  const request = { kind };
  if (kind === "zoom") {
    markPetZoomInteractionActive();
    request.scaleFactor = Number(payload?.scaleFactor);
    request.pivotScreenPoint =
      Number.isFinite(Number(payload?.pivotScreenPoint?.x)) &&
      Number.isFinite(Number(payload?.pivotScreenPoint?.y))
        ? {
            x: Number(payload.pivotScreenPoint.x),
            y: Number(payload.pivotScreenPoint.y)
          }
        : screen.getCursorScreenPoint();
  } else if (kind === "anchor") {
    request.requestedAnchor = payload?.requestedAnchor;
  }

  const result = applyPetTransformRequest(current, request, {
    minZoomScale: MIN_PET_ZOOM_SCALE,
    maxZoomScale: MAX_PET_ZOOM_SCALE
  });
  if (!result.accepted) {
    return false;
  }
  if (result.changed) {
    acceptPetTransformState(result.state, {
      deferSave: true,
      broadcast: true,
      sourceRequestId: payload?.requestId
    });
  } else {
    broadcastPetTransformState(payload?.requestId);
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
    micEnabled: Boolean(latestFrontendState.micEnabled),
    micPaused: Boolean(latestFrontendState.micPaused),
    cameraEnabled: Boolean(latestFrontendState.cameraEnabled),
    screenEnabled: Boolean(latestFrontendState.screenEnabled),
    browserPanelEnabled: Boolean(latestFrontendState.browserPanelEnabled),
    readerVisible: Boolean(readerWindow && !readerWindow.isDestroyed() && readerWindow.isVisible())
  };
}

function isLoopbackHostname(hostname) {
  const normalized = String(hostname || "").trim().toLowerCase();
  return normalized === "127.0.0.1" || normalized === "localhost" || normalized === "::1" || normalized === "[::1]";
}

function launcherControlRequest(pathname, { method = "GET", payload = null, timeoutMs = 150000 } = {}) {
  return new Promise((resolve) => {
    if (!LAUNCHER_CONTROL_TOKEN) {
      resolve({ ok: false, error: "launcher-control-token-missing" });
      return;
    }
    let target;
    try {
      target = new URL(pathname, LAUNCHER_CONTROL_URL);
    } catch (_error) {
      resolve({ ok: false, error: "launcher-control-url-invalid" });
      return;
    }
    if (!isLoopbackHostname(target.hostname) || !["http:", "https:"].includes(target.protocol)) {
      resolve({ ok: false, error: "launcher-control-url-not-loopback" });
      return;
    }
    const body = payload && method !== "GET" ? Buffer.from(JSON.stringify(payload), "utf8") : null;
    const transport = target.protocol === "https:" ? https : http;
    const request = transport.request(
      target,
      {
        method,
        headers: {
          "Authorization": `Bearer ${LAUNCHER_CONTROL_TOKEN}`,
          ...(body
            ? {
                "Content-Type": "application/json; charset=utf-8",
                "Content-Length": String(body.length)
              }
            : {})
        }
      },
      (response) => {
        const chunks = [];
        let size = 0;
        response.on("data", (chunk) => {
          size += chunk.length;
          if (size > MAX_LAUNCHER_RESPONSE_BYTES) {
            request.destroy(new Error("launcher-control-response-too-large"));
            return;
          }
          chunks.push(chunk);
        });
        response.on("end", () => {
          try {
            const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
            if (response.statusCode && response.statusCode >= 400) {
              resolve({ ok: false, ...parsed, status: response.statusCode });
              return;
            }
            resolve(parsed && typeof parsed === "object" ? parsed : { ok: false, error: "launcher-control-invalid-response" });
          } catch (_error) {
            resolve({ ok: false, error: "launcher-control-invalid-response", status: response.statusCode || 0 });
          }
        });
      }
    );
    request.setTimeout(timeoutMs, () => request.destroy(new Error("launcher-control-timeout")));
    request.on("error", (error) => resolve({ ok: false, error: error.message || "launcher-control-unavailable" }));
    if (body) request.write(body);
    request.end();
  });
}

async function confirmWorkPanelAction({ title, message, detail = "" }) {
  const parent = briefingWindow && !briefingWindow.isDestroyed() ? briefingWindow : undefined;
  const options = {
    type: "warning",
    title: String(title || "確認操作"),
    message: String(message || "要繼續這項操作嗎？"),
    detail: String(detail || ""),
    buttons: ["取消", "繼續"],
    defaultId: 0,
    cancelId: 0,
    noLink: true
  };
  const result = parent
    ? await dialog.showMessageBox(parent, options)
    : await dialog.showMessageBox(options);
  return result.response === 1;
}

function normalizeHistoryContent(value) {
  if (typeof value === "string") {
    return value.trim();
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeHistoryContent(item))
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  if (value && typeof value === "object") {
    return normalizeHistoryContent(value.text ?? value.content ?? value.value ?? "");
  }
  return "";
}

function isSafeHistorySegment(value) {
  const normalized = String(value || "").trim();
  return Boolean(
    normalized &&
    normalized !== "." &&
    normalized !== ".." &&
    path.basename(normalized) === normalized &&
    !normalized.includes("/") &&
    !normalized.includes("\\")
  );
}

function getActiveChatHistoryPayload() {
  const confUid = String(latestFrontendState.confUid || "").trim();
  const historyUid = String(latestFrontendState.currentHistoryUid || "").trim();
  const title = String(latestFrontendState.currentHistoryTitle || "").trim();
  if (!confUid || !historyUid) {
    return {
      ok: true,
      confUid,
      historyUid,
      title,
      messages: []
    };
  }
  if (!isSafeHistorySegment(confUid) || !isSafeHistorySegment(historyUid)) {
    return { ok: false, error: "history-unavailable", confUid: "", historyUid: "", title, messages: [] };
  }

  const historyRoot = path.resolve(repoRoot, "Open-LLM-VTuber", "chat_history");
  const characterRoot = path.resolve(historyRoot, confUid);
  const historyPath = path.resolve(characterRoot, `${historyUid}.json`);
  const expectedPrefix = `${characterRoot}${path.sep}`.toLowerCase();
  if (!historyPath.toLowerCase().startsWith(expectedPrefix)) {
    return { ok: false, error: "history-unavailable", confUid, historyUid, title, messages: [] };
  }

  try {
    if (!fs.existsSync(historyPath)) {
      return { ok: true, confUid, historyUid, title, messages: [] };
    }
    const payload = JSON.parse(fs.readFileSync(historyPath, "utf8"));
    if (!Array.isArray(payload)) {
      return { ok: false, error: "history-invalid", confUid, historyUid, title, messages: [] };
    }

    const messages = payload
      .filter((item) => item && typeof item === "object")
      .map((item) => ({
        role: String(item.role || "").trim().toLowerCase(),
        timestamp: String(item.timestamp || "").trim(),
        content: normalizeHistoryContent(item.content)
      }))
      .filter((item) => item.role && item.role !== "metadata" && item.content)
      .slice(-120);

    return { ok: true, confUid, historyUid, title, messages };
  } catch (error) {
    petLog("work-panel-history-read-failed", error);
    return { ok: false, error: "history-unavailable", confUid, historyUid, title, messages: [] };
  }
}

function getBriefingStatePayload() {
  const data = briefingStore ? briefingStore.getData() : null;
  const pendingMemoryCount = data
    ? data.memoryCandidates.filter((candidate) => candidate.status === "pending").length
    : 0;
  return {
    ok: true,
    aiState: latestFrontendState.aiState || "idle",
    wsConnected: Boolean(latestFrontendState.wsConnected),
    confName: latestFrontendState.confName || "",
    confUid: latestFrontendState.confUid || "",
    currentHistoryUid: latestFrontendState.currentHistoryUid || "",
    currentHistoryTitle: latestFrontendState.currentHistoryTitle || "",
    latestAssistantText: latestFrontendState.latestAssistantText || "",
    forceIgnoreMouse: Boolean(appState.forceIgnoreMouse),
    petGameMode: Boolean(appState.petGameMode),
    currentOutfitId: latestFrontendState.currentOutfitId || appState.outfit?.outfitId || "normal",
    currentExpressionId: latestFrontendState.currentExpressionId || appState.expression?.expressionId || "neutral",
    currentExpressionLabel: latestFrontendState.currentExpressionLabel || appState.expression?.expressionLabel || "一般",
    micEnabled: Boolean(latestFrontendState.micEnabled),
    micPaused: Boolean(latestFrontendState.micPaused),
    cameraEnabled: Boolean(latestFrontendState.cameraEnabled),
    screenEnabled: Boolean(latestFrontendState.screenEnabled),
    browserPanelEnabled: Boolean(latestFrontendState.browserPanelEnabled),
    briefingVisible: isBriefingWindowVisible(),
    briefingDate: data?.snapshot?.date || "",
    briefingUpdatedAt: data?.snapshot?.updatedAt || data?.updatedAt || "",
    mailBriefing: mailBriefingService ? mailBriefingService.readStatus() : null,
    pendingMemoryCount,
    updatedAt: new Date().toISOString()
  };
}

function getBriefingDataPayload() {
  if (!briefingStore) {
    return {
      ok: false,
      error: "Briefing store is not ready."
    };
  }

  return {
    ok: true,
    ...briefingStore.getData()
  };
}

function readMailBriefingStatus() {
  return mailBriefingService ? mailBriefingService.readStatus() : null;
}

function readMailPreferences() {
  if (!mailBriefingService) {
    return {
      ok: false,
      error: "Mail briefing service is not ready."
    };
  }
  return mailBriefingService.readPreferences();
}

function saveMailPreferences(preferences) {
  if (!mailBriefingService) {
    return {
      ok: false,
      error: "Mail briefing service is not ready."
    };
  }
  const result = mailBriefingService.savePreferences(preferences);
  broadcastBriefingState();
  return result;
}

function readMailRules() {
  if (!mailBriefingService) {
    return {
      ok: false,
      error: "Mail briefing service is not ready."
    };
  }
  return mailBriefingService.readRules();
}

function saveMailRules(rulesPayload) {
  if (!mailBriefingService) {
    return {
      ok: false,
      error: "Mail briefing service is not ready."
    };
  }
  const result = mailBriefingService.saveRules(rulesPayload);
  broadcastBriefingState();
  return result;
}

async function readMailMessage(messageId) {
  if (!mailBriefingService) {
    return {
      ok: false,
      error: "Mail briefing service is not ready."
    };
  }
  return mailBriefingService.readMessage(messageId);
}

async function refreshMailBriefing() {
  if (!mailBriefingService) {
    return {
      ok: false,
      error: "Mail briefing service is not ready."
    };
  }
  const result = await mailBriefingService.refreshOnce();
  broadcastBriefingState();
  return result;
}

function broadcastReaderState() {
  const targets = [readerWindow, briefingWindow];
  for (const target of targets) {
    if (!target || target.isDestroyed()) {
      continue;
    }
    try {
      target.webContents.send("reader-state", getReaderStatePayload());
    } catch (error) {
      petLog("reader-state-broadcast-failed", error);
    }
  }
}

function broadcastBriefingState() {
  if (!briefingWindow || briefingWindow.isDestroyed()) {
    return;
  }
  try {
    briefingWindow.webContents.send("briefing-state", getBriefingStatePayload());
  } catch (error) {
    petLog("briefing-state-broadcast-failed", error);
  }
}

function broadcastBriefingData() {
  if (!briefingWindow || briefingWindow.isDestroyed()) {
    return;
  }
  try {
    briefingWindow.webContents.send("briefing-data", getBriefingDataPayload());
  } catch (error) {
    petLog("briefing-data-broadcast-failed", error);
  }
}

function scheduleStudySnapshotBroadcast() {
  if (studySnapshotBroadcastTimer) {
    clearTimeout(studySnapshotBroadcastTimer);
  }
  studySnapshotBroadcastTimer = setTimeout(() => {
    studySnapshotBroadcastTimer = null;
    broadcastBriefingData();
  }, 350);
}

function startStudySnapshotWatcher() {
  if (studySnapshotWatcher) {
    return;
  }
  const studyDir = path.dirname(studySnapshotPath);
  if (!fs.existsSync(studyDir)) {
    return;
  }
  try {
    studySnapshotWatcher = fs.watch(studyDir, (_eventType, filename) => {
      if (!filename || String(filename) === path.basename(studySnapshotPath)) {
        scheduleStudySnapshotBroadcast();
      }
    });
  } catch (error) {
    petLog("study-snapshot-watch-failed", error);
  }
}

function updateFrontendState(patch = {}) {
  latestFrontendState = {
    ...latestFrontendState,
    ...(patch || {})
  };
  broadcastReaderState();
  broadcastBriefingState();
}

function broadcast(channel, payload) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send(channel, payload);
}

function broadcastPetCursorPoint(force = false) {
  if (!mainWindow || mainWindow.isDestroyed() || appState.mode !== "pet") {
    return;
  }

  const point = screen.getCursorScreenPoint();
  const now = Date.now();
  const unchanged =
    lastPetCursorPoint &&
    lastPetCursorPoint.x === point.x &&
    lastPetCursorPoint.y === point.y;
  if (!force && unchanged && now - lastPetCursorPoint.sentAt < PET_CURSOR_HEARTBEAT_MS) {
    return;
  }

  lastPetCursorPoint = { x: point.x, y: point.y, sentAt: now };
  broadcast("pet-command", {
    type: "pet-pointer-set",
    screenPoint: { x: point.x, y: point.y }
  });
}

function startPetCursorTracking() {
  if (petCursorBroadcastTimer) {
    return;
  }
  broadcastPetCursorPoint(true);
  petCursorBroadcastTimer = setInterval(
    () => broadcastPetCursorPoint(false),
    PET_CURSOR_POLL_MS
  );
  petCursorBroadcastTimer.unref?.();
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

async function captureLive2DPreview(options = {}) {
  if (live2dPreviewCaptureInFlight) {
    return live2dPreviewCaptureInFlight;
  }
  live2dPreviewCaptureInFlight = captureLive2DPreviewImpl(options);
  try {
    return await live2dPreviewCaptureInFlight;
  } finally {
    live2dPreviewCaptureInFlight = null;
  }
}

async function captureLive2DPreviewImpl(options = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return null;
  }
  try {
    const dataUrl = await executeRenderer(`((options) => {
      if (window.__kuroLive2DPreview && typeof window.__kuroLive2DPreview.capture === "function") {
        return Promise.race([
          window.__kuroLive2DPreview.capture(options),
          new Promise((resolve) => setTimeout(() => resolve(null), 4200))
        ]);
      }
      return null;
    })(${JSON.stringify(options || {})});`);
    const pngPrefix = "data:image/png;base64,";
    if (typeof dataUrl === "string" && dataUrl.startsWith(pngPrefix)) {
      return Buffer.from(dataUrl.slice(pngPrefix.length), "base64");
    }

    await executeRenderer(`new Promise((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)));
    });`);
    const image = await mainWindow.webContents.capturePage();
    if (!image || image.isEmpty()) {
      return null;
    }
    return image.toPNG();
  } catch (error) {
    petLog("live2d-preview-capture-failed", error);
    return null;
  }
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

async function setFrontendInputEnabled(kind, enabled) {
  const normalizedKind = String(kind || "").trim();
  if (!["microphone", "camera", "screen", "browser"].includes(normalizedKind)) {
    return { ok: false, error: "unsupported-input-kind" };
  }
  const result = await executeRenderer(`((kind, enabled) => {
    if (typeof window.__kuroPetSetInputEnabled !== "function") {
      return { ok: false, error: "frontend-input-bridge-missing" };
    }
    return window.__kuroPetSetInputEnabled(kind, enabled);
  })(${JSON.stringify(normalizedKind)}, ${JSON.stringify(Boolean(enabled))});`);
  return result && typeof result === "object" ? result : { ok: false, error: "renderer-unavailable" };
}

async function controlFrontendMicrophone(action) {
  const normalizedAction = String(action || "").trim().toLowerCase();
  if (!["start", "pause", "resume", "submit", "cancel"].includes(normalizedAction)) {
    return { ok: false, error: "unsupported-microphone-action" };
  }
  const result = await executeRenderer(`((action) => {
    if (typeof window.__kuroPetControlMicrophone !== "function") {
      return { ok: false, error: "frontend-microphone-bridge-missing" };
    }
    return window.__kuroPetControlMicrophone(action);
  })(${JSON.stringify(normalizedAction)});`);
  return result && typeof result === "object" ? result : { ok: false, error: "renderer-unavailable" };
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

function isBriefingWindowVisible() {
  return Boolean(
    briefingWindow &&
      !briefingWindow.isDestroyed() &&
      briefingWindow.isVisible() &&
      !briefingWindow.isMinimized()
  );
}

function revealBriefingWindow() {
  if (!briefingWindow || briefingWindow.isDestroyed()) {
    return false;
  }

  const wasVisible = briefingWindow.isVisible();
  const wasMinimized = briefingWindow.isMinimized();
  if (wasMinimized) {
    briefingWindow.restore();
  }

  const currentBounds = briefingWindow.getBounds();
  const visibleBounds = clampBriefingBounds(currentBounds);
  if (
    currentBounds.x !== visibleBounds.x ||
    currentBounds.y !== visibleBounds.y ||
    currentBounds.width !== visibleBounds.width ||
    currentBounds.height !== visibleBounds.height
  ) {
    briefingWindow.setBounds(visibleBounds, false);
  }

  briefingWindow.show();
  briefingWindow.moveTop();
  if (process.platform === "win32") {
    app.focus({ steal: true });
  }
  briefingWindow.focus();
  petLog("work-panel-reveal", {
    wasVisible,
    wasMinimized,
    bounds: briefingWindow.getBounds(),
    focused: briefingWindow.isFocused()
  });
  return true;
}

function setBriefingVisible(visible) {
  appState.briefingVisible = Boolean(visible);
  if (!briefingWindow || briefingWindow.isDestroyed()) {
    if (appState.briefingVisible) {
      createBriefingWindow();
    }
  } else if (appState.briefingVisible) {
    revealBriefingWindow();
  } else {
    briefingWindow.hide();
  }
  updateTrayMenu();
  broadcastBriefingState();
  return {
    ok: true,
    route: "window",
    action: "set-briefing-visible",
    briefingVisible: isBriefingWindowVisible(),
    briefingPending: Boolean(appState.briefingVisible && !isBriefingWindowVisible())
  };
}

function replaceBriefingSnapshot(snapshot) {
  if (!briefingStore) {
    return {
      ok: false,
      error: "Briefing store is not ready."
    };
  }
  const data = briefingStore.replaceSnapshot(snapshot);
  broadcastBriefingData();
  broadcastBriefingState();
  return {
    ok: true,
    action: "set-briefing-snapshot",
    data
  };
}

function addBriefingMemoryCandidate(candidate) {
  if (!briefingStore) {
    return {
      ok: false,
      error: "Briefing store is not ready."
    };
  }
  const result = briefingStore.addMemoryCandidate(candidate);
  if (result.ok) {
    broadcastBriefingData();
    broadcastBriefingState();
  }
  return {
    action: "add-briefing-memory-candidate",
    ...result
  };
}

function setBriefingMemoryCandidateStatus(candidateId, status) {
  if (!briefingStore) {
    return {
      ok: false,
      error: "Briefing store is not ready."
    };
  }
  const result = briefingStore.setMemoryCandidateStatus(candidateId, status);
  if (result.ok) {
    broadcastBriefingData();
    broadcastBriefingState();
  }
  return {
    action: "set-briefing-memory-candidate-status",
    ...result
  };
}

async function handleControlAction(action, payload = {}) {
  switch (action) {
    case "mic-toggle":
      return { ...(await setFrontendInputEnabled("microphone", Boolean(payload.enabled))), action };
    case "mic-start":
      return { ...(await controlFrontendMicrophone("start")), action };
    case "mic-pause":
      return { ...(await controlFrontendMicrophone("pause")), action };
    case "mic-resume":
      return { ...(await controlFrontendMicrophone("resume")), action };
    case "mic-submit":
      return { ...(await controlFrontendMicrophone("submit")), action };
    case "mic-cancel":
      return { ...(await controlFrontendMicrophone("cancel")), action };
    case "interrupt":
      broadcast("pet-command", { type: "interrupt" });
      return { ok: true, route: "ipc", action };
    case "set-reader-visible":
      return setReaderVisible(Boolean(payload.enabled));
    case "set-briefing-visible":
      return setBriefingVisible(Boolean(payload.enabled));
    case "toggle-briefing":
      return setBriefingVisible(!isBriefingWindowVisible());
    case "set-briefing-snapshot":
      return replaceBriefingSnapshot(payload.snapshot || payload);
    case "add-briefing-memory-candidate":
      return addBriefingMemoryCandidate(payload.candidate || payload);
    case "set-briefing-memory-candidate-status":
      return setBriefingMemoryCandidateStatus(payload.id, String(payload.status || "pending"));
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
    case "send-text":
      return sendTextToFrontend(
        String(payload.text || ""),
        Array.isArray(payload.attachments) ? payload.attachments : []
      );
    case "toggle-subtitle":
      return setReaderVisible(!(readerWindow && !readerWindow.isDestroyed() && readerWindow.isVisible()));
    case "toggle-camera":
      return { ...(await setFrontendInputEnabled("camera", Boolean(payload.enabled))), action };
    case "toggle-screen":
      return { ...(await setFrontendInputEnabled("screen", Boolean(payload.enabled))), action };
    case "toggle-browser":
      return { ...(await setFrontendInputEnabled("browser", Boolean(payload.enabled))), action };
    case "reload-frontend":
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.reloadIgnoringCache();
      }
      if (readerWindow && !readerWindow.isDestroyed()) {
        readerWindow.webContents.reloadIgnoringCache();
      }
      if (briefingWindow && !briefingWindow.isDestroyed()) {
        briefingWindow.webContents.reloadIgnoringCache();
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
    case "reset-pet-position":
      return { ok: true, action, petAnchor: resetPetBoundsToDefault() };
    case "set-game-mode":
      return {
        ok: true,
        action,
        petGameMode: setPetGameMode(Boolean(payload.enabled))
      };
    case "set-force-ignore-mouse":
      return {
        ok: true,
        action,
        forceIgnoreMouse: setForceIgnoreMouse(Boolean(payload.enabled))
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
  clearPetInteractionState();
  const targetBounds = resolveTargetBoundsForMode(nextMode);

  if (nextMode === "pet") {
    ensurePetAnchor();
    mainWindow.setResizable(false);
    mainWindow.setMinimumSize(1, 1);
  } else {
    mainWindow.setResizable(true);
    mainWindow.setMinimumSize(960, 640);
  }

  applyMainWindowBounds(targetBounds, "mode-switch");
  applyPetWindowLayerPolicy({ reason: "apply-window-mode" });
  applyTaskbarPolicy();
  if (nextMode === "pet") {
    broadcastPetHostState("pet-host-set");
    broadcastPetTransformState();
  }
  saveCurrentState();
  applyIgnoreMouseState();
  updateTrayMenu();
}

function refreshLayoutForDisplayTopology(reason = "display-metrics-changed") {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  if (PET_FIXED_DESKTOP_SHELL && appState.mode === "pet") {
    rebuildFixedPetShellBounds();
  }
  const targetBounds = resolveTargetBoundsForMode(appState.mode);
  applyMainWindowBounds(
    targetBounds,
    appState.mode === "pet" ? "display-topology" : "window-topology"
  );

  if (appState.mode === "pet") {
    ensurePetAnchor();
    broadcastPetHostState("pet-host-set");
    saveCurrentState();
  } else {
    setBoundsForCurrentMode(targetBounds);
  }

  if (briefingWindow && !briefingWindow.isDestroyed()) {
    const briefingBounds = clampBriefingBounds(briefingWindow.getBounds());
    briefingWindow.setBounds(briefingBounds, false);
    setBriefingBounds(briefingBounds);
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

  applyMainWindowBounds(nextBounds, "window-next-display");
  setBoundsForCurrentMode(nextBounds);
}

function showMainWindow() {
  if (!mainWindow) {
    return;
  }
  showPetWindow();
}

function toggleForceIgnoreMouse() {
  return setForceIgnoreMouse(!appState.forceIgnoreMouse);
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
  if (readerWindow && !readerWindow.isDestroyed()) {
    readerWindow.webContents.reloadIgnoringCache();
  }
  if (briefingWindow && !briefingWindow.isDestroyed()) {
    briefingWindow.webContents.reloadIgnoringCache();
  }
}

function getMenuState() {
  return {
    forceIgnoreMouse: appState.forceIgnoreMouse,
    petGameMode: appState.petGameMode,
    readerVisible: appState.readerVisible,
    briefingVisible: isBriefingWindowVisible()
  };
}

function getMenuActions() {
  return {
    showPet: showMainWindow,
    toggleIgnoreMouse: toggleForceIgnoreMouse,
    toggleGameMode: togglePetGameMode,
    toggleReader: toggleReaderWindow,
    showBriefing: () => setBriefingVisible(true),
    interruptOutput: () => {
      handleControlAction("interrupt").catch((error) => petLog("menu-interrupt-failed", error));
    },
    moveNextDisplay: moveWindowToNextDisplay,
    resetPosition: resetPetBoundsToDefault,
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
    captureLive2DPreview,
    getShellStatus: () => ({
      service: CONTROL_SERVICE,
      protocolVersion: CONTROL_PROTOCOL_VERSION,
      pid: process.pid,
      instanceId: APP_INSTANCE_ID,
      startedAt: APP_STARTED_AT,
      mode: appState.mode,
      forceIgnoreMouse: appState.forceIgnoreMouse,
      petGameMode: appState.petGameMode,
      petMousePolicy: lastPetMousePolicy,
      petWindowPolicy:
        mainWindow && !mainWindow.isDestroyed()
          ? {
              ...lastPetWindowPolicy,
              actualAlwaysOnTop: mainWindow.isAlwaysOnTop(),
              actualFocusable: mainWindow.isFocusable(),
              visible: mainWindow.isVisible()
            }
          : null,
      petSpanAllDisplays: appState.petSpanAllDisplays,
      petHostMode: PET_HOST_MODE,
      petHostSizing: getPetHostSizingMode(),
      petFixedDesktopShell: PET_FIXED_DESKTOP_SHELL,
      petFixedShellBounds: PET_FIXED_DESKTOP_SHELL ? getFixedPetShellBounds() : null,
      petFixedShellBoundsWriteCount: fixedPetShellBoundsWriteCount,
      petFixedShellBoundsRejectedCount: fixedPetShellBoundsRejectedCount,
      petLastFixedShellBoundsWriteReason: lastFixedPetShellBoundsWriteReason,
      petLastFixedShellBoundsRejectedReason: lastFixedPetShellBoundsRejectedReason,
      petInteractionFreezeHost: PET_INTERACTION_FREEZE_HOST,
      petInteractionFreezeMode: "hold-pending",
      petInteractionActive: isPetInteractionActive(),
      petDragActive: petInteractionState.dragActive,
      petZoomActive: petInteractionState.zoomActive,
      petLastZoomRequestAt: petInteractionState.lastZoomRequestAt,
      petPendingInteractionHostBounds: pendingInteractionHostBounds
        ? { ...pendingInteractionHostBounds }
        : null,
      petHostRelocationSuppressedCount,
      petHostRelocationAppliedCount,
      petLastHostRelocationSuppressedReason: lastPetHostRelocationSuppressedReason,
      petLastHostRelocationAppliedReason: lastPetHostRelocationAppliedReason,
      petTransformRevision: ensurePetTransformState().revision,
      petEnvelopeTransformRevision: latestPetEnvelopeRevision || null,
      petZoomScale: ensurePetTransformState().zoomScale,
      petHostBounds: getPetHostBounds(),
      petModelScreenBounds: latestPetModelScreenBounds
        ? { ...latestPetModelScreenBounds }
        : null,
      petModelEnvelopeContained: !PET_FIXED_DESKTOP_SHELL && latestPetModelScreenBounds
        ? hostContainsBounds(
            getPetHostBounds(),
            {
              x: latestPetModelScreenBounds.left,
              y: latestPetModelScreenBounds.top,
              width: latestPetModelScreenBounds.width,
              height: latestPetModelScreenBounds.height
            }
          )
        : null,
      petModelEnvelopeContainedByNativeShell:
        PET_FIXED_DESKTOP_SHELL && latestPetModelScreenBounds
          ? hostContainsBounds(
              getFixedPetShellBounds(),
              {
                x: latestPetModelScreenBounds.left,
                y: latestPetModelScreenBounds.top,
                width: latestPetModelScreenBounds.width,
                height: latestPetModelScreenBounds.height
              }
            )
          : null,
      petAnchor: ensurePetTransformState().anchor,
      bounds: mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : null,
      nativeWindowBounds:
        mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : null,
      nativeContentBounds:
        mainWindow && !mainWindow.isDestroyed()
          ? mainWindow.getContentBounds()
          : null,
      briefingVisible: isBriefingWindowVisible(),
      briefingFocused: Boolean(
        briefingWindow && !briefingWindow.isDestroyed() && briefingWindow.isFocused()
      ),
      briefingMinimized: Boolean(
        briefingWindow && !briefingWindow.isDestroyed() && briefingWindow.isMinimized()
      ),
      briefingBounds:
        briefingWindow && !briefingWindow.isDestroyed() ? briefingWindow.getBounds() : null
    }),
    isReaderVisible: () => Boolean(appState.readerVisible),
    isBriefingVisible: isBriefingWindowVisible,
    readBriefingData: getBriefingDataPayload,
    readMailBriefingStatus,
    readMailPreferences,
    saveMailPreferences,
    readMailRules,
    saveMailRules,
    readMailMessage,
    refreshMailBriefing,
    replaceBriefingSnapshot,
    addBriefingMemoryCandidate,
    setBriefingMemoryCandidateStatus,
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

function createBriefingWindow() {
  if (briefingWindow && !briefingWindow.isDestroyed()) {
    if (appState.briefingVisible) {
      revealBriefingWindow();
    }
    return;
  }

  const bounds = clampBriefingBounds(getBriefingBounds());
  briefingWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    minWidth: MIN_BRIEFING_WINDOW_WIDTH,
    minHeight: MIN_BRIEFING_WINDOW_HEIGHT,
    show: false,
    frame: false,
    transparent: false,
    backgroundColor: "#11151f",
    resizable: true,
    maximizable: true,
    minimizable: true,
    skipTaskbar: false,
    fullscreenable: true,
    alwaysOnTop: false,
    title: "Kuro 工作面板",
    icon: iconPath,
    autoHideMenuBar: true,
    webPreferences: {
      preload: briefingPreloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false
    }
  });

  briefingWindow.setMenuBarVisibility(false);

  briefingWindow.on("move", () => {
    if (!briefingWindow || briefingWindow.isDestroyed()) {
      return;
    }
    setBriefingBounds(briefingWindow.getBounds());
  });

  briefingWindow.on("resize", () => {
    if (!briefingWindow || briefingWindow.isDestroyed()) {
      return;
    }
    setBriefingBounds(briefingWindow.getBounds());
  });

  briefingWindow.on("show", () => {
    appState.briefingVisible = true;
    saveCurrentState();
    broadcastBriefingState();
    updateTrayMenu();
  });

  briefingWindow.on("hide", () => {
    appState.briefingVisible = false;
    saveCurrentState();
    broadcastBriefingState();
    updateTrayMenu();
  });

  briefingWindow.on("minimize", () => {
    appState.briefingVisible = false;
    saveCurrentState();
    broadcastBriefingState();
    updateTrayMenu();
  });

  briefingWindow.on("restore", () => {
    appState.briefingVisible = true;
    saveCurrentState();
    broadcastBriefingState();
    updateTrayMenu();
  });

  briefingWindow.on("close", (event) => {
    if (appIsQuitting || !briefingWindow || briefingWindow.isDestroyed()) {
      return;
    }
    event.preventDefault();
    briefingWindow.hide();
    petLog("work-panel-hidden", { reason: "close-request" });
  });

  briefingWindow.on("closed", () => {
    briefingWindow = null;
    appState.briefingVisible = false;
    saveCurrentState();
    broadcastBriefingState();
    updateTrayMenu();
  });

  briefingWindow.once("ready-to-show", () => {
    if (appState.briefingVisible) {
      revealBriefingWindow();
    }
  });

  briefingWindow.webContents.on("did-finish-load", () => {
    broadcastReaderState();
    broadcastBriefingState();
    broadcastBriefingData();
    if (appState.briefingVisible) {
      revealBriefingWindow();
    }
  });

  briefingWindow.loadFile(workPanelEntry).catch((error) => {
    petLog("Failed to load work panel", error);
    appState.briefingVisible = false;
    saveCurrentState();
    broadcastBriefingState();
    updateTrayMenu();
    if (briefingWindow && !briefingWindow.isDestroyed()) {
      briefingWindow.destroy();
    }
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
    alwaysOnTop: appState.mode === "pet",
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
    petHostMode: PET_HOST_MODE,
    petAnchor: ensurePetAnchor(),
    backendBaseUrl: process.env.KURO_BACKEND_BASE_URL || null,
    backendWsUrl: process.env.KURO_BACKEND_WS_URL || null
  });

  mainWindow.setMenuBarVisibility(false);
  applyWindowMode(appState.mode, { force: true });
  scheduleTaskbarPolicyRefresh();
  mainWindow.on("show", () => {
    scheduleTaskbarPolicyRefresh();
    schedulePetWindowLayerRefresh("pet-window-show-event", { moveTop: appState.mode === "pet" });
  });
  mainWindow.on("restore", () => {
    scheduleTaskbarPolicyRefresh();
    schedulePetWindowLayerRefresh("pet-window-restore-event", { moveTop: appState.mode === "pet" });
  });
  mainWindow.on("always-on-top-changed", (_event, isAlwaysOnTop) => {
    if (appState.mode !== "pet" || isAlwaysOnTop || petWindowLayerRepairScheduled) {
      return;
    }
    petWindowLayerRepairScheduled = true;
    setTimeout(() => {
      petWindowLayerRepairScheduled = false;
      if (mainWindow && !mainWindow.isDestroyed() && appState.mode === "pet") {
        schedulePetWindowLayerRefresh("always-on-top-lost", { moveTop: true });
      }
    }, 0);
  });

  mainWindow.on("move", () => {
    if (
      mainWindow &&
      !mainWindow.isDestroyed() &&
      !(PET_FIXED_DESKTOP_SHELL && appState.mode === "pet")
    ) {
      setBoundsForCurrentMode(mainWindow.getBounds());
    }
  });

  mainWindow.on("resize", () => {
    if (
      mainWindow &&
      !mainWindow.isDestroyed() &&
      !(PET_FIXED_DESKTOP_SHELL && appState.mode === "pet")
    ) {
      setBoundsForCurrentMode(mainWindow.getBounds());
    }
  });

  mainWindow.on("close", (event) => {
    if (appIsQuitting || !mainWindow || mainWindow.isDestroyed()) {
      return;
    }
    event.preventDefault();
    mainWindow.hide();
    petLog("pet-window-hidden", { reason: "close-request" });
  });

  mainWindow.on("closed", () => {
    clearPetInteractionState();
    lastPetMousePolicy = null;
    lastPetWindowPolicy = null;
    petWindowLayerRefreshGeneration += 1;
    petWindowLayerRepairScheduled = false;
    mainWindow = null;
  });

  mainWindow.on("maximize", () => broadcast("window-maximized-change", true));
  mainWindow.on("unmaximize", () => broadcast("window-maximized-change", false));
  mainWindow.on("enter-full-screen", () => broadcast("window-fullscreen-change", true));
  mainWindow.on("leave-full-screen", () => broadcast("window-fullscreen-change", false));

  mainWindow.webContents.on("did-finish-load", () => {
    petLog("did-finish-load");
    broadcastPetCursorPoint(true);
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
    failClosedPetInteraction("renderer-load-failed");
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
    failClosedPetInteraction("renderer-process-gone");
  });

  mainWindow.webContents.on("unresponsive", () => {
    petLog("renderer-unresponsive");
    failClosedPetInteraction("renderer-unresponsive");
  });

  mainWindow.webContents.on("before-input-event", (_event, input) => {
    if (input.type !== "keyDown") {
      return;
    }

    if (input.key === "F10") {
      toggleForceIgnoreMouse();
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
    const transform = ensurePetTransformState();
    event.returnValue = {
      baseUrl: process.env.KURO_BACKEND_BASE_URL || "http://127.0.0.1:23456",
      wsUrl: process.env.KURO_BACKEND_WS_URL || "ws://127.0.0.1:23456/client-ws",
      zoomScale: transform.zoomScale,
      petTransformRevision: transform.revision,
      petHostMode: PET_HOST_MODE,
      petFixedDesktopShell: PET_FIXED_DESKTOP_SHELL,
      petShellBounds: PET_FIXED_DESKTOP_SHELL ? getFixedPetShellBounds() : null,
      petHostBounds: getPetHostBounds(),
      petAnchor: transform.anchor,
      cursorScreenPoint: screen.getCursorScreenPoint(),
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

  ipcMain.on("pet-model-envelope", (_event, payload) => {
    handlePetModelEnvelope(payload);
  });

  ipcMain.on("pet-transform-request", (_event, payload) => {
    handlePetTransformRequest(payload);
  });

  ipcMain.on("set-mode", (_event, mode) => {
    const nextMode = mode === "window" ? "window" : "pet";
    applyWindowMode(nextMode);
    saveCurrentState();
  });

  ipcMain.on("toggle-force-ignore-mouse", () => {
    toggleForceIgnoreMouse();
  });

  ipcMain.on("set-ignore-mouse-event", (_event, ignore) => {
    updateComponentHoverLease("live2d-hit-test", !ignore);
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

  ipcMain.handle("work-panel-get-chat-history", async () => {
    const result = await launcherControlRequest("/v1/history");
    return result?.ok ? result : getActiveChatHistoryPayload();
  });

  ipcMain.handle("work-panel-get-profile", () => launcherControlRequest("/v1/profile"));
  ipcMain.handle("work-panel-apply-profile", async (_event, payload) => {
    const confirmed = await confirmWorkPanelAction({
      title: "套用助理設定",
      message: "要切換目前的角色、專案、模型或推理深度嗎？",
      detail: "Kuro 可能會重新載入 TTS 與對話 runtime；目前對話仍會保存在本機。"
    });
    if (!confirmed) return { ok: false, cancelled: true, error: "cancelled" };
    return launcherControlRequest("/v1/profile/apply", {
      method: "POST",
      payload: { ...(payload || {}), confirmed: true }
    });
  });
  ipcMain.handle("work-panel-get-histories", (_event, historyUid) => {
    const suffix = String(historyUid || "").trim();
    return launcherControlRequest(`/v1/history${suffix ? `?history_uid=${encodeURIComponent(suffix)}` : ""}`);
  });
  ipcMain.handle("work-panel-create-history", () =>
    launcherControlRequest("/v1/history/create", { method: "POST", payload: {} })
  );
  ipcMain.handle("work-panel-select-history", (_event, historyUid) =>
    launcherControlRequest("/v1/history/select", { method: "POST", payload: { history_uid: historyUid } })
  );
  ipcMain.handle("work-panel-delete-history", async (_event, historyUid, historyTitle) => {
    const confirmed = await confirmWorkPanelAction({
      title: "刪除對話",
      message: `確定要刪除「${String(historyTitle || "這段對話")}」嗎？`,
      detail: "這會刪除本機對話檔；若刪除目前對話，Kuro 會自動建立一段新對話。"
    });
    if (!confirmed) return { ok: false, cancelled: true, error: "cancelled" };
    return launcherControlRequest("/v1/history/delete", {
      method: "POST",
      payload: { history_uid: historyUid, confirmed: true }
    });
  });
  ipcMain.handle("work-panel-get-memories", () => launcherControlRequest("/v1/memories"));
  ipcMain.handle("work-panel-memory-action", async (_event, action, payload) => {
    const routes = new Map([
      ["add", "/v1/memory/add"],
      ["status", "/v1/memory/status"],
      ["delete", "/v1/memory/delete"],
      ["compact", "/v1/memory/compact"]
    ]);
    const normalizedAction = String(action || "");
    const route = routes.get(normalizedAction);
    if (!route) return { ok: false, error: "work-panel-memory-action-not-allowed" };
    const labels = {
      add: ["新增長期記憶", "要把這段內容加入目前角色的長期記憶嗎？"],
      status: ["變更記憶狀態", "要變更這條長期記憶的啟用狀態嗎？"],
      delete: ["刪除長期記憶", "確定要永久刪除這條長期記憶嗎？"],
      compact: ["整理長期記憶", "要整理並合併目前角色的長期記憶嗎？"]
    };
    const [title, message] = labels[normalizedAction];
    const confirmed = await confirmWorkPanelAction({
      title,
      message,
      detail: "這項操作會寫入 Kuro 的本機記憶資料，完成後會刷新目前 runtime 的記憶 prompt。"
    });
    if (!confirmed) return { ok: false, cancelled: true, error: "cancelled" };
    return launcherControlRequest(route, {
      method: "POST",
      payload: { ...(payload || {}), confirmed: true }
    });
  });
  ipcMain.handle("work-panel-get-tools", () => launcherControlRequest("/v1/tools"));

  ipcMain.handle("work-panel-control", async (_event, action, payload) => {
    const allowedActions = new Set([
      "interrupt",
      "show-pet",
      "move-next-display",
      "reset-pet-position",
      "set-game-mode",
      "set-force-ignore-mouse",
      "mic-toggle",
      "mic-start",
      "mic-pause",
      "mic-resume",
      "mic-submit",
      "mic-cancel",
      "toggle-camera",
      "toggle-screen",
      "toggle-browser",
      "set-outfit",
      "set-expression",
      "play-motion"
    ]);
    const normalizedAction = String(action || "").trim();
    if (!allowedActions.has(normalizedAction)) {
      return { ok: false, error: "work-panel-action-not-allowed" };
    }
    return handleControlAction(normalizedAction, payload && typeof payload === "object" ? payload : {});
  });

  ipcMain.on("reader-close", () => {
    if (readerWindow && !readerWindow.isDestroyed()) {
      readerWindow.hide();
    }
  });

  ipcMain.handle("briefing-get-state", () => getBriefingStatePayload());
  ipcMain.handle("briefing-get-data", () => getBriefingDataPayload());
  ipcMain.handle("briefing-refresh-mail", async () => refreshMailBriefing());
  ipcMain.handle("briefing-get-mail-preferences", () => readMailPreferences());
  ipcMain.handle("briefing-save-mail-preferences", (_event, preferences) => saveMailPreferences(preferences));
  ipcMain.handle("briefing-get-mail-rules", () => readMailRules());
  ipcMain.handle("briefing-save-mail-rules", (_event, rulesPayload) => saveMailRules(rulesPayload));
  ipcMain.handle("briefing-get-mail-message", (_event, messageId) => readMailMessage(messageId));

  ipcMain.on("briefing-close", () => {
    if (briefingWindow && !briefingWindow.isDestroyed()) {
      briefingWindow.hide();
    }
  });

  ipcMain.on("briefing-minimize", () => {
    if (briefingWindow && !briefingWindow.isDestroyed()) {
      briefingWindow.minimize();
    }
  });

  ipcMain.on("briefing-toggle-maximize", () => {
    if (!briefingWindow || briefingWindow.isDestroyed()) {
      return;
    }
    if (briefingWindow.isMaximized()) {
      briefingWindow.unmaximize();
    } else {
      briefingWindow.maximize();
    }
  });

  ipcMain.on("update-component-hover", (_event, componentName, hovered) => {
    if (typeof componentName !== "string" || !componentName) {
      return;
    }
    updateComponentHoverLease(componentName, Boolean(hovered));
    applyIgnoreMouseState();
  });

  ipcMain.on("start-window-drag", (_event, payload) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    if (appState.mode === "pet") {
      if (hoveredComponents.get("live2d-model")) {
        setPetDragInteractionActive(true);
      }
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

    updateComponentHoverLease("pet-window-drag", true);
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

    applyMainWindowBounds(nextBounds, "window-drag");
    setBoundsForCurrentMode(nextBounds);
  });

  ipcMain.on("adjust-pet-window-scale", (_event, payload) => {
    adjustPetWindowScale(Number(payload?.scaleRatio));
  });

  ipcMain.on("set-pet-window-zoom", (_event, payload) => {
    setPetWindowZoom(Number(payload?.zoomScale));
  });

  ipcMain.on("set-pet-model-zoom", (_event, payload) => {
    setPetModelZoom(Number(payload?.zoomScale), {
      pivotScreenPoint: payload?.pivotScreenPoint,
      deferSave: true
    });
  });

  ipcMain.on("set-pet-anchor", (_event, payload) => {
    handlePetTransformRequest({
      kind: "anchor",
      requestedAnchor: { x: Number(payload?.x), y: Number(payload?.y) },
      requestId: payload?.requestId
    });
  });

  ipcMain.on("end-window-drag", () => {
    activeWindowDrag = null;
    setPetDragInteractionActive(false);
    flushPetAnchorSave();
    updateComponentHoverLease("pet-window-drag", false);
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
    if (appState.briefingVisible) {
      revealBriefingWindow();
    }
  });

  app.whenReady().then(() => {
    session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
      callback(permission === "media" || permission === "display-capture");
    });
    statePath = path.join(app.getPath("userData"), "pet-shell-state.json");
    briefingStorePath = path.join(app.getPath("userData"), "briefing-store.json");
    appState = mergeState(loadState(statePath));
    briefingStore = createBriefingStore({
      storePath: briefingStorePath,
      studySnapshotPath,
      log: petLog
    });
    latestFrontendState.currentOutfitId = appState.outfit.outfitId;
    latestFrontendState.currentOutfitParameterId = appState.outfit.parameterId;
    latestFrontendState.currentOutfitParameterIndex = appState.outfit.parameterIndex;
    latestFrontendState.currentOutfitValue = appState.outfit.value;
    latestFrontendState.currentExpressionId = appState.expression.expressionId;
    latestFrontendState.currentExpressionLabel = appState.expression.expressionLabel;
    appState.mode = "pet";
    appState.forceIgnoreMouse = true;
    appState.petSpanAllDisplays = false;
    appState.readerVisible = false;
    appState.briefingVisible = false;
    appState.petZoomScale = normalizePetZoomScale(appState.petZoomScale);
    ensurePetAnchor();
    petTransformState = createPetTransformState(
      {
        revision: 1,
        anchor: appState.petAnchor,
        zoomScale: appState.petZoomScale
      },
      {
        minZoomScale: MIN_PET_ZOOM_SCALE,
        maxZoomScale: MAX_PET_ZOOM_SCALE
      }
    );
    saveCurrentState();
    petLog("app-ready", { statePath, briefingStorePath, appState });

    registerIpc();
    startControlServer();
    mailBriefingService = createMailBriefingService({
      repoRoot,
      controlHost: CONTROL_HOST,
      controlPort: CONTROL_PORT,
      log: petLog,
      onStatusChange: broadcastBriefingState
    });
    mailBriefingService.start();
    createTray();
    createWindow();
    startPetCursorTracking();
    startPetInteractionLeaseWatchdog();
    if (appState.readerVisible) {
      createReaderWindow();
    }
    if (appState.briefingVisible) {
      createBriefingWindow();
    }
    startStudySnapshotWatcher();

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
    if (appState.readerVisible && !readerWindow) {
      createReaderWindow();
    }
    if (appState.briefingVisible) {
      if (!briefingWindow) {
        createBriefingWindow();
      } else {
        revealBriefingWindow();
      }
    }
  });

  app.on("window-all-closed", () => {
    petLog("all-windows-closed", { trayResident: true });
  });

  app.on("before-quit", () => {
    appIsQuitting = true;
    flushPetAnchorSave();
    clearPetHostShrinkTimer();
    clearPetInteractionTimer();
    if (mailBriefingService) {
      try {
        mailBriefingService.stop();
      } catch (error) {
        petLog("mail-briefing-service-stop-error", error);
      }
      mailBriefingService = null;
    }
    if (controlServer) {
      try {
        controlServer.close();
      } catch (error) {
        petLog("control-server-close-error", error);
      }
      controlServer = null;
    }
    if (studySnapshotBroadcastTimer) {
      clearTimeout(studySnapshotBroadcastTimer);
      studySnapshotBroadcastTimer = null;
    }
    if (studySnapshotWatcher) {
      try {
        studySnapshotWatcher.close();
      } catch (error) {
        petLog("study-snapshot-watch-close-error", error);
      }
      studySnapshotWatcher = null;
    }
    if (petCursorBroadcastTimer) {
      clearInterval(petCursorBroadcastTimer);
      petCursorBroadcastTimer = null;
    }
    stopPetInteractionLeaseWatchdog();
  });
}

