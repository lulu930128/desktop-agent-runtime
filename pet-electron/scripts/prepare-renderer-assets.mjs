import fs from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(import.meta.dirname, "..", "..");
const rendererPublic = path.resolve(import.meta.dirname, "..", "renderer", "public", "live2d");
const shaderSource = path.resolve(repoRoot, "vendor", "CubismWebFramework", "Shaders", "WebGL");
const shaderTarget = path.resolve(rendererPublic, "Framework", "Shaders", "WebGL");
const coreSource = path.resolve(
  repoRoot,
  "Open-LLM-VTuber",
  "frontend",
  "libs",
  "live2dcubismcore.min.js"
);
const coreTarget = path.resolve(rendererPublic, "live2dcubismcore.min.js");

fs.mkdirSync(shaderTarget, { recursive: true });
fs.copyFileSync(coreSource, coreTarget);

for (const entry of fs.readdirSync(shaderSource, { withFileTypes: true })) {
  if (!entry.isFile()) {
    continue;
  }
  fs.copyFileSync(path.join(shaderSource, entry.name), path.join(shaderTarget, entry.name));
}

console.log("[pet-electron] renderer assets prepared");
