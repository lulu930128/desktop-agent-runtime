import { CubismFramework, Option } from "@framework/live2dcubismframework";
import { CubismMatrix44 } from "@framework/math/cubismmatrix44";
import { CubismWebGLOffscreenManager } from "@framework/rendering/cubismoffscreenmanager";
import * as LAppDefine from "./lappdefine";
import { LAppModel } from "./lappmodel";
import { LAppPal } from "./lapppal";
import { LAppSubdelegate } from "./lappsubdelegate";
import { Live2DHitTester } from "./live2d-hit-tester";

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

type ScreenBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type ScreenPoint = {
  x: number;
  y: number;
};

type AnchorDragState = {
  startClientX: number;
  startClientY: number;
  startAnchorX: number;
  startAnchorY: number;
};

const FORCE_MAX_RENDER_FPS = true;
const MIN_MODEL_ZOOM_SCALE = 0.2;
const MAX_MODEL_ZOOM_SCALE = 8;
const MODEL_ZOOM_WHEEL_FACTOR = 1.06;

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
  private readonly subdelegate: LAppSubdelegate;
  private readonly hitTester: Live2DHitTester;
  private model: LAppModel | null;
  private modelDescriptor: ModelDescriptor | null;
  private rafId: number | null;
  private renderTimerId: number | null;
  private disposed: boolean;
  private zoomScale: number;
  private outfitParameterId: string | null;
  private outfitParameterIndex: number | null;
  private outfitValue: number;
  private expressionId: string | null;
  private expressionParameters: Record<string, number>;
  private aiState: string;
  private pointerActive: boolean;
  private forceActiveUntilMs: number;
  private cachedDrawableBounds: DrawableBounds | null;
  private cachedDrawableBoundsAtMs: number;
  private lastResizeWidth: number;
  private lastResizeHeight: number;
  private lastResizeDpr: number;
  private hostBounds: ScreenBounds;
  private anchorScreenPoint: ScreenPoint;
  private anchorDrag: AnchorDragState | null;

  public constructor(canvas: HTMLCanvasElement) {
    ensureCubismReady();
    this.canvas = canvas;
    this.subdelegate = new LAppSubdelegate(canvas);
    if (!this.subdelegate.initialize()) {
      throw new Error("Unable to initialize Live2D WebGL context.");
    }

    this.hitTester = new Live2DHitTester();
    this.model = null;
    this.modelDescriptor = null;
    this.rafId = null;
    this.renderTimerId = null;
    this.disposed = false;
    this.zoomScale = 1.0;
    this.outfitParameterId = null;
    this.outfitParameterIndex = null;
    this.outfitValue = 0;
    this.expressionId = null;
    this.expressionParameters = {};
    this.aiState = "idle";
    this.pointerActive = false;
    this.forceActiveUntilMs = 0;
    this.cachedDrawableBounds = null;
    this.cachedDrawableBoundsAtMs = 0;
    this.lastResizeWidth = -1;
    this.lastResizeHeight = -1;
    this.lastResizeDpr = -1;
    this.hostBounds = {
      x: 0,
      y: 0,
      width: Math.max(1, window.innerWidth || canvas.clientWidth || 1),
      height: Math.max(1, window.innerHeight || canvas.clientHeight || 1)
    };
    this.anchorScreenPoint = {
      x: this.hostBounds.x + this.hostBounds.width / 2,
      y: this.hostBounds.y + this.hostBounds.height / 2
    };
    this.anchorDrag = null;
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
    this.invalidateDrawableBounds();
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

  public setHostBounds(bounds?: Partial<ScreenBounds> | null): void {
    if (!bounds || typeof bounds !== "object") {
      return;
    }

    const nextBounds = {
      x: Number.isFinite(Number(bounds.x)) ? Number(bounds.x) : this.hostBounds.x,
      y: Number.isFinite(Number(bounds.y)) ? Number(bounds.y) : this.hostBounds.y,
      width: Number.isFinite(Number(bounds.width))
        ? Math.max(1, Number(bounds.width))
        : this.hostBounds.width,
      height: Number.isFinite(Number(bounds.height))
        ? Math.max(1, Number(bounds.height))
        : this.hostBounds.height
    };

    this.hostBounds = nextBounds;
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

  public beginAnchorDrag(clientX: number, clientY: number): void {
    this.anchorDrag = {
      startClientX: clientX,
      startClientY: clientY,
      startAnchorX: this.anchorScreenPoint.x,
      startAnchorY: this.anchorScreenPoint.y
    };
    this.bumpActivity(700);
  }

  public updateAnchorDrag(clientX: number, clientY: number): ScreenPoint {
    if (!this.anchorDrag) {
      this.beginAnchorDrag(clientX, clientY);
    }

    const drag = this.anchorDrag;
    if (!drag) {
      return this.getAnchorScreenPoint();
    }

    this.setAnchorScreenPoint(
      drag.startAnchorX + (clientX - drag.startClientX),
      drag.startAnchorY + (clientY - drag.startClientY)
    );
    return this.getAnchorScreenPoint();
  }

  public endAnchorDrag(): void {
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
    parameterIndex: number | null = null
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
      0.85,
      this.outfitParameterIndex
    );
    this.bumpActivity(900);
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

  public setDragPointFromCanvas(clientX: number, clientY: number): void {
    if (!this.model || this.disposed) {
      return;
    }

    const rect = this.canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      this.model.setDragging(0, 0);
      return;
    }

    const dragX = ((clientX - rect.left) / rect.width) * 2 - 1;
    const dragY = 1 - ((clientY - rect.top) / rect.height) * 2;
    const clampedX = clampDragPoint(dragX);
    const clampedY = clampDragPoint(dragY);
    this.model.setDragging(clampedX, clampedY);
    this.model.setExternalLookTarget(clampedX, clampedY);
    this.bumpActivity(700);
  }

  public resetDragPoint(): void {
    this.model?.setDragging(0, 0);
    this.model?.setExternalLookTarget(0, 0);
    this.bumpActivity(300);
  }

  public adjustZoomByWheel(deltaY: number): number {
    const direction = deltaY < 0 ? 1 : -1;
    const nextScale =
      this.zoomScale * (direction > 0 ? MODEL_ZOOM_WHEEL_FACTOR : 1 / MODEL_ZOOM_WHEEL_FACTOR);
    return this.setZoomScale(nextScale);
  }

  public hitTestCanvasPoint(clientX: number, clientY: number): boolean {
    if (this.disposed) {
      return false;
    }

    const readyModel =
      this.model && typeof this.model.isReadyToRender === "function" && this.model.isReadyToRender()
        ? this.model
        : null;
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

  public dispose(): void {
    this.disposed = true;
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.renderTimerId !== null) {
      window.clearTimeout(this.renderTimerId);
      this.renderTimerId = null;
    }
    this.releaseCurrentModel();
    this.subdelegate.release();
  }

  private start(): void {
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
    }
    if (this.renderTimerId !== null) {
      window.clearTimeout(this.renderTimerId);
      this.renderTimerId = null;
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
    this.invalidateDrawableBounds();
    this.hitTester.clear();
  }

  private bumpActivity(durationMs: number): void {
    this.forceActiveUntilMs = Math.max(
      this.forceActiveUntilMs,
      performance.now() + Math.max(0, durationMs)
    );
  }

  private invalidateDrawableBounds(): void {
    this.cachedDrawableBounds = null;
    this.cachedDrawableBoundsAtMs = 0;
  }

  private getTargetFps(): number {
    if (FORCE_MAX_RENDER_FPS) {
      return Number.POSITIVE_INFINITY;
    }

    if (document.hidden) {
      return 2;
    }

    const now = performance.now();
    if (this.pointerActive || now < this.forceActiveUntilMs) {
      return 30;
    }

    if (this.aiState === "speaking") {
      return 30;
    }
    if (this.aiState === "listening") {
      return 24;
    }
    if (
      this.aiState === "thinking" ||
      this.aiState === "connecting" ||
      this.aiState === "interrupted"
    ) {
      return 18;
    }
    return 12;
  }

  private scheduleNextFrame(): void {
    if (this.disposed || this.rafId !== null || this.renderTimerId !== null) {
      return;
    }

    if (FORCE_MAX_RENDER_FPS) {
      this.rafId = window.requestAnimationFrame(this.renderFrame);
      return;
    }

    const delayMs = Math.max(16, Math.round(1000 / this.getTargetFps()));
    this.renderTimerId = window.setTimeout(() => {
      this.renderTimerId = null;
      if (!this.disposed) {
        this.rafId = window.requestAnimationFrame(this.renderFrame);
      }
    }, delayMs);
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

  private getDrawableBounds(readyModel: LAppModel): DrawableBounds | null {
    if (this.cachedDrawableBounds) {
      return this.cachedDrawableBounds;
    }

    this.cachedDrawableBounds = this.measureDrawableBounds(readyModel);
    this.cachedDrawableBoundsAtMs = performance.now();
    return this.cachedDrawableBounds;
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

  private getAnchorViewPoint(projection: CubismMatrix44): ScreenPoint | null {
    const rect = this.canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return null;
    }

    const anchorCanvasX = this.anchorScreenPoint.x - this.hostBounds.x;
    const anchorCanvasY = this.anchorScreenPoint.y - this.hostBounds.y;
    if (!Number.isFinite(anchorCanvasX) || !Number.isFinite(anchorCanvasY)) {
      return null;
    }

    const deviceX = (anchorCanvasX / rect.width) * 2 - 1;
    const deviceY = 1 - (anchorCanvasY / rect.height) * 2;
    return {
      x: projection.invertTransformX(deviceX),
      y: projection.invertTransformY(deviceY)
    };
  }

  private renderFrame(): void {
    this.rafId = null;
    if (this.disposed) {
      return;
    }

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

    const readyModel =
      this.model && typeof this.model.isReadyToRender === 'function' && this.model.isReadyToRender()
        ? this.model
        : null;

    if (readyModel?.getModel()) {
      CubismWebGLOffscreenManager.getInstance().beginFrameProcess(gl);
      const projection = new CubismMatrix44();
      const { width, height } = this.canvas;

      if (width > 0 && height > 0) {
        if (width < height) {
          projection.scale(1.0, width / height);
        } else {
          projection.scale(height / width, 1.0);
        }
      }

      readyModel.update();

      const matrix = readyModel.getModelMatrix();
      if (matrix && this.modelDescriptor) {
        matrix.loadIdentity();

        const anchorViewPoint = this.getAnchorViewPoint(projection) || { x: 0, y: 0 };
        const baseTargetHeight = Math.min(
          2.8,
          Math.max(0.85, this.modelDescriptor.sizeHint * 1.9)
        );
        const targetHeight = baseTargetHeight * this.zoomScale;

        matrix.setHeight(targetHeight);

        const bounds = this.getDrawableBounds(readyModel);
        if (bounds) {
          const centerX = (bounds.left + bounds.right) / 2;
          const centerY = (bounds.top + bounds.bottom) / 2;
          matrix.translate(
            anchorViewPoint.x - centerX * matrix.getScaleX(),
            anchorViewPoint.y - centerY * matrix.getScaleY()
          );
        } else {
          matrix.centerX(anchorViewPoint.x);
          matrix.centerY(anchorViewPoint.y);
        }
      }

      this.hitTester.updateProjection(projection);
      readyModel.draw(projection);

      CubismWebGLOffscreenManager.getInstance().endFrameProcess(gl);
      CubismWebGLOffscreenManager
        .getInstance()
        .releaseStaleRenderTextures(gl);
    } else {
      this.hitTester.clear();
    }
    this.scheduleNextFrame();
  }
}
