import fs from "node:fs";
import path from "node:path";

const projectRoot = path.resolve(import.meta.dirname, "..");
const rendererPublic = path.resolve(import.meta.dirname, "..", "renderer", "public", "live2d");
const shaderSource = path.resolve(projectRoot, "vendor", "CubismWebFramework", "Shaders", "WebGL");
const shaderTarget = path.resolve(rendererPublic, "Framework", "Shaders", "WebGL");
const coreTarget = path.resolve(rendererPublic, "live2dcubismcore.min.js");

fs.mkdirSync(shaderTarget, { recursive: true });
if (!fs.existsSync(coreTarget)) {
  throw new Error(`Missing Live2D Cubism Core runtime at ${coreTarget}`);
}

for (const entry of fs.readdirSync(shaderSource, { withFileTypes: true })) {
  if (!entry.isFile()) {
    continue;
  }
  fs.copyFileSync(path.join(shaderSource, entry.name), path.join(shaderTarget, entry.name));
}

console.log("[pet-electron] renderer assets prepared");
