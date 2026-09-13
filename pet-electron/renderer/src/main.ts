import "./styles.css";
import { PetLive2DRenderer } from "./live2d/pet-live2d-renderer";
import { BackendClient } from "./backend/backend-client";
import type { RendererState, UserAttachmentPayload } from "./backend/types";
import { bindPetCommands } from "./commands/pet-command-router";
import { bindModelPointerControls } from "./interaction/model-pointer-controls";
import { PetRenderSurfaceController } from "./live2d/pet-render-surface-controller";
import { resolveInitialZoomScale, storeModelZoomScale } from "./model-zoom";

const RENDERER_BUILD_TAG = "fixed-desktop-shell-v1";
const DEFAULT_OUTFIT_PARAMETER_ID = "Param10";
console.info("[pet-renderer] boot", { build: RENDERER_BUILD_TAG });

const originalFetch = window.fetch.bind(window);
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const target =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
  try {
    const response = await originalFetch(input, init);
    console.info("[pet-renderer] fetch", {
      target,
      status: response.status,
      ok: response.ok
    });
    return response;
  } catch (error) {
    console.error("[pet-renderer] fetch failed", {
      target,
      error: error instanceof Error ? error.message : String(error)
    });
    throw error;
  }
};


const root = document.getElementById("app");
if (!root) {
  throw new Error("Renderer root not found.");
}

root.innerHTML = `
  <div class="pet-renderer">
    <div class="pet-surface" id="pet-render-surface">
      <canvas id="live2d-canvas"></canvas>
    </div>
  </div>
`;

const surfaceElement = document.getElementById("pet-render-surface");
const canvas = document.getElementById("live2d-canvas");
if (!(surfaceElement instanceof HTMLElement) || !(canvas instanceof HTMLCanvasElement)) {
  throw new Error("Renderer DOM bootstrap failed.");
}

