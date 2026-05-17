import { defineConfig } from "vite";
import path from "path";

export default defineConfig({
  root: path.resolve(__dirname, "renderer"),
  base: "./",
  resolve: {
    alias: {
      "@framework": path.resolve(__dirname, "..", "vendor", "CubismWebFramework", "src")
    }
  },
  build: {
    outDir: path.resolve(__dirname, "renderer-dist"),
    emptyOutDir: true,
    sourcemap: true
  }
});
