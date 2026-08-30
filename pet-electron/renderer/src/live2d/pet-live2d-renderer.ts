import { CubismFramework, Option } from "@framework/live2dcubismframework";
import { CubismMatrix44 } from "@framework/math/cubismmatrix44";
import { CubismWebGLOffscreenManager } from "@framework/rendering/cubismoffscreenmanager";
import * as LAppDefine from "./lappdefine";
import { LAppModel } from "./lappmodel";
import { LAppPal } from "./lapppal";
import { LAppSubdelegate } from "./lappsubdelegate";
import {
  Live2DDebugOverlay,
  type Live2DInspectorSnapshot
} from "./live2d-inspector";
import { Live2DHitTester } from "./live2d-hit-tester";
import {
  modelPointToNormalized,
  resolveModelInteractionProfile
} from "./model-interaction-profile";
import {
  resolveModelScreenBounds,
  resolveStablePlacementTranslation,
  resolveViewportInvariantTargetHeight,
  type ModelScreenBounds
} from "./model-screen-geometry";
import { resolveAuthoritativePetTransform } from "../interaction/pet-transform-revision";
import {
  containsScreenPoint,
  getActualCanvasViewportBounds,
  screenPointToViewportPoint,
  type CanvasViewportBounds,
  type ScreenPoint
} from "../geometry/pet-viewport-geometry";

type ModelDescriptor = {
  modelUrl: string;
  sizeHint: number;
};

type DrawableBounds = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

type ScreenBounds = CanvasViewportBounds;

export type PetModelEnvelopeUpdate = {
  transformRevision: number;
  modelScreenBounds: ModelScreenBounds;
};

type AnchorDragState = {
  startScreenX: number;
  startScreenY: number;
  startAnchorX: number;
  startAnchorY: number;
};

export type DragFinishReason =
  | "pointerup"
  | "pointercancel"
  | "lostpointercapture"
  | "blur"
  | "dispose";

type DragTelemetry = {
  sessionId: number;
  startedAt: number | null;
  startTransformRevision: number | null;
  lastFinishReason: DragFinishReason | null;
  lostPointerCaptureCount: number;
  pointerCancelCount: number;
};

const ACTIVE_RENDER_FPS = 60;
const IDLE_RENDER_FPS = 30;
const HIDDEN_RENDER_FPS = 2;
const FRAME_INTERVAL_TOLERANCE_MS = 0.5;
const MIN_MODEL_ZOOM_SCALE = 0.2;
const MAX_MODEL_ZOOM_SCALE = 8;
const MODEL_ENVELOPE_REPORT_THRESHOLD_DIP = 0.75;
const MODEL_ENVELOPE_REPORT_INTERVAL_MS = 16;
const MODEL_ENVELOPE_HEARTBEAT_MS = 1000;
const DYNAMIC_VISUAL_BOUNDS_INTERVAL_MS = 50;

export type OutfitParameterState = {
  parameterId: string | null;
  parameterIndex: number | null;
  value: number;
};

let cubismInitialized = false;

function ensureCubismReady() {
  if (cubismInitialized) {
    return;
  }

  const option = new Option();
  option.logFunction = LAppPal.printMessage;
  option.loggingLevel = LAppDefine.CubismLoggingLevel;

  CubismFramework.startUp(option);
  CubismFramework.initialize();
  cubismInitialized = true;
}

function splitModelUrl(modelUrl: string): { modelDir: string; fileName: string } {
  const lastSlash = modelUrl.lastIndexOf("/");
  if (lastSlash < 0) {
    return {
      modelDir: "",
      fileName: modelUrl
    };
  }

  return {
    modelDir: modelUrl.slice(0, lastSlash + 1),
    fileName: modelUrl.slice(lastSlash + 1)
  };
}

function clampDragPoint(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(-1, value));
}

export class PetLive2DRenderer {
  private readonly canvas: HTMLCanvasElement;
  private readonly rendererBuild: string;
  private readonly subdelegate: LAppSubdelegate;
  private readonly hitTester: Live2DHitTester;
  private readonly debugOverlay: Live2DDebugOverlay;
  private model: LAppModel | null;
  private modelDescriptor: ModelDescriptor | null;
  private rafId: number | null;
  private disposed: boolean;
  private lastRenderedAtMs: number;
  private renderSampleStartedAtMs: number;
  private renderedFramesInSample: number;
  private measuredRenderFps: number;
  private zoomScale: number;
  private outfitParameterId: string | null;
  private outfitParameterIndex: number | null;
  private outfitValue: number;
  private expressionId: string | null;
  private expressionParameters: Record<string, number>;
  private aiState: string;
  private pointerActive: boolean;
  private forceActiveUntilMs: number;
  private stablePlacementBounds: DrawableBounds | null;
  private dynamicVisualBounds: DrawableBounds | null;
  private dynamicVisualBoundsMeasuredAtMs: number;
  private lastResizeWidth: number;
  private lastResizeHeight: number;
  private lastResizeDpr: number;
  private expectedHostBounds: ScreenBounds;
  private anchorScreenPoint: ScreenPoint;
  private transformRevision: number;
  private anchorDrag: AnchorDragState | null;
  private dragTelemetry: DragTelemetry;
  private latestProjectionMatrix: CubismMatrix44 | null;
  private latestModelMatrix: CubismMatrix44 | null;
  private latestModelBounds: DrawableBounds | null;
  private latestModelScreenBounds: ModelScreenBounds | null;
  private lastReportedModelScreenBounds: ModelScreenBounds | null;
  private lastModelEnvelopeReportedAtMs: number;
  private modelEnvelopeListener: ((update: PetModelEnvelopeUpdate) => void) | null;
  private beforeFrameListener: (() => void) | null;

