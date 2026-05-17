const { contextBridge, ipcRenderer } = require("electron");

const DEFAULT_BACKEND_BASE_URL =
  process.env.KURO_BACKEND_BASE_URL || "http://127.0.0.1:23456";
const DEFAULT_BACKEND_WS_URL =
  process.env.KURO_BACKEND_WS_URL || "ws://127.0.0.1:23456/client-ws";

function normalizeConfigValue(value, fallback) {
  const normalized = String(value || "").trim();
  return normalized || fallback;
}

function onPetCommand(listener) {
  if (typeof listener !== "function") {
    return () => undefined;
  }

  const wrapped = (_event, payload) => listener(payload || {});
  ipcRenderer.on("pet-command", wrapped);
  return () => ipcRenderer.removeListener("pet-command", wrapped);
}

const bridge = {
  getInitialConfig() {
    let bootstrapConfig = null;
    try {
      bootstrapConfig = ipcRenderer.sendSync("get-bootstrap-config");
    } catch (error) {
      console.warn("[pet-electron] Failed to read bootstrap config:", error);
    }

    return {
      baseUrl: normalizeConfigValue(DEFAULT_BACKEND_BASE_URL, "http://127.0.0.1:23456"),
      wsUrl: normalizeConfigValue(DEFAULT_BACKEND_WS_URL, "ws://127.0.0.1:23456/client-ws"),
      ...(bootstrapConfig && typeof bootstrapConfig === "object" ? bootstrapConfig : {})
    };
  },
  reportFrontendState(payload) {
    ipcRenderer.send("pet-frontend-state", payload);
  },
  updateComponentHover(componentName, hovered) {
    ipcRenderer.send("update-component-hover", componentName, Boolean(hovered));
  },
  setIgnoreMouseEvent(ignore) {
    ipcRenderer.send("set-ignore-mouse-event", Boolean(ignore));
  },
  startWindowDrag(screenX, screenY) {
    ipcRenderer.send("start-window-drag", {
      screenX: Number(screenX),
      screenY: Number(screenY)
    });
  },
  updateWindowDrag(screenX, screenY) {
    ipcRenderer.send("update-window-drag", {
      screenX: Number(screenX),
      screenY: Number(screenY)
    });
  },
  setPetWindowZoom(zoomScale) {
    ipcRenderer.send("set-pet-window-zoom", {
      zoomScale: Number(zoomScale)
    });
  },
  adjustPetWindowScale(scaleRatio) {
    ipcRenderer.send("adjust-pet-window-scale", {
      scaleRatio: Number(scaleRatio)
    });
  },
  endWindowDrag() {
    ipcRenderer.send("end-window-drag");
  },
  showContextMenu() {
    ipcRenderer.send("show-context-menu");
  },
  onCommand: onPetCommand
};

contextBridge.exposeInMainWorld("kuroPetElectron", bridge);
contextBridge.exposeInMainWorld("api", {
  startWindowDrag: bridge.startWindowDrag,
  updateWindowDrag: bridge.updateWindowDrag,
  setPetWindowZoom: bridge.setPetWindowZoom,
  adjustPetWindowScale: bridge.adjustPetWindowScale,
  endWindowDrag: bridge.endWindowDrag,
  updateComponentHover: bridge.updateComponentHover,
  setIgnoreMouseEvent: bridge.setIgnoreMouseEvent,
  showContextMenu: bridge.showContextMenu,
  onToggleInputSubtitle() {
    return () => undefined;
  },
  updateConfigFiles() {
    return undefined;
  }
});
contextBridge.exposeInMainWorld("electron", {
  process: {
    platform: process.platform
  }
});
