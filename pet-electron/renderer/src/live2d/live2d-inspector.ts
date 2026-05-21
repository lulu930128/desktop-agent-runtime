import type { CubismMatrix44 } from "@framework/math/cubismmatrix44";

export type Live2DInspectorBounds = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type Live2DInspectorParameter = {
  index: number;
  id: string;
  value: number;
  defaultValue: number;
  minValue: number;
  maxValue: number;
};

export type Live2DInspectorPart = {
  index: number;
  id: string;
  opacity: number;
};

export type Live2DInspectorDrawable = {
  index: number;
  id: string;
  opacity: number;
  visible: boolean;
  vertexCount: number;
  bounds: Live2DInspectorBounds | null;
};

export type Live2DInspectorHitArea = {
  index: number;
  name: string;
  drawableId: string;
  drawableIndex: number;
  visible: boolean;
  opacity: number;
  bounds: Live2DInspectorBounds | null;
};

export type Live2DInspectorExpression = {
  index: number;
  id: string;
  fileName: string;
  loaded: boolean;
};

export type Live2DInspectorMotion = {
  index: number;
  fileName: string;
  soundFileName: string;
  fadeInSeconds: number;
  fadeOutSeconds: number;
  loaded: boolean;
};

export type Live2DInspectorMotionGroup = {
  name: string;
  motions: Live2DInspectorMotion[];
};

export type Live2DInspectorModelSnapshot = {
  canvasWidth: number;
  canvasHeight: number;
  pixelsPerUnit: number;
  expressions: Live2DInspectorExpression[];
  motionGroups: Live2DInspectorMotionGroup[];
  hitAreas: Live2DInspectorHitArea[];
  parameters: Live2DInspectorParameter[];
  parts: Live2DInspectorPart[];
  drawables: Live2DInspectorDrawable[];
  eyeBlinkParameterIds: string[];
  lipSyncParameterIds: string[];
  features: Record<string, boolean>;
  loadedExpressionCount: number;
  loadedMotionCount: number;
};

export type Live2DInspectorSnapshot = {
  ready: boolean;
  overlayEnabled: boolean;
  modelUrl: string;
  zoomScale: number;
  hostBounds: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  anchorScreenPoint: {
    x: number;
    y: number;
  };
  canvas: {
    width: number;
    height: number;
    clientWidth: number;
    clientHeight: number;
    devicePixelRatio: number;
  };
  modelBounds: Live2DInspectorBounds | null;
  model: Live2DInspectorModelSnapshot | null;
};

type Live2DOverlayFrame = {
  projection: CubismMatrix44;
  modelMatrix: CubismMatrix44;
};

type OverlayMetrics = {
  cssWidth: number;
  cssHeight: number;
  scaleX: number;
  scaleY: number;
};

type CanvasPoint = {
  x: number;
  y: number;
};

const MAX_DRAWABLE_BOUNDS = 160;

