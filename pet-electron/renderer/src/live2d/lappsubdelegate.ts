import { LAppGlManager } from "./lappglmanager";
import { LAppTextureManager } from "./lapptexturemanager";

export class LAppSubdelegate {
  private readonly canvas: HTMLCanvasElement;
  private readonly glManager: LAppGlManager;
  private readonly textureManager: LAppTextureManager;
  private frameBuffer: WebGLFramebuffer | null;

  public constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.glManager = new LAppGlManager();
    this.textureManager = new LAppTextureManager();
    this.frameBuffer = null;
  }

  public initialize(): boolean {
    if (!this.glManager.initialize(this.canvas)) {
      return false;
    }

    this.textureManager.setGlManager(this.glManager);
    this.resize();

    const gl = this.glManager.getGl();
    this.frameBuffer = gl.getParameter(gl.FRAMEBUFFER_BINDING);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    return true;
  }

  public resize(): void {
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const targetWidth = Math.max(
      1,
      Math.round((this.canvas.clientWidth || window.innerWidth || 640) * dpr)
    );
    const targetHeight = Math.max(
      1,
      Math.round((this.canvas.clientHeight || window.innerHeight || 960) * dpr)
    );

    if (this.canvas.width !== targetWidth || this.canvas.height !== targetHeight) {
      this.canvas.width = targetWidth;
      this.canvas.height = targetHeight;
    }

    const gl = this.glManager.getGl();
    gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
  }

  public release(): void {
    this.textureManager.releaseTextures();
    this.textureManager.release();
    this.frameBuffer = null;
  }

  public getCanvas(): HTMLCanvasElement {
    return this.canvas;
  }

  public getGlManager(): LAppGlManager {
    return this.glManager;
  }

  public getTextureManager(): LAppTextureManager {
    return this.textureManager;
  }

  public getFrameBuffer(): WebGLFramebuffer | null {
    return this.frameBuffer;
  }
}
