import { CubismFramework, Option } from "@framework/live2dcubismframework";
import { CubismMatrix44 } from "@framework/math/cubismmatrix44";
import { CubismWebGLOffscreenManager } from "@framework/rendering/cubismoffscreenmanager";
import * as LAppDefine from "./lappdefine";
import { LAppModel } from "./lappmodel";
import { LAppPal } from "./lapppal";
import { LAppSubdelegate } from "./lappsubdelegate";

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
  private readonly hitTestPixel: Uint8Array;
  private model: LAppModel | null;
  private modelDescriptor: ModelDescriptor | null;
  private rafId: number | null;
  private renderTimerId: number | null;
  private disposed: boolean;
  private zoomScale: number;
  private outfitParameterId: string | null;
  private outfitParameterIndex: number | null;
  private outfitValue: number;
  private expressionParameters: Record<string, number>;
  private aiState: string;
  private pointerActive: boolean;
  private forceActiveUntilMs: number;
  private cachedDrawableBounds: DrawableBounds | null;
  private cachedDrawableBoundsAtMs: number;
  private lastResizeWidth: number;
  private lastResizeHeight: number;
  private lastResizeDpr: number;

  public constructor(canvas: HTMLCanvasElement) {
    ensureCubismReady();
    this.canvas = canvas;
    this.subdelegate = new LAppSubdelegate(canvas);
    if (!this.subdelegate.initialize()) {
      throw new Error("Unable to initialize Live2D WebGL context.");
    }

    this.hitTestPixel = new Uint8Array(4);
    this.model = null;
    this.modelDescriptor = null;
    this.rafId = null;
    this.renderTimerId = null;
    this.disposed = false;
    this.zoomScale = 1.0;
    this.outfitParameterId = null;
    this.outfitParameterIndex = null;
    this.outfitValue = 0;
    this.expressionParameters = {};
    this.aiState = "idle";
    this.pointerActive = false;
    this.forceActiveUntilMs = 0;
    this.cachedDrawableBounds = null;
    this.cachedDrawableBoundsAtMs = 0;
    this.lastResizeWidth = -1;
    this.lastResizeHeight = -1;
    this.lastResizeDpr = -1;
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

  public setZoomScale(nextZoomScale: number): number {
    if (!Number.isFinite(nextZoomScale)) {
      return this.zoomScale;
    }

    this.zoomScale = Math.min(2.25, Math.max(0.55, nextZoomScale));
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
    const nextScale = this.zoomScale * (direction > 0 ? 1.08 : 1 / 1.08);
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

    const gl = this.subdelegate.getGlManager().getGl();
    if (!gl || gl.isContextLost()) {
      return false;
    }

    const rect = this.canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }

    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    if (localX < 0 || localY < 0 || localX > rect.width || localY > rect.height) {
      return false;
    }

    const pixelX = Math.max(
      0,
      Math.min(this.canvas.width - 1, Math.floor((localX / rect.width) * this.canvas.width))
    );
    const pixelY = Math.max(
      0,
      Math.min(
        this.canvas.height - 1,
        this.canvas.height - 1 - Math.floor((localY / rect.height) * this.canvas.height)
      )
    );

    try {
      gl.readPixels(
        pixelX,
        pixelY,
        1,
        1,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        this.hitTestPixel
      );
      return this.hitTestPixel[3] >= 20;
    } catch (error) {
      console.warn("[pet-renderer] Canvas hit test failed", error);
      return false;
    }
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
    this.invalidateDrawableBounds();
  }

  private getDrawableBounds(readyModel: LAppModel): DrawableBounds | null {
    const now = performance.now();
    if (this.cachedDrawableBounds && now - this.cachedDrawableBoundsAtMs < 1200) {
      return this.cachedDrawableBounds;
    }

    this.cachedDrawableBounds = this.measureDrawableBounds(readyModel);
    this.cachedDrawableBoundsAtMs = now;
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

        const targetHeight = Math.min(
          2.8,
          Math.max(0.85, this.modelDescriptor.sizeHint * 1.9)
        );

        matrix.setHeight(targetHeight);

        const bounds = this.getDrawableBounds(readyModel);
        if (bounds) {
          const centerX = (bounds.left + bounds.right) / 2;
          const centerY = (bounds.top + bounds.bottom) / 2;
          matrix.translate(
            -centerX * matrix.getScaleX(),
            -centerY * matrix.getScaleY()
          );
        } else {
          matrix.centerX(0);
          matrix.centerY(0);
        }
      }

      readyModel.draw(projection);

      CubismWebGLOffscreenManager.getInstance().endFrameProcess(gl);
      CubismWebGLOffscreenManager
        .getInstance()
        .releaseStaleRenderTextures(gl);
    }
    this.scheduleNextFrame();
  }
}
