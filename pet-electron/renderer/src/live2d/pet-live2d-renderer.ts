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

export class PetLive2DRenderer {
  private readonly canvas: HTMLCanvasElement;
  private readonly subdelegate: LAppSubdelegate;
  private model: LAppModel | null;
  private modelDescriptor: ModelDescriptor | null;
  private rafId: number | null;
  private disposed: boolean;

  public constructor(canvas: HTMLCanvasElement) {
    ensureCubismReady();
    this.canvas = canvas;
    this.subdelegate = new LAppSubdelegate(canvas);
    if (!this.subdelegate.initialize()) {
      throw new Error("Unable to initialize Live2D WebGL context.");
    }

    this.model = null;
    this.modelDescriptor = null;
    this.rafId = null;
    this.disposed = false;
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

    const { modelDir, fileName } = splitModelUrl(modelUrl);
    const nextModel = new LAppModel();
    nextModel.setSubdelegate(this.subdelegate);
    this.model = nextModel;
    this.subdelegate.getTextureManager().releaseTextures();
    console.info("[pet-renderer] Loading model assets", { modelDir, fileName });
    nextModel.loadAssets(modelDir, fileName);
  }

  public resize(): void {
    this.subdelegate.resize();
  }

  public dispose(): void {
    this.disposed = true;
    if (this.rafId !== null) {
      window.cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.releaseCurrentModel();
    this.subdelegate.release();
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
  }

  private renderFrame(): void {
    if (this.disposed) {
      return;
    }

    LAppPal.updateTime();
    this.subdelegate.resize();

    const gl = this.subdelegate.getGlManager().getGl();
    if (gl.isContextLost()) {
      console.warn("[pet-renderer] WebGL context lost; waiting for recovery.");
      this.rafId = window.requestAnimationFrame(this.renderFrame);
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

      const matrix = this.model.getModelMatrix();
      if (matrix && this.modelDescriptor) {
        matrix.loadIdentity();

        const targetHeight = Math.min(
          1.85,
          Math.max(1.45, this.modelDescriptor.sizeHint * 1.9)
        );

        matrix.setHeight(targetHeight);
        matrix.centerX(0);
        matrix.bottom(1.02);
      }

      readyModel.update();
      readyModel.draw(projection);

      CubismWebGLOffscreenManager.getInstance().endFrameProcess(gl);
      CubismWebGLOffscreenManager
        .getInstance()
        .releaseStaleRenderTextures(gl);
    }
    this.rafId = window.requestAnimationFrame(this.renderFrame);
  }
}
