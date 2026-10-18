const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const {
  app,
  BrowserWindow,
  desktopCapturer,
  ipcMain,
  screen,
  session
} = require("electron");
const { protocol, net } = require('electron');
const { normalizePresentation, registerModelProtocol } = require('./main-process/local-model');
const { repairPlacement } = require('./main-process/pet-visibility');
const { withTimeout, petCapability } = require('./main-process/pet-status');
protocol.registerSchemesAsPrivileged([{ scheme: 'kuro-model', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } }]);
let localPresentation = null;
let modelRequestedAt = Date.now();
let runtimeCapabilities = { pet: { state: 'loading', responsive: false } };
let latestPetCapabilityInspector = null;
let latestPetCapabilityObservedAt = 0;
let capabilityRefreshPending = false;
let petPlacementRecoveryReason = 'startup';

async function refreshRuntimeCapabilities() {
  if (capabilityRefreshPending) return;
  capabilityRefreshPending = true;
  try {
    const inspector = await withTimeout(readLive2DInspectorSnapshot(), 600, null);
    latestPetCapabilityInspector = inspector;
    latestPetCapabilityObservedAt = Date.now();
    runtimeCapabilities = { pet: petCapability(inspector, localPresentation,
      Date.now() - modelRequestedAt, getAllDisplays(), readNativeContentBounds(mainWindow), isPetNativeWindowVisible()) };
  } finally { capabilityRefreshPending = false; }
}

const { cloneDefaultState, loadState, mergeState, saveState } = require("./state");
const { startControlServer: createControlServer } = require("./main-process/control-server");
const { createPetContextMenu } = require("./main-process/menus");
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
  readNativeContentBounds,
  reconcileFixedPetShell,
  resolveFixedDesktopShellBounds
} = require("./main-process/pet-fixed-shell");

const APP_NAME = "Kuro Pet Electron";
const APP_USER_MODEL_ID = "kuro.desktop-agent";
const CONTROL_SERVICE = "kuro-pet-control";
const CONTROL_PROTOCOL_VERSION = 1;
const APP_STARTED_AT = new Date().toISOString();
const APP_INSTANCE_ID = process.env.KURO_PET_INSTANCE_ID || `${process.pid}-${Date.now().toString(36)}`;
const TEMP_MAX_RENDER_PERFORMANCE = false;
const CONTROL_HOST = process.env.KURO_PET_CONTROL_HOST || "127.0.0.1";
const CONTROL_PORT = Number(process.env.KURO_PET_CONTROL_PORT || "23567");
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
const iconPath = path.join(projectRoot, "src", "assets", "favicon.ico");
const MIN_PET_ZOOM_SCALE = 0.2;
const MAX_PET_ZOOM_SCALE = 8;
const MIN_PET_WINDOW_WIDTH = 280;
const MIN_PET_WINDOW_HEIGHT = 420;

let mainWindow = null;
let appState = cloneDefaultState();
let statePath = "";
let hoveredComponents = new Map();
let componentHoverLeaseAt = new Map();
let activeWindowDrag = null;
let lastPetMousePolicy = null;
let lastPetWindowPolicy = null;
let petWindowLayerRefreshGeneration = 0;
let petWindowLayerRepairScheduled = false;
let controlServer = null;
let petCursorBroadcastTimer = null;
let petInteractionLeaseTimer = null;
let lastPetCursorPoint = null;
let petAnchorSaveTimer = null;
let petHostShrinkTimer = null;
let pendingPetHostShrinkBounds = null;
let currentPetHostBounds = null;
let currentFixedPetShellBounds = null;
let fixedPetShellReconciliation = { state: "unknown", actualBounds: null, fallbackAttempted: false };
let pendingFixedPetShellTopology = false;
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
  wsUrl: process.env.KURO_BACKEND_WS_URL || "",
  baseUrl: process.env.KURO_BACKEND_BASE_URL || "",
  confName: "",
  confUid: "",
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

