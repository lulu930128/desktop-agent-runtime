import { boot, makeBridge, syntheticRequest } from "./preview-bridge";
void boot(makeBridge(syntheticRequest)).catch((error) => {
  document.getElementById("app")!.textContent = `SYNTHETIC preview unavailable: ${String(error)}`;
});