  public constructor(canvas: HTMLCanvasElement, rendererBuild = "unknown") {
    ensureCubismReady();
    this.canvas = canvas;
    this.rendererBuild = String(rendererBuild || "unknown");
    this.subdelegate = new LAppSubdelegate(canvas);
    if (!this.subdelegate.initialize()) {
      throw new Error("Unable to initialize Live2D WebGL context.");
    }

    this.hitTester = new Live2DHitTester();
    this.debugOverlay = new Live2DDebugOverlay(canvas);
    this.model = null;
    this.modelDescriptor = null;
    this.rafId = null;
    this.disposed = false;
    this.lastRenderedAtMs = 0;
    this.renderSampleStartedAtMs = 0;
    this.renderedFramesInSample = 0;
    this.measuredRenderFps = 0;
    this.zoomScale = 1.0;
    this.outfitParameterId = null;
    this.outfitParameterIndex = null;
    this.outfitValue = 0;
    this.expressionId = null;
    this.expressionParameters = {};
    this.aiState = "idle";
    this.pointerActive = false;
    this.forceActiveUntilMs = 0;
    this.stablePlacementBounds = null;
    this.dynamicVisualBounds = null;
    this.dynamicVisualBoundsMeasuredAtMs = 0;
    this.lastResizeWidth = -1;
    this.lastResizeHeight = -1;
    this.lastResizeDpr = -1;
    this.expectedHostBounds = {
      x: 0,
      y: 0,
      width: Math.max(1, window.innerWidth || canvas.clientWidth || 1),
      height: Math.max(1, window.innerHeight || canvas.clientHeight || 1)
    };
    this.anchorScreenPoint = {
      x: this.expectedHostBounds.x + this.expectedHostBounds.width / 2,
      y: this.expectedHostBounds.y + this.expectedHostBounds.height / 2
    };
    this.transformRevision = 0;
    this.anchorDrag = null;
    this.dragTelemetry = {
      sessionId: 0,
      startedAt: null,
      startTransformRevision: null,
      lastFinishReason: null,
      lostPointerCaptureCount: 0,
      pointerCancelCount: 0
    };
    this.latestProjectionMatrix = null;
    this.latestModelMatrix = null;
    this.latestModelBounds = null;
    this.latestModelScreenBounds = null;
    this.lastReportedModelScreenBounds = null;
    this.lastModelEnvelopeReportedAtMs = 0;
    this.modelEnvelopeListener = null;
    this.beforeFrameListener = null;
    this.renderFrame = this.renderFrame.bind(this);
    this.start();
  }

  public loadModel(modelUrl: string, scaleWidth: number): void {
    const normalizedScale = Number.isFinite(scaleWidth) && scaleWidth > 0 ? scaleWidth : 1.8;
    console.info("[pet-renderer] PetLive2DRenderer.loadModel()", {
      modelUrl,
      scaleWidth: normalizedScale
    });
    this.releaseCurrentModel();

    const descriptor: ModelDescriptor = {
      modelUrl,
      sizeHint: normalizedScale
    };
    this.modelDescriptor = descriptor;
    this.stablePlacementBounds = null;
    this.dynamicVisualBounds = null;
    this.dynamicVisualBoundsMeasuredAtMs = 0;
    this.bumpActivity(1800);

    const { modelDir, fileName } = splitModelUrl(modelUrl);
    const nextModel = new LAppModel();
    nextModel.setSubdelegate(this.subdelegate);
    this.model = nextModel;
    if (this.outfitParameterId || this.outfitParameterIndex !== null) {
      nextModel.setExternalParameterTarget(
        this.outfitParameterId || "",
        this.outfitValue,
        0.85,
        this.outfitParameterIndex
      );
    }
    for (const [parameterId, value] of Object.entries(this.expressionParameters)) {
      nextModel.setExternalParameterTarget(parameterId, value, 0.35);
    }
    if (this.expressionId) {
      nextModel.setExpression(this.expressionId);
    }
    this.subdelegate.getTextureManager().releaseTextures();
    console.info("[pet-renderer] Loading model assets", { modelDir, fileName });
    nextModel.loadAssets(modelDir, fileName);
  }

  public resize(): void {
    this.lastResizeWidth = -1;
    this.lastResizeHeight = -1;
    this.lastResizeDpr = -1;
    this.resizeIfNeeded();
    this.bumpActivity(600);
  }

  public setExpectedHostBounds(bounds?: Partial<ScreenBounds> | null): void {
    if (!bounds || typeof bounds !== "object") {
      return;
    }

    const nextBounds = {
      x: Number.isFinite(Number(bounds.x))
        ? Number(bounds.x)
        : this.expectedHostBounds.x,
      y: Number.isFinite(Number(bounds.y))
        ? Number(bounds.y)
        : this.expectedHostBounds.y,
      width: Number.isFinite(Number(bounds.width))
        ? Math.max(1, Number(bounds.width))
        : this.expectedHostBounds.width,
      height: Number.isFinite(Number(bounds.height))
        ? Math.max(1, Number(bounds.height))
        : this.expectedHostBounds.height
    };

    this.expectedHostBounds = nextBounds;
    this.bumpActivity(500);
  }