function setBoundsForCurrentMode() {
  saveCurrentState();
}

function getWindowBoundsForMode(mode) {
  return appState.boundsByMode.pet;
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
  return currentFixedPetShellBounds
    ? { ...currentFixedPetShellBounds }
    : resolveFixedDesktopShellBounds(getAllDisplays());
}

function isPetNativeWindowVisible() {
  try {
    return Boolean(mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible() && !mainWindow.isMinimized());
  } catch {
    return false;
  }
}

function observePetCapability() {
  const inspector = Date.now() - latestPetCapabilityObservedAt <= 6000
    && latestPetCapabilityInspector?.transformRevision === petTransformState?.revision
    ? latestPetCapabilityInspector : null;
  return petCapability(inspector, localPresentation, Date.now() - modelRequestedAt,
    getAllDisplays(), readNativeContentBounds(mainWindow), isPetNativeWindowVisible());
}

function reconcilePetNativeShell(reason) {
  if (!PET_FIXED_DESKTOP_SHELL || !mainWindow || mainWindow.isDestroyed()) return;
  if (isPetInteractionActive()) {
    pendingFixedPetShellTopology = true;
    return;
  }
  pendingFixedPetShellTopology = false;
  rebuildFixedPetShellBounds();
  fixedPetShellReconciliation = reconcileFixedPetShell({
    window: mainWindow,
    displays: getAllDisplays(),
    anchor: ensurePetTransformState().anchor,
    reason,
    applyBounds: applyMainWindowBounds
  });
  petLog("fixed-pet-shell-readback", { reason, ...fixedPetShellReconciliation });
  broadcastPetHostState();
}