const rendererState: RendererState = {
  wsConnected: false,
  aiState: "idle",
  latestAssistantText: "",
  latestUserText: "",
  wsUrl: "",
  baseUrl: "",
  currentModelUrl: "",
  confName: "",
  confUid: "",
  currentHistoryUid: "",
  currentHistoryTitle: "",
  currentOutfitId: "normal",
  currentOutfitParameterId: DEFAULT_OUTFIT_PARAMETER_ID,
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

let live2dRenderer: PetLive2DRenderer | null = null;

const reportState = (patch: Partial<RendererState>) => {
  Object.assign(rendererState, patch);
  live2dRenderer?.setActivityState(rendererState.aiState);
  window.__kuroPetRendererState = { ...rendererState };
  window.kuroPetElectron.reportFrontendState({ ...rendererState });
};

const initialConfig = window.kuroPetElectron.getInitialConfig();
const renderSurface = new PetRenderSurfaceController(surfaceElement, {
  enabled: initialConfig.petFixedDesktopShell === true,
  shellBounds: initialConfig.petShellBounds || initialConfig.petHostBounds || null,
  anchorScreenPoint: initialConfig.petAnchor || null,
  transformRevision: Number(initialConfig.petTransformRevision) || 1
});
const renderer = new PetLive2DRenderer(canvas, RENDERER_BUILD_TAG);
live2dRenderer = renderer;
renderer.setBeforeFrameListener(() => {
  renderSurface.flushPending();
});
renderer.setModelEnvelopeListener((update) => {
  renderSurface.scheduleModelEnvelope(
    update.modelScreenBounds,
    update.transformRevision
  );
  window.kuroPetElectron.reportPetModelEnvelope(update);
});
const getInspectorSnapshot = () => ({
  ...renderer.getInspectorSnapshot(),
  renderSurface: renderSurface.getSnapshot()
});
window.__kuroLive2DInspector = {
  getSnapshot: getInspectorSnapshot,
  setOverlayEnabled: (enabled: boolean) => {
    const live2dInspectorOverlayEnabled = renderer.setInspectorOverlayEnabled(enabled);
    reportState({ live2dInspectorOverlayEnabled });
    return getInspectorSnapshot();
  },
  toggleOverlay: () => {
    const live2dInspectorOverlayEnabled = renderer.setInspectorOverlayEnabled(
      !renderer.isInspectorOverlayEnabled()
    );
    reportState({ live2dInspectorOverlayEnabled });
    return getInspectorSnapshot();
  }
};
renderer.setExpectedHostBounds(initialConfig.petHostBounds);
renderer.applyAuthoritativeTransform({
  revision: Number(initialConfig.petTransformRevision) || 1,
  anchor: initialConfig.petAnchor || renderer.getAnchorScreenPoint(),
  zoomScale: resolveInitialZoomScale(initialConfig.zoomScale)
});
renderSurface.scheduleTransform(
  renderer.getAnchorScreenPoint(),
  renderer.getTransformRevision()
);
renderSurface.flushPending();
storeModelZoomScale(renderer.getZoomScale());
const initialOutfit = initialConfig.outfit || {};
const initialOutfitId = String(initialOutfit.outfitId || "normal");
const initialOutfitParameterId = String(
  initialOutfit.parameterId || DEFAULT_OUTFIT_PARAMETER_ID
);
const initialOutfitParameterIndex =
  Number.isInteger(initialOutfit.parameterIndex) && initialOutfit.parameterIndex !== null
    ? initialOutfit.parameterIndex
    : null;
const initialOutfitValue = Math.min(
  1,
  Math.max(0, Number(initialOutfit.value) || 0)
);
renderer.setOutfitParameter(
  initialOutfitParameterId,
  initialOutfitValue,
  initialOutfitParameterIndex
);
const initialExpression = initialConfig.expression || {};
const initialExpressionId = String(initialExpression.expressionId || "neutral");
const initialExpressionLabel = String(initialExpression.expressionLabel || "一般");
const initialExpressionParameters = initialExpression.parameters || {};
renderer.setExpressionParameters(initialExpressionParameters);
const client = new BackendClient(
  {
    baseUrl: initialConfig.baseUrl,
    wsUrl: initialConfig.wsUrl
  },
  renderer,
  reportState
);

window.__kuroPetSendTextInput = (text: string, attachments: UserAttachmentPayload[] = []) =>
  client.sendText(text, attachments);
window.__kuroPetApplyBackendConfig = (baseUrl: string, wsUrl: string, reconnect = true) =>
  client.applyConfig(baseUrl, wsUrl, reconnect);
window.__kuroPetSetInputEnabled = async (kind: string, enabled: boolean) => {
  if (kind === "microphone") return client.setMicrophoneEnabled(enabled);
  if (kind === "camera") return client.setCameraEnabled(enabled);
  if (kind === "screen") return client.setScreenEnabled(enabled);
  if (kind === "browser") return client.setBrowserPanelEnabled(enabled);
  return { ok: false, error: "unsupported-input-kind" };
};
window.__kuroPetControlMicrophone = (action) => client.controlMicrophone(action);
window.__kuroLive2DPreview = {
  capture: async (options = {}) => {
    const outfitId = String(options.outfitId || "").trim();
    const parameterId = String(options.parameterId || DEFAULT_OUTFIT_PARAMETER_ID).trim();
    const parameterIndex =
      Number.isInteger(options.parameterIndex) && options.parameterIndex !== null
        ? options.parameterIndex
        : null;
    const value = Number.isFinite(Number(options.value))
      ? Math.max(0, Math.min(1, Number(options.value)))
      : outfitId === "hoodie"
        ? 1
        : outfitId === "normal"
          ? 0
          : rendererState.currentOutfitValue;
    return renderer.capturePreviewDataUrl({
      parameterId,
      parameterIndex,
      value
    });
  }
};

reportState({
  baseUrl: initialConfig.baseUrl,
  wsUrl: initialConfig.wsUrl,
  currentOutfitId: initialOutfitId,
  currentOutfitParameterId: initialOutfitParameterId,
  currentOutfitParameterIndex: initialOutfitParameterIndex,
  currentOutfitValue: initialOutfitValue,
  currentExpressionId: initialExpressionId,
  currentExpressionLabel: initialExpressionLabel,
  live2dInspectorOverlayEnabled: renderer.isInspectorOverlayEnabled()
});
client.setPresentationModel(initialConfig.presentation || null);
client.connect();

const unbindModelPointerControls = bindModelPointerControls(canvas, renderer);

window.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  window.kuroPetElectron.showContextMenu();
});

window.addEventListener("resize", () => {
  renderer.resize();
});

const unsubscribe = bindPetCommands({
  client,
  renderer,
  reportState,
  defaultOutfitParameterId: DEFAULT_OUTFIT_PARAMETER_ID,
  onTransformAccepted: () => {
    renderSurface.scheduleTransform(
      renderer.getAnchorScreenPoint(),
      renderer.getTransformRevision()
    );
  },
  onHostAccepted: (bounds) => {
    renderSurface.scheduleShellBounds(bounds);
  }
});

window.addEventListener(
  "beforeunload",
  () => {
    unsubscribe();
    unbindModelPointerControls();
    client.disconnect();
    renderSurface.dispose();
    renderer.dispose();
  },
  { passive: true }
);

window.addEventListener("error", (event) => {
  console.error("[pet-renderer] Unhandled window error", event.error || event.message);
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason as any;
  console.error("[pet-renderer] Unhandled promise rejection", {
    message: reason?.message || String(reason),
    stack: reason?.stack || null
  });
});
