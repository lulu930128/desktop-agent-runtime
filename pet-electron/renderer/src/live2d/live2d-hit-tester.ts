import { CubismMatrix44 } from "@framework/math/cubismmatrix44";
import { LAppModel } from "./lappmodel";

type CanvasPoint = {
  x: number;
  y: number;
};

export type Live2DHitTestResult = {
  hit: boolean;
  source: "hit-area" | "drawable-bounds" | "none";
};

export class Live2DHitTester {
  private projectionMatrix: CubismMatrix44 | null = null;

  public updateProjection(projectionMatrix: CubismMatrix44): void {
    this.projectionMatrix = projectionMatrix.clone();
  }

  public clear(): void {
    this.projectionMatrix = null;
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

    const viewPoint = this.toViewPoint(canvas, clientX, clientY);
    if (!viewPoint) {
      return { hit: false, source: "none" };
    }

    if (model.hitTestAnyArea(viewPoint.x, viewPoint.y)) {
      return { hit: true, source: "hit-area" };
    }

    if (model.hitTestDrawableBounds(viewPoint.x, viewPoint.y)) {
      return { hit: true, source: "drawable-bounds" };
    }

    return { hit: false, source: "none" };
  }

  private toViewPoint(
    canvas: HTMLCanvasElement,
    clientX: number,
    clientY: number
  ): CanvasPoint | null {
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return null;
    }

    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    if (localX < 0 || localY < 0 || localX > rect.width || localY > rect.height) {
      return null;
    }

    const deviceX = (localX / rect.width) * 2 - 1;
    const deviceY = 1 - (localY / rect.height) * 2;

    return {
      x: this.projectionMatrix.invertTransformX(deviceX),
      y: this.projectionMatrix.invertTransformY(deviceY)
    };
  }
}