function flushPendingFixedPetShellTopology() {
  if (pendingFixedPetShellTopology && !isPetInteractionActive()) {
    reconcilePetNativeShell("display-topology");
  }
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
    return readNativeContentBounds(mainWindow);
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
    const actual = mainWindow.getBounds();
    const changed = actual.x !== current.x || actual.y !== current.y
      || actual.width !== current.width || actual.height !== current.height;
    fixedPetShellBoundsWriteCount += changed ? 1 : 0;
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
    petShellBounds: PET_FIXED_DESKTOP_SHELL ? getPetHostBounds() : null,
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
  flushPendingFixedPetShellTopology();
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
    flushPendingFixedPetShellTopology();
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
  // Envelope heartbeats are observations, not permission to move the pet.
  // Recover once after startup/topology changes, before any user positioning.
  if (!PET_FIXED_DESKTOP_SHELL && petPlacementRecoveryReason && !isPetInteractionActive()) {
    const reason = petPlacementRecoveryReason;
    petPlacementRecoveryReason = '';
    const repaired = repairPlacement(transform.anchor, getAllDisplays(), modelScreenBounds);
    if (Math.abs(repaired.x - transform.anchor.x) > 2 || Math.abs(repaired.y - transform.anchor.y) > 2) {
      commitPetTransformValues({ anchor: repaired }, { broadcast: true });
      petLog('pet-position-recovered', { reason });
      return true;
    }
  }
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


function resolveTargetBoundsForMode() {
  ensurePetAnchor();
  return PET_FIXED_DESKTOP_SHELL ? getFixedPetShellBounds() : getPetHostBounds();
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
  flushPendingFixedPetShellTopology();
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
  petPlacementRecoveryReason = '';
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


function updateFrontendState(patch = {}) {
  latestFrontendState = {
    ...latestFrontendState,
    ...(patch || {})
  };
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
  const state = await executeRenderer("window.__kuroPetRendererState || null");
  if (!state || typeof state !== "object") return { available: false };
  // Status is pet-local. Never expose conversation text or history identifiers.
  const keys = ["wsConnected", "aiState", "confName", "baseUrl", "wsUrl", "currentOutfitId",
    "currentOutfitParameterId", "currentOutfitParameterIndex", "currentOutfitValue",
    "currentExpressionId", "currentExpressionLabel", "micEnabled", "micPaused",
    "cameraEnabled", "screenEnabled", "live2dInspectorOverlayEnabled"];
  return { available: true, petGameMode: appState.petGameMode,
    ...Object.fromEntries(keys.filter(key => key in state).map(key => [key, state[key]])) };
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
  const result = await executeRenderer(`window.__kuroPetApplyBackendConfig?.(${JSON.stringify(baseUrl)}, ${JSON.stringify(wsUrl)}, ${JSON.stringify(reload)})`);
  if (!result) return { ok: false, error: "renderer-unavailable" };
  updateFrontendState({ baseUrl, wsUrl });
  return { ok: true };
}


async function setFrontendInputEnabled(kind, enabled) {
  const normalizedKind = String(kind || "").trim();
  if (!["microphone", "camera", "screen"].includes(normalizedKind)) {
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
    case "stop-playback":
      broadcast("pet-command", { type: "stop-playback" });
      return { ok: true, route: "ipc", action };
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
    case "toggle-camera":
      return { ...(await setFrontendInputEnabled("camera", Boolean(payload.enabled))), action };
    case "toggle-screen":
      return { ...(await setFrontendInputEnabled("screen", Boolean(payload.enabled))), action };
    case "reload-frontend":
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.reloadIgnoringCache();
      }
      return { ok: true, action };
    case "set-presentation": {
      const next = normalizePresentation(path.join(repoRoot, "Open-LLM-VTuber"), payload.presentation);
      if (!next) return { ok: false, error: "invalid-presentation" };
      if (JSON.stringify(next) !== JSON.stringify(localPresentation)) {
        localPresentation = next;
        modelRequestedAt = Date.now();
        broadcast("pet-command", { type: "local-model-set", presentation: next });
      }
      return { ok: true, action };
    }
    case "capture-input":
      return await executeRenderer("window.__kuroPetCaptureInput?.()") || { ok: false, error: "renderer-unavailable" };
    case "hide-pet":
      mainWindow?.hide();
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

function applyPetWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  appState.mode = "pet";
  clearPetInteractionState();
  ensurePetAnchor();
  mainWindow.setResizable(false);
  mainWindow.setMinimumSize(1, 1);
  applyMainWindowBounds(resolveTargetBoundsForMode(), "pet-layout");
  applyPetWindowLayerPolicy({ reason: "apply-pet-window" });
  applyTaskbarPolicy();
  broadcastPetHostState("pet-host-set");
  broadcastPetTransformState();
  saveCurrentState();
  applyIgnoreMouseState();
}

function refreshLayoutForDisplayTopology(reason = "display-metrics-changed") {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  if (PET_FIXED_DESKTOP_SHELL && appState.mode === "pet") {
    reconcilePetNativeShell("display-topology");
    return;
  }
  const targetBounds = resolveTargetBoundsForMode(appState.mode);
  applyMainWindowBounds(
    targetBounds,
    appState.mode === "pet" ? "display-topology" : "window-topology"
  );

  if (appState.mode === "pet") {
    petPlacementRecoveryReason = reason;
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


function reloadMainWindow() {
  modelRequestedAt = Date.now();
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.reloadIgnoringCache();
}

function getMenuState() {
  return { forceIgnoreMouse: appState.forceIgnoreMouse, petGameMode: appState.petGameMode };
}

function getMenuActions() {
  return {
    showPet: showMainWindow,
    toggleIgnoreMouse: toggleForceIgnoreMouse,
    toggleGameMode: togglePetGameMode,
    interruptOutput: () => {
      handleControlAction("stop-playback").catch((error) => petLog("menu-interrupt-failed", error));
    },
    moveNextDisplay: moveWindowToNextDisplay,
    resetPosition: resetPetBoundsToDefault,
    reloadFrontend: reloadMainWindow,
    hidePet: () => mainWindow?.hide()
  };
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
      capabilities: { pet: observePetCapability() },
      service: CONTROL_SERVICE,
      protocolVersion: CONTROL_PROTOCOL_VERSION,
      pid: process.pid,
      instanceId: APP_INSTANCE_ID,
      sourceRoot: repoRoot,
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
      petFixedShellReconciliation: { ...fixedPetShellReconciliation },
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
      petTransformRevision: petTransformState?.revision ?? null,
      petEnvelopeTransformRevision: latestPetEnvelopeRevision || null,
      petZoomScale: petTransformState?.zoomScale ?? null,
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
              readNativeContentBounds(mainWindow),
              {
                x: latestPetModelScreenBounds.left,
                y: latestPetModelScreenBounds.top,
                width: latestPetModelScreenBounds.width,
                height: latestPetModelScreenBounds.height
              }
            )
          : null,
      petAnchor: petTransformState ? { ...petTransformState.anchor } : null,
      bounds: mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : null,
      nativeWindowBounds:
        mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : null,
      nativeContentBounds: readNativeContentBounds(mainWindow),
    }),
    handleControlAction,
    applyRendererBackendConfig,
    log: petLog
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
  applyPetWindow();
  reconcilePetNativeShell("startup");
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
    if (PET_FIXED_DESKTOP_SHELL && mainWindow && !mainWindow.isDestroyed()) {
      broadcastPetHostState();
    }
    if (
      mainWindow &&
      !mainWindow.isDestroyed() &&
      !(PET_FIXED_DESKTOP_SHELL && appState.mode === "pet")
    ) {
      setBoundsForCurrentMode(mainWindow.getBounds());
    }
  });

  mainWindow.on("resize", () => {
    if (PET_FIXED_DESKTOP_SHELL && mainWindow && !mainWindow.isDestroyed()) {
      broadcastPetHostState();
    }
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
    applyPetWindow();
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
      presentation: localPresentation,
      wsUrl: process.env.KURO_BACKEND_WS_URL || "ws://127.0.0.1:23456/client-ws",
      zoomScale: transform.zoomScale,
      petTransformRevision: transform.revision,
      petHostMode: PET_HOST_MODE,
      petFixedDesktopShell: PET_FIXED_DESKTOP_SHELL,
      petShellBounds: PET_FIXED_DESKTOP_SHELL ? getPetHostBounds() : null,
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


  ipcMain.on("show-context-menu", () => {
    showPetContextMenu();
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
    appState.petSpanAllDisplays = false;
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
    petLog("app-ready", { statePath, appState });

    registerIpc();
    registerModelProtocol(protocol, net, path.join(repoRoot, 'Open-LLM-VTuber'));
    try {
      localPresentation = normalizePresentation(path.join(repoRoot, 'Open-LLM-VTuber'), JSON.parse(process.env.KURO_PRESENTATION || 'null'));
    } catch (error) { petLog('local-model-bootstrap-failed', error); }
    startControlServer();
    createWindow();
    void refreshRuntimeCapabilities();
    setInterval(() => { void refreshRuntimeCapabilities(); }, 5000).unref();
    startPetCursorTracking();
    startPetInteractionLeaseWatchdog();

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
  });

  app.on("window-all-closed", () => {
    petLog("all-windows-closed", { petOnly: true });
  });

  app.on("before-quit", () => {
    appIsQuitting = true;
    flushPetAnchorSave();
    clearPetHostShrinkTimer();
    clearPetInteractionTimer();
    if (controlServer) {
      try {
        controlServer.close();
      } catch (error) {
        petLog("control-server-close-error", error);
      }
      controlServer = null;
    }
    if (petCursorBroadcastTimer) {
      clearInterval(petCursorBroadcastTimer);
      petCursorBroadcastTimer = null;
    }
    stopPetInteractionLeaseWatchdog();
  });
}
