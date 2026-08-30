import { CubismMatrix44 } from "@framework/math/cubismmatrix44";
import { LAppModel } from "./lappmodel";

type CanvasPoint = {
  x: number;
  y: number;
};

export type Live2DHitTestResult = {
  hit: boolean;
  source: "hit-area" | "drawable-mesh" | "none";
};

export class Live2DHitTester {
  private projectionMatrix: CubismMatrix44 | null = null;
  private hasOfficialHitAreas = false;

  public updateFrame(
    projectionMatrix: CubismMatrix44,
    hasOfficialHitAreas: boolean
  ): void {
    this.projectionMatrix = projectionMatrix.clone();
    this.hasOfficialHitAreas = hasOfficialHitAreas;
  }

  public clear(): void {
    this.projectionMatrix = null;
    this.hasOfficialHitAreas = false;
  }

  public hitTestCanvasPoint(
    canvas: HTMLCanvasElement,
    model: LAppModel | null,
    clientX: number,
    clientY: number
  ): Live2DHitTestResult {
    if (!model || !this.projectionMatrix) {
      return { hit: false, source: "none" };
    }

    const rect = canvas.getBoundingClientRect();
    return this.hitTestViewportPoint(
      canvas,
      model,
      clientX - rect.left,
      clientY - rect.top
    );
  }

  public hitTestViewportPoint(
    canvas: HTMLCanvasElement,
    model: LAppModel | null,
    viewportX: number,
    viewportY: number
  ): Live2DHitTestResult {
    if (!model || !this.projectionMatrix) {
      return { hit: false, source: "none" };
    }

    const viewPoint = this.toViewPoint(canvas, viewportX, viewportY);
    if (!viewPoint) {
      return { hit: false, source: "none" };
    }

    if (this.hasOfficialHitAreas) {
      return model.hitTestAnyArea(viewPoint.x, viewPoint.y)
        ? { hit: true, source: "hit-area" }
        : { hit: false, source: "none" };
    }

    return model.hitTestDrawableMeshes(viewPoint.x, viewPoint.y)
      ? { hit: true, source: "drawable-mesh" }
      : { hit: false, source: "none" };

  }

  private toViewPoint(
    canvas: HTMLCanvasElement,
    viewportX: number,
    viewportY: number
  ): CanvasPoint | null {
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return null;
    }

    if (
      viewportX < 0 ||
      viewportY < 0 ||
      viewportX > rect.width ||
      viewportY > rect.height
    ) {
      return null;
    }

    const deviceX = (viewportX / rect.width) * 2 - 1;
    const deviceY = 1 - (viewportY / rect.height) * 2;

    return {
      x: this.projectionMatrix.invertTransformX(deviceX),
      y: this.projectionMatrix.invertTransformY(deviceY)
    };
  }
}