function finiteOrZero(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

function formatNumber(value: number, digits = 2): string {
  if (!Number.isFinite(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function compactText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 1))}...`;
}

export class Live2DDebugOverlay {
  private readonly sourceCanvas: HTMLCanvasElement;
  private readonly canvas: HTMLCanvasElement;
  private readonly context: CanvasRenderingContext2D;
  private enabled: boolean;

  public constructor(sourceCanvas: HTMLCanvasElement) {
    this.sourceCanvas = sourceCanvas;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "live2d-debug-overlay";
    this.canvas.setAttribute("aria-hidden", "true");
    this.canvas.style.display = "none";
    this.canvas.style.pointerEvents = "none";

    const context = this.canvas.getContext("2d");
    if (!context) {
      throw new Error("Unable to initialize Live2D debug overlay context.");
    }
    this.context = context;
    this.enabled = false;

    const parent = sourceCanvas.parentElement;
    if (parent) {
      parent.appendChild(this.canvas);
    } else {
      sourceCanvas.insertAdjacentElement("afterend", this.canvas);
    }
  }

  public setEnabled(enabled: boolean): void {
    this.enabled = Boolean(enabled);
    this.canvas.style.display = this.enabled ? "block" : "none";
    if (!this.enabled) {
      this.clear();
    }
  }

  public isEnabled(): boolean {
    return this.enabled;
  }

  public clear(): void {
    const metrics = this.syncSize();
    this.context.setTransform(metrics.scaleX, 0, 0, metrics.scaleY, 0, 0);
    this.context.clearRect(0, 0, metrics.cssWidth, metrics.cssHeight);
    this.context.setTransform(1, 0, 0, 1, 0, 0);
  }

  public render(
    snapshot: Live2DInspectorSnapshot,
    frame: Live2DOverlayFrame | null
  ): void {
    if (!this.enabled) {
      return;
    }

    const metrics = this.syncSize();
    const ctx = this.context;
    ctx.save();
    ctx.setTransform(metrics.scaleX, 0, 0, metrics.scaleY, 0, 0);
    ctx.clearRect(0, 0, metrics.cssWidth, metrics.cssHeight);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    if (frame && snapshot.model) {
      this.drawDrawableBounds(ctx, metrics, frame, snapshot.model.drawables);
      this.drawBounds(
        ctx,
        metrics,
        frame,
        snapshot.modelBounds,
        "rgba(120, 255, 170, 0.9)",
        2
      );
      this.drawHitAreas(ctx, metrics, frame, snapshot.model.hitAreas);
    }

    this.drawAnchor(ctx, snapshot);
    this.drawHud(ctx, metrics, snapshot);

    ctx.restore();
  }

  public dispose(): void {
    this.clear();
    this.canvas.remove();
  }

  private syncSize(): OverlayMetrics {
    const rect = this.sourceCanvas.getBoundingClientRect();
    const cssWidth = Math.max(1, rect.width || this.sourceCanvas.clientWidth || 1);
    const cssHeight = Math.max(1, rect.height || this.sourceCanvas.clientHeight || 1);
    const pixelWidth = Math.max(
      1,
      this.sourceCanvas.width || Math.round(cssWidth * (window.devicePixelRatio || 1))
    );
    const pixelHeight = Math.max(
      1,
      this.sourceCanvas.height || Math.round(cssHeight * (window.devicePixelRatio || 1))
    );

    if (this.canvas.width !== pixelWidth) {
      this.canvas.width = pixelWidth;
    }
    if (this.canvas.height !== pixelHeight) {
      this.canvas.height = pixelHeight;
    }

    return {
      cssWidth,
      cssHeight,
      scaleX: pixelWidth / cssWidth,
      scaleY: pixelHeight / cssHeight
    };
  }

  private modelPointToCanvas(
    metrics: OverlayMetrics,
    frame: Live2DOverlayFrame,
    x: number,
    y: number
  ): CanvasPoint {
    const viewX = frame.modelMatrix.transformX(x);
    const viewY = frame.modelMatrix.transformY(y);
    const deviceX = frame.projection.transformX(viewX);
    const deviceY = frame.projection.transformY(viewY);
    return {
      x: ((deviceX + 1) / 2) * metrics.cssWidth,
      y: ((1 - deviceY) / 2) * metrics.cssHeight
    };
  }

  private boundsToCanvasRect(
    metrics: OverlayMetrics,
    frame: Live2DOverlayFrame,
    bounds: Live2DInspectorBounds | null
  ): { x: number; y: number; width: number; height: number } | null {
    if (!bounds) {
      return null;
    }

    const corners = [
      this.modelPointToCanvas(metrics, frame, bounds.left, bounds.top),
      this.modelPointToCanvas(metrics, frame, bounds.right, bounds.top),
      this.modelPointToCanvas(metrics, frame, bounds.right, bounds.bottom),
      this.modelPointToCanvas(metrics, frame, bounds.left, bounds.bottom)
    ];
    const left = Math.min(...corners.map((point) => point.x));
    const right = Math.max(...corners.map((point) => point.x));
    const top = Math.min(...corners.map((point) => point.y));
    const bottom = Math.max(...corners.map((point) => point.y));

    return {
      x: left,
      y: top,
      width: right - left,
      height: bottom - top
    };
  }

  private drawBounds(
    ctx: CanvasRenderingContext2D,
    metrics: OverlayMetrics,
    frame: Live2DOverlayFrame,
    bounds: Live2DInspectorBounds | null,
    color: string,
    lineWidth = 1
  ): void {
    const rect = this.boundsToCanvasRect(metrics, frame, bounds);
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      return;
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
  }

  private drawDrawableBounds(
    ctx: CanvasRenderingContext2D,
    metrics: OverlayMetrics,
    frame: Live2DOverlayFrame,
    drawables: Live2DInspectorDrawable[]
  ): void {
    const color = "rgba(78, 205, 255, 0.28)";
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    for (const drawable of drawables.slice(0, MAX_DRAWABLE_BOUNDS)) {
      if (!drawable.visible || drawable.opacity <= 0.001) {
        continue;
      }
      this.drawBounds(ctx, metrics, frame, drawable.bounds, color, 1);
    }
  }

  private drawHitAreas(
    ctx: CanvasRenderingContext2D,
    metrics: OverlayMetrics,
    frame: Live2DOverlayFrame,
    hitAreas: Live2DInspectorHitArea[]
  ): void {
    for (const hitArea of hitAreas) {
      const rect = this.boundsToCanvasRect(metrics, frame, hitArea.bounds);
      if (!rect || rect.width <= 0 || rect.height <= 0) {
        continue;
      }

      ctx.strokeStyle = hitArea.visible
        ? "rgba(255, 190, 80, 0.95)"
        : "rgba(255, 95, 95, 0.85)";
      ctx.lineWidth = 2;
      ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
      this.drawLabel(ctx, hitArea.name || hitArea.drawableId, rect.x + 4, rect.y + 14);
    }
  }

  private drawAnchor(ctx: CanvasRenderingContext2D, snapshot: Live2DInspectorSnapshot): void {
    const x = finiteOrZero(snapshot.anchorScreenPoint.x - snapshot.hostBounds.x);
    const y = finiteOrZero(snapshot.anchorScreenPoint.y - snapshot.hostBounds.y);
    ctx.strokeStyle = "rgba(255, 90, 160, 0.95)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x - 12, y);
    ctx.lineTo(x + 12, y);
    ctx.moveTo(x, y - 12);
    ctx.lineTo(x, y + 12);
    ctx.stroke();
    this.drawLabel(ctx, "anchor", x + 8, y - 8);
  }

  private drawLabel(ctx: CanvasRenderingContext2D, text: string, x: number, y: number): void {
    ctx.font = "11px Segoe UI, sans-serif";
    ctx.textBaseline = "top";
    const width = ctx.measureText(text).width + 8;
    ctx.fillStyle = "rgba(10, 14, 20, 0.72)";
    ctx.fillRect(x - 2, y - 2, width, 15);
    ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
    ctx.fillText(text, x + 2, y);
  }

  private drawHud(
    ctx: CanvasRenderingContext2D,
    metrics: OverlayMetrics,
    snapshot: Live2DInspectorSnapshot
  ): void {
    const model = snapshot.model;
    const motionCount =
      model?.motionGroups.reduce((count, group) => count + group.motions.length, 0) || 0;
    const lines = [
      `Live2D Inspector: ${snapshot.ready ? "ready" : "loading"}`,
      `model: ${compactText(snapshot.modelUrl || "-", 42)}`,
      `zoom: ${formatNumber(snapshot.zoomScale)} anchor: ${formatNumber(snapshot.anchorScreenPoint.x, 0)},${formatNumber(snapshot.anchorScreenPoint.y, 0)}`,
      model
        ? `params ${model.parameters.length} parts ${model.parts.length} drawables ${model.drawables.length}`
        : "params 0 parts 0 drawables 0",
      model
        ? `hit ${model.hitAreas.length} expressions ${model.expressions.length} motions ${motionCount}`
        : "hit 0 expressions 0 motions 0"
    ];

    ctx.font = "12px Segoe UI, sans-serif";
    ctx.textBaseline = "top";
    const padding = 8;
    const lineHeight = 16;
    const width = Math.min(
      metrics.cssWidth - 16,
      Math.max(...lines.map((line) => ctx.measureText(line).width)) + padding * 2
    );
    const height = lines.length * lineHeight + padding * 2;
    const x = 8;
    const y = 8;

    ctx.fillStyle = "rgba(6, 10, 16, 0.78)";
    ctx.fillRect(x, y, width, height);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
    ctx.strokeRect(x + 0.5, y + 0.5, width - 1, height - 1);
    ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
    for (let i = 0; i < lines.length; i += 1) {
      ctx.fillText(lines[i], x + padding, y + padding + i * lineHeight);
    }
  }
}