  public setAnchorScreenPoint(x: number, y: number): void {
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      return;
    }

    this.anchorScreenPoint = {
      x,
      y
    };
    this.bumpActivity(500);
  }

  public getAnchorScreenPoint(): ScreenPoint {
    return {
      x: this.anchorScreenPoint.x,
      y: this.anchorScreenPoint.y
    };
  }

  public beginAnchorDrag(screenX: number, screenY: number): void {
    this.dragTelemetry.sessionId += 1;
    this.dragTelemetry.startedAt = Date.now();
    this.dragTelemetry.startTransformRevision = this.transformRevision;
    this.anchorDrag = {
      startScreenX: screenX,
      startScreenY: screenY,
      startAnchorX: this.anchorScreenPoint.x,
      startAnchorY: this.anchorScreenPoint.y
    };
    this.bumpActivity(700);
  }

  public updateAnchorDrag(screenX: number, screenY: number): ScreenPoint {
    if (!this.anchorDrag) {
      this.beginAnchorDrag(screenX, screenY);
    }

    const drag = this.anchorDrag;
    if (!drag) {
      return this.getAnchorScreenPoint();
    }

    this.bumpActivity(500);
    return {
      x: drag.startAnchorX + (screenX - drag.startScreenX),
      y: drag.startAnchorY + (screenY - drag.startScreenY)
    };
  }

  public endAnchorDrag(reason: DragFinishReason = "pointerup"): void {
    if (!this.anchorDrag) {
      return;
    }
    this.dragTelemetry.lastFinishReason = reason;
    if (reason === "lostpointercapture") {
      this.dragTelemetry.lostPointerCaptureCount += 1;
    } else if (reason === "pointercancel") {
      this.dragTelemetry.pointerCancelCount += 1;
    }
    this.anchorDrag = null;
    this.bumpActivity(300);
  }

  public setZoomScale(nextZoomScale: number): number {
    if (!Number.isFinite(nextZoomScale)) {
      return this.zoomScale;
    }

    this.zoomScale = Math.min(
      MAX_MODEL_ZOOM_SCALE,
      Math.max(MIN_MODEL_ZOOM_SCALE, nextZoomScale)
    );
    this.bumpActivity(800);
    return this.zoomScale;
  }

  public getZoomScale(): number {
    return this.zoomScale;
  }

  public getTransformRevision(): number {
    return this.transformRevision;
  }

  public applyAuthoritativeTransform(transform: {
    revision: number;
    anchor: ScreenPoint;
    zoomScale: number;
  }): boolean {
    const resolution = resolveAuthoritativePetTransform(
      {
        revision: this.transformRevision,
        anchor: this.getAnchorScreenPoint(),
        zoomScale: this.zoomScale
      },
      transform
    );
    if (!resolution.accepted) {
      return false;
    }

    this.transformRevision = resolution.state.revision;
    this.setAnchorScreenPoint(
      resolution.state.anchor.x,
      resolution.state.anchor.y
    );
    this.setZoomScale(resolution.state.zoomScale);
    this.lastReportedModelScreenBounds = null;
    return true;
  }

  public setModelEnvelopeListener(
    listener: ((update: PetModelEnvelopeUpdate) => void) | null
  ): void {
    this.modelEnvelopeListener = typeof listener === "function" ? listener : null;
    this.lastReportedModelScreenBounds = null;
    this.lastModelEnvelopeReportedAtMs = 0;
  }

  public setBeforeFrameListener(listener: (() => void) | null): void {
    this.beforeFrameListener = typeof listener === "function" ? listener : null;
  }

  public setInspectorOverlayEnabled(enabled: boolean): boolean {
    this.debugOverlay.setEnabled(Boolean(enabled));
    this.bumpActivity(this.debugOverlay.isEnabled() ? 1200 : 200);
    return this.debugOverlay.isEnabled();
  }

  public isInspectorOverlayEnabled(): boolean {
    return this.debugOverlay.isEnabled();
  }

  public getInspectorSnapshot(
    readyModel: LAppModel | null = this.getReadyModel(),
    modelBounds: DrawableBounds | null | undefined = undefined,
    frameViewportBounds: CanvasViewportBounds | null | undefined = undefined
  ): Live2DInspectorSnapshot {
    const rect = this.canvas.getBoundingClientRect();
    const actualViewportBounds =
      frameViewportBounds === undefined
        ? getActualCanvasViewportBounds(this.canvas)
        : frameViewportBounds;
    const resolvedBounds =
      modelBounds === undefined && readyModel
        ? this.dynamicVisualBounds || this.measureDrawableBounds(readyModel)
        : modelBounds;
    const interactionProfile = resolvedBounds
      ? resolveModelInteractionProfile(this.modelDescriptor?.modelUrl || "")
      : null;

    return {
      ready: Boolean(readyModel),
      rendererBuild: this.rendererBuild,
      transformRevision: this.transformRevision,
      overlayEnabled: this.debugOverlay.isEnabled(),
      modelUrl: this.modelDescriptor?.modelUrl || "",
      zoomScale: this.zoomScale,
      // Compatibility alias for older inspector consumers. Rendering geometry
      // never reads this expected value.
      hostBounds: { ...this.expectedHostBounds },
      expectedHostBounds: { ...this.expectedHostBounds },
      actualViewportBounds: actualViewportBounds
        ? { ...actualViewportBounds }
        : null,
      viewportOriginError: actualViewportBounds
        ? {
            x:
              actualViewportBounds.x -
              (this.expectedHostBounds.x + rect.left),
            y:
              actualViewportBounds.y -
              (this.expectedHostBounds.y + rect.top)
          }
        : null,
      anchorScreenPoint: { ...this.anchorScreenPoint },
      canvas: {
        width: this.canvas.width,
        height: this.canvas.height,
        clientWidth: Math.max(0, rect.width || this.canvas.clientWidth || 0),
        clientHeight: Math.max(0, rect.height || this.canvas.clientHeight || 0),
        devicePixelRatio: window.devicePixelRatio || 1
      },
      renderPerformance: {
        targetFps: this.getTargetFps(),
        measuredFps: Number(this.measuredRenderFps.toFixed(1))
      },
      modelBounds: resolvedBounds || null,
      stablePlacementBounds: this.stablePlacementBounds
        ? { ...this.stablePlacementBounds }
        : null,
      dynamicVisualBounds: resolvedBounds ? { ...resolvedBounds } : null,
      modelScreenBounds: this.latestModelScreenBounds
        ? { ...this.latestModelScreenBounds }
        : null,
      hitTestMode: readyModel
        ? readyModel.hasConfiguredHitAreas()
          ? "configured-hit-areas"
          : "drawable-mesh"
        : "none",
      interactionProfile: interactionProfile
        ? {
            id: interactionProfile.id,
            active: false,
            ellipses: []
          }
        : null,
      drag: {
        active: Boolean(this.anchorDrag),
        sessionId: this.dragTelemetry.sessionId,
        startedAt: this.dragTelemetry.startedAt,
        startTransformRevision: this.dragTelemetry.startTransformRevision,
        lastFinishReason: this.dragTelemetry.lastFinishReason,
        lostPointerCaptureCount: this.dragTelemetry.lostPointerCaptureCount,
        pointerCancelCount: this.dragTelemetry.pointerCancelCount
      },
      model: readyModel?.getInspectorModelSnapshot() || null
    };
  }

  public setLipSyncValue(value: number): void {
    this.model?.setExternalLipSyncValue(value);
    if (Number(value) > 0.02) {
      this.bumpActivity(260);
    }
  }

  public setActivityState(aiState: string): void {
    const normalized = String(aiState || "idle").trim().toLowerCase() || "idle";
    if (this.aiState === normalized) {
      return;
    }
    this.aiState = normalized;
    this.bumpActivity(
      normalized === "speaking" || normalized === "listening" ? 1200 : 600
    );
  }

  public setPointerActive(active: boolean): void {
    this.pointerActive = Boolean(active);
    if (this.pointerActive) {
      this.bumpActivity(1200);
    }
  }

  public setOutfitParameter(
    parameterId: string,
    value: number,
    parameterIndex: number | null = null,
    durationSeconds = 0.85
  ): void {
    const normalizedParameterId = String(parameterId || "").trim();
    const normalizedParameterIndex =
      Number.isInteger(parameterIndex) && parameterIndex !== null && parameterIndex >= 0
        ? parameterIndex
        : null;
    if (!normalizedParameterId && normalizedParameterIndex === null) {
      return;
    }

    this.outfitParameterId = normalizedParameterId;
    this.outfitParameterIndex = normalizedParameterIndex;
    this.outfitValue = Math.min(1, Math.max(0, Number(value) || 0));
    this.model?.setExternalParameterTarget(
      this.outfitParameterId,
      this.outfitValue,
      durationSeconds,
      this.outfitParameterIndex
    );
    this.bumpActivity(900);
  }

  public getOutfitParameterState(): OutfitParameterState {
    return {
      parameterId: this.outfitParameterId,
      parameterIndex: this.outfitParameterIndex,
      value: this.outfitValue
    };
  }

  public async capturePreviewDataUrl(
    outfit?: Partial<OutfitParameterState> | null
  ): Promise<string | null> {
    if (!this.getReadyModel()) {
      return null;
    }

    const previous = this.getOutfitParameterState();
    const hasPreviewOutfit = Boolean(
      outfit &&
        (String(outfit.parameterId || "").trim() ||
          (Number.isInteger(outfit.parameterIndex) && outfit.parameterIndex !== null))
    );

    if (hasPreviewOutfit && outfit) {
      this.setOutfitParameter(
        String(outfit.parameterId || previous.parameterId || ""),
        Number.isFinite(Number(outfit.value)) ? Number(outfit.value) : previous.value,
        Number.isInteger(outfit.parameterIndex) && outfit.parameterIndex !== null
          ? outfit.parameterIndex
          : previous.parameterIndex,
        0
      );
      await this.waitAnimationFrames(2);
    } else {
      this.bumpActivity(400);
      await this.waitAnimationFrames(2);
    }

    let dataUrl = "";
    try {
      dataUrl = this.captureCroppedCanvasDataUrl() || this.canvas.toDataURL("image/png");
    } catch (error) {
      console.warn("[pet-renderer] Live2D preview capture failed", error);
      dataUrl = "";
    }

    if (hasPreviewOutfit) {
      this.setOutfitParameter(
        previous.parameterId || "",
        previous.value,
        previous.parameterIndex,
        0
      );
      await this.waitAnimationFrames(2);
    }

    return dataUrl || null;
  }

  private captureCroppedCanvasDataUrl(): string | null {
    const sourceWidth = Math.max(1, this.canvas.width || 0);
    const sourceHeight = Math.max(1, this.canvas.height || 0);
    const scratch = document.createElement("canvas");
    scratch.width = sourceWidth;
    scratch.height = sourceHeight;
    const scratchContext = scratch.getContext("2d", { willReadFrequently: true });
    if (!scratchContext) {
      return null;
    }

    scratchContext.clearRect(0, 0, sourceWidth, sourceHeight);
    scratchContext.drawImage(this.canvas, 0, 0, sourceWidth, sourceHeight);

    const imageData = scratchContext.getImageData(0, 0, sourceWidth, sourceHeight);
    const data = imageData.data;
    const alphaThreshold = 8;
    let minX = sourceWidth;
    let minY = sourceHeight;
    let maxX = -1;
    let maxY = -1;

    for (let y = 0; y < sourceHeight; y += 1) {
      const rowOffset = y * sourceWidth * 4;
      for (let x = 0; x < sourceWidth; x += 1) {
        if (data[rowOffset + x * 4 + 3] <= alphaThreshold) {
          continue;
        }
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }

    if (maxX < minX || maxY < minY) {
      return null;
    }

    const padding = Math.max(24, Math.round(32 * (window.devicePixelRatio || 1)));
    const cropX = Math.max(0, minX - padding);
    const cropY = Math.max(0, minY - padding);
    const cropRight = Math.min(sourceWidth, maxX + padding + 1);
    const cropBottom = Math.min(sourceHeight, maxY + padding + 1);
    const cropWidth = Math.max(1, cropRight - cropX);
    const cropHeight = Math.max(1, cropBottom - cropY);

    const output = document.createElement("canvas");
    output.width = cropWidth;
    output.height = cropHeight;
    const outputContext = output.getContext("2d");
    if (!outputContext) {
      return null;
    }
    outputContext.clearRect(0, 0, cropWidth, cropHeight);
    outputContext.drawImage(
      scratch,
      cropX,
      cropY,
      cropWidth,
      cropHeight,
      0,
      0,
      cropWidth,
      cropHeight
    );
    return output.toDataURL("image/png");
  }

  public setExpressionParameters(parameters: Record<string, number>): void {
    const nextParameters: Record<string, number> = {};

    for (const [parameterId, value] of Object.entries(parameters || {})) {
      const normalizedParameterId = String(parameterId || "").trim();
      const numericValue = Number(value);
      if (!normalizedParameterId || !Number.isFinite(numericValue)) {
        continue;
      }
      nextParameters[normalizedParameterId] = Math.min(1, Math.max(-1, numericValue));
    }

    for (const parameterId of Object.keys(this.expressionParameters)) {
      if (!(parameterId in nextParameters)) {
        this.model?.setExternalParameterTarget(parameterId, 0, 0.35);
      }
    }

    this.expressionParameters = nextParameters;
    for (const [parameterId, value] of Object.entries(nextParameters)) {
      this.model?.setExternalParameterTarget(parameterId, value, 0.35);
    }
    this.bumpActivity(900);
  }

  public setExpressionId(expressionId: string): void {
    const normalizedExpressionId = String(expressionId || "").trim();
    if (!normalizedExpressionId) {
      return;
    }

    this.expressionId = normalizedExpressionId;
    this.model?.setExpression(normalizedExpressionId);
    this.bumpActivity(900);
  }

  public playMotion(
    group: string,
    motionIndex: number | null = null,
    priority = LAppDefine.PriorityNormal
  ): void {
    const normalizedGroup = String(group || "").trim();
    if (!this.model || !normalizedGroup) {
      return;
    }

    if (Number.isInteger(motionIndex) && motionIndex !== null && motionIndex >= 0) {
      this.model.startMotion(normalizedGroup, motionIndex, priority);
    } else {
      this.model.startRandomMotion(normalizedGroup, priority);
    }
    this.bumpActivity(1200);
  }

  public setPointerScreenPoint(screenX: number, screenY: number): void {
    if (
      !this.model ||
      this.disposed ||
      !Number.isFinite(screenX) ||
      !Number.isFinite(screenY) ||
      !this.latestProjectionMatrix ||
      !this.latestModelMatrix ||
      !this.latestModelBounds
    ) {
      return;
    }

    const actualViewport = getActualCanvasViewportBounds(this.canvas);
    const canvasPoint = actualViewport
      ? screenPointToViewportPoint({ x: screenX, y: screenY }, actualViewport)
      : null;
    if (!actualViewport || !canvasPoint) {
      return;
    }

    const deviceX = (canvasPoint.x / actualViewport.width) * 2 - 1;
    const deviceY = 1 - (canvasPoint.y / actualViewport.height) * 2;
    const viewPoint = {
      x: this.latestProjectionMatrix.invertTransformX(deviceX),
      y: this.latestProjectionMatrix.invertTransformY(deviceY)
    };
    const modelPoint = {
      x: this.latestModelMatrix.invertTransformX(viewPoint.x),
      y: this.latestModelMatrix.invertTransformY(viewPoint.y)
    };
    const normalized = modelPointToNormalized(modelPoint, this.latestModelBounds);
    if (!normalized) {
      return;
    }

    const profile = resolveModelInteractionProfile(this.modelDescriptor?.modelUrl || "");
    const lookX = clampDragPoint(
      (normalized.x - profile.faceOrigin.x) / profile.lookRange.x
    );
    const lookY = clampDragPoint(
      (normalized.y - profile.faceOrigin.y) / profile.lookRange.y
    );
    this.model.setDragging(lookX, lookY);
    this.bumpActivity(120);
  }

  public resetDragPoint(): void {
    this.model?.setDragging(0, 0);
    this.bumpActivity(300);
  }

  public hitTestCanvasPoint(clientX: number, clientY: number): boolean {
    if (this.disposed) {
      return false;
    }

    const readyModel = this.getReadyModel();
    if (!readyModel) {
      return false;
    }

    return this.hitTester.hitTestCanvasPoint(
      this.canvas,
      readyModel,
      clientX,
      clientY
    ).hit;
  }

  public hitTestScreenPoint(screenX: number, screenY: number): boolean {
    if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) {
      return false;
    }
    const actualViewport = getActualCanvasViewportBounds(this.canvas);
    const screenPoint = { x: screenX, y: screenY };
    if (!actualViewport || !containsScreenPoint(actualViewport, screenPoint)) {
      return false;
    }
    const viewportPoint = screenPointToViewportPoint(screenPoint, actualViewport);
    if (!viewportPoint) {
      return false;
    }
    return this.hitTester.hitTestViewportPoint(
      this.canvas,
      this.getReadyModel(),
      viewportPoint.x,
      viewportPoint.y
    ).hit;
  }

  public dispose(): void {
    this.disposed = true;
    this.beforeFrameListener = null;
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.releaseCurrentModel();
    this.subdelegate.release();
    this.debugOverlay.dispose();
  }

  private start(): void {
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
    }
    this.rafId = window.requestAnimationFrame(this.renderFrame);
  }

  private releaseCurrentModel(): void {
    if (!this.model) {
      return;
    }

    try {
      this.model.release();
    } catch (error) {
      console.warn("[pet-renderer] Failed to release current model", error);
    }

    this.model = null;
    this.stablePlacementBounds = null;
    this.dynamicVisualBounds = null;
    this.dynamicVisualBoundsMeasuredAtMs = 0;
    this.hitTester.clear();
    this.latestProjectionMatrix = null;
    this.latestModelMatrix = null;
    this.latestModelBounds = null;
    this.latestModelScreenBounds = null;
    this.lastReportedModelScreenBounds = null;
  }

  private getReadyModel(): LAppModel | null {
    return this.model &&
      typeof this.model.isReadyToRender === "function" &&
      this.model.isReadyToRender()
      ? this.model
      : null;
  }

  private bumpActivity(durationMs: number): void {
    this.forceActiveUntilMs = Math.max(
      this.forceActiveUntilMs,
      performance.now() + Math.max(0, durationMs)
    );
  }

  private waitAnimationFrames(frameCount: number, timeoutMs = 900): Promise<void> {
    const targetCount = Math.max(1, Math.round(frameCount));
    return new Promise((resolve) => {
      let resolved = false;
      const finish = () => {
        if (resolved) {
          return;
        }
        resolved = true;
        window.clearTimeout(timerId);
        resolve();
      };
      const timerId = window.setTimeout(finish, Math.max(80, timeoutMs));
      let remaining = targetCount;
      const tick = () => {
        if (resolved) {
          return;
        }
        remaining -= 1;
        if (remaining <= 0) {
          finish();
          return;
        }
        window.requestAnimationFrame(tick);
      };
      window.requestAnimationFrame(tick);
    });
  }

  private getTargetFps(): number {
    if (this.debugOverlay.isEnabled()) {
      return ACTIVE_RENDER_FPS;
    }

    if (document.hidden) {
      return HIDDEN_RENDER_FPS;
    }

    const now = performance.now();
    if (this.pointerActive || now < this.forceActiveUntilMs) {
      return ACTIVE_RENDER_FPS;
    }

    if (
      this.aiState === "speaking" ||
      this.aiState === "listening" ||
      this.aiState === "thinking" ||
      this.aiState === "connecting" ||
      this.aiState === "interrupted"
    ) {
      return ACTIVE_RENDER_FPS;
    }
    return IDLE_RENDER_FPS;
  }

  private scheduleNextFrame(): void {
    if (this.disposed || this.rafId !== null) {
      return;
    }
    this.rafId = window.requestAnimationFrame(this.renderFrame);
  }

  private shouldRenderFrame(frameTimeMs: number): boolean {
    const targetFps = this.getTargetFps();
    const targetIntervalMs = 1000 / targetFps;
    if (this.lastRenderedAtMs <= 0) {
      this.lastRenderedAtMs = frameTimeMs;
      return true;
    }

    const elapsedMs = frameTimeMs - this.lastRenderedAtMs;
    if (elapsedMs + FRAME_INTERVAL_TOLERANCE_MS < targetIntervalMs) {
      return false;
    }

    this.lastRenderedAtMs = frameTimeMs - (elapsedMs % targetIntervalMs);
    return true;
  }

  private recordRenderedFrame(frameTimeMs: number): void {
    if (this.renderSampleStartedAtMs <= 0) {
      this.renderSampleStartedAtMs = frameTimeMs;
      this.renderedFramesInSample = 1;
      return;
    }

    this.renderedFramesInSample += 1;
    const sampleDurationMs = frameTimeMs - this.renderSampleStartedAtMs;
    if (sampleDurationMs < 1000) {
      return;
    }

    this.measuredRenderFps =
      ((this.renderedFramesInSample - 1) * 1000) / sampleDurationMs;
    this.renderSampleStartedAtMs = frameTimeMs;
    this.renderedFramesInSample = 1;
  }

  private resizeIfNeeded(): void {
    const rect = this.canvas.getBoundingClientRect();
    const width = Math.max(0, Math.round(rect.width));
    const height = Math.max(0, Math.round(rect.height));
    const dpr = window.devicePixelRatio || 1;

    if (
      width === this.lastResizeWidth &&
      height === this.lastResizeHeight &&
      Math.abs(dpr - this.lastResizeDpr) < 0.001
    ) {
      return;
    }

    this.lastResizeWidth = width;
    this.lastResizeHeight = height;
    this.lastResizeDpr = dpr;
    this.subdelegate.resize();
  }

  private getDynamicVisualBounds(
    readyModel: LAppModel,
    frameTimeMs: number
  ): DrawableBounds | null {
    if (
      this.dynamicVisualBounds &&
      frameTimeMs - this.dynamicVisualBoundsMeasuredAtMs <
        DYNAMIC_VISUAL_BOUNDS_INTERVAL_MS
    ) {
      return this.dynamicVisualBounds;
    }

    const measuredBounds = this.measureDrawableBounds(readyModel);
    this.dynamicVisualBounds = measuredBounds ? { ...measuredBounds } : null;
    this.dynamicVisualBoundsMeasuredAtMs = frameTimeMs;
    if (!this.stablePlacementBounds && measuredBounds) {
      this.stablePlacementBounds = { ...measuredBounds };
    }
    return this.dynamicVisualBounds;
  }

  private measureDrawableBounds(readyModel: LAppModel): DrawableBounds | null {
    const cubismModel = readyModel.getModel();
    if (!cubismModel) {
      return null;
    }

    let left = Number.POSITIVE_INFINITY;
    let right = Number.NEGATIVE_INFINITY;
    let top = Number.POSITIVE_INFINITY;
    let bottom = Number.NEGATIVE_INFINITY;
    let hasVisibleVertex = false;
    const drawableCount = cubismModel.getDrawableCount();

    for (let drawableIndex = 0; drawableIndex < drawableCount; drawableIndex += 1) {
      if (
        cubismModel.getDrawableOpacity(drawableIndex) <= 0.001 ||
        !cubismModel.getDrawableDynamicFlagIsVisible(drawableIndex)
      ) {
        continue;
      }

      const vertexCount = cubismModel.getDrawableVertexCount(drawableIndex);
      const vertices = cubismModel.getDrawableVertices(drawableIndex);
      for (let vertexIndex = 0; vertexIndex < vertexCount; vertexIndex += 1) {
        const x = vertices[vertexIndex * 2];
        const y = vertices[vertexIndex * 2 + 1];
        if (!Number.isFinite(x) || !Number.isFinite(y)) {
          continue;
        }

        left = Math.min(left, x);
        right = Math.max(right, x);
        top = Math.min(top, y);
        bottom = Math.max(bottom, y);
        hasVisibleVertex = true;
      }
    }

    if (!hasVisibleVertex) {
      return null;
    }

    return { left, right, top, bottom };
  }

  private getAnchorViewPoint(
    projection: CubismMatrix44,
    actualViewport: CanvasViewportBounds
  ): ScreenPoint | null {
    const anchorViewportPoint = screenPointToViewportPoint(
      this.anchorScreenPoint,
      actualViewport
    );
    if (!anchorViewportPoint) {
      return null;
    }

    const deviceX = (anchorViewportPoint.x / actualViewport.width) * 2 - 1;
    const deviceY = 1 - (anchorViewportPoint.y / actualViewport.height) * 2;
    return {
      x: projection.invertTransformX(deviceX),
      y: projection.invertTransformY(deviceY)
    };
  }

  private resolveCurrentModelScreenBounds(
    projection: CubismMatrix44,
    matrix: CubismMatrix44,
    modelBounds: DrawableBounds,
    actualViewport: CanvasViewportBounds
  ): ModelScreenBounds | null {
    return resolveModelScreenBounds(
      modelBounds,
      {
        scaleX: matrix.getScaleX(),
        scaleY: matrix.getScaleY(),
        translateX: matrix.getTranslateX(),
        translateY: matrix.getTranslateY()
      },
      {
        scaleX: projection.getScaleX(),
        scaleY: projection.getScaleY(),
        translateX: projection.getTranslateX(),
        translateY: projection.getTranslateY()
      },
      actualViewport
    );
  }

  private maybeReportModelEnvelope(
    modelScreenBounds: ModelScreenBounds,
    frameTimeMs: number
  ): void {
    if (!this.modelEnvelopeListener) {
      return;
    }

    const previous = this.lastReportedModelScreenBounds;
    const materiallyChanged =
      !previous ||
      Math.abs(previous.left - modelScreenBounds.left) >= MODEL_ENVELOPE_REPORT_THRESHOLD_DIP ||
      Math.abs(previous.top - modelScreenBounds.top) >= MODEL_ENVELOPE_REPORT_THRESHOLD_DIP ||
      Math.abs(previous.right - modelScreenBounds.right) >= MODEL_ENVELOPE_REPORT_THRESHOLD_DIP ||
      Math.abs(previous.bottom - modelScreenBounds.bottom) >= MODEL_ENVELOPE_REPORT_THRESHOLD_DIP;
    const elapsedMs = frameTimeMs - this.lastModelEnvelopeReportedAtMs;
    if (
      (!materiallyChanged && elapsedMs < MODEL_ENVELOPE_HEARTBEAT_MS) ||
      (materiallyChanged && elapsedMs < MODEL_ENVELOPE_REPORT_INTERVAL_MS)
    ) {
      return;
    }

    this.lastReportedModelScreenBounds = { ...modelScreenBounds };
    this.lastModelEnvelopeReportedAtMs = frameTimeMs;
    this.modelEnvelopeListener({
      transformRevision: this.transformRevision,
      modelScreenBounds: { ...modelScreenBounds }
    });
  }

  private renderFrame(frameTimeMs: number): void {
    this.rafId = null;
    if (this.disposed) {
      return;
    }
    if (!this.shouldRenderFrame(frameTimeMs)) {
      this.scheduleNextFrame();
      return;
    }
    this.beforeFrameListener?.();
    this.recordRenderedFrame(frameTimeMs);

    LAppPal.updateTime();
    this.resizeIfNeeded();

    const gl = this.subdelegate.getGlManager().getGl();
    if (gl.isContextLost()) {
      console.warn("[pet-renderer] WebGL context lost; waiting for recovery.");
      this.scheduleNextFrame();
      return;
    }

    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.clearDepth(1.0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const readyModel = this.getReadyModel();

    if (readyModel?.getModel()) {
      CubismWebGLOffscreenManager.getInstance().beginFrameProcess(gl);
      const projection = new CubismMatrix44();
      const { width, height } = this.canvas;
      const actualViewportBounds = getActualCanvasViewportBounds(this.canvas);

      if (width > 0 && height > 0) {
        if (width < height) {
          projection.scale(1.0, width / height);
        } else {
          projection.scale(height / width, 1.0);
        }
      }

      if (!this.stablePlacementBounds) {
        const initialBounds = this.measureDrawableBounds(readyModel);
        if (initialBounds) {
          this.stablePlacementBounds = { ...initialBounds };
        }
      }

      readyModel.update();

      let modelBounds: DrawableBounds | null = null;
      const matrix = readyModel.getModelMatrix();
      if (matrix && this.modelDescriptor) {
        matrix.loadIdentity();

        const anchorViewPoint = actualViewportBounds
          ? this.getAnchorViewPoint(projection, actualViewportBounds) || { x: 0, y: 0 }
          : { x: 0, y: 0 };
        const baseTargetHeight = Math.min(
          2.8,
          Math.max(0.85, this.modelDescriptor.sizeHint * 1.9)
        );
        // Model visual size is owned only by zoom. The viewport contributes
        // the view-unit-to-DIP conversion, so resizing the BrowserWindow does
        // not feed back into the character's on-screen scale.
        const targetHeight = actualViewportBounds
          ? resolveViewportInvariantTargetHeight(
              baseTargetHeight,
              this.zoomScale,
              actualViewportBounds.width,
              actualViewportBounds.height
            )
          : null;

        if (targetHeight) {
          matrix.setHeight(targetHeight);
        }

        modelBounds = this.getDynamicVisualBounds(readyModel, frameTimeMs);
        const placementBounds = this.stablePlacementBounds || modelBounds;
        const placementTranslation = placementBounds
          ? resolveStablePlacementTranslation(
              placementBounds,
              anchorViewPoint,
              matrix.getScaleX(),
              matrix.getScaleY()
            )
          : null;
        if (placementTranslation) {
          // Placement is permanently based on the model's first stable visible
          // pose. Motion/expression/outfit bounds may resize the transparent
          // host, but cannot redefine the character's feet or horizontal centre.
          matrix.translate(placementTranslation.x, placementTranslation.y);
        } else {
          matrix.centerX(anchorViewPoint.x);
          matrix.bottom(anchorViewPoint.y);
        }
      }

      if (matrix) {
        this.latestProjectionMatrix = projection.clone();
        this.latestModelMatrix = matrix.clone();
        this.latestModelBounds = modelBounds ? { ...modelBounds } : null;
        this.latestModelScreenBounds = modelBounds && actualViewportBounds
          ? this.resolveCurrentModelScreenBounds(
              projection,
              matrix,
              modelBounds,
              actualViewportBounds
            )
          : null;
        if (this.latestModelScreenBounds) {
          this.maybeReportModelEnvelope(this.latestModelScreenBounds, frameTimeMs);
        }
        this.hitTester.updateFrame(
          projection,
          readyModel.hasConfiguredHitAreas()
        );
      } else {
        this.hitTester.clear();
      }
      const overlayEnabled = this.debugOverlay.isEnabled();
      const overlayProjection = overlayEnabled ? new CubismMatrix44() : null;
      if (overlayProjection) {
        overlayProjection.setMatrix(projection.getArray());
      }
      const overlaySnapshot = overlayEnabled
        ? this.getInspectorSnapshot(
            readyModel,
            modelBounds,
            actualViewportBounds
          )
        : null;
      readyModel.draw(projection);

      CubismWebGLOffscreenManager.getInstance().endFrameProcess(gl);
      CubismWebGLOffscreenManager
        .getInstance()
        .releaseStaleRenderTextures(gl);

      if (overlaySnapshot && overlayProjection && matrix) {
        this.debugOverlay.render(overlaySnapshot, {
          projection: overlayProjection,
          modelMatrix: matrix
        });
      }
    } else {
      this.hitTester.clear();
      this.latestProjectionMatrix = null;
      this.latestModelMatrix = null;
      this.latestModelBounds = null;
      this.latestModelScreenBounds = null;
      if (this.debugOverlay.isEnabled()) {
        this.debugOverlay.render(this.getInspectorSnapshot(null, null), null);
      }
    }
    this.scheduleNextFrame();
  }
}
