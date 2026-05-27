const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kuroBriefing", {
  getState() {
    return ipcRenderer.invoke("briefing-get-state");
  },
  getData() {
    return ipcRenderer.invoke("briefing-get-data");
  },
  closeWindow() {
    ipcRenderer.send("briefing-close");
  },
  minimizeWindow() {
    ipcRenderer.send("briefing-minimize");
  },
  toggleMaximizeWindow() {
    ipcRenderer.send("briefing-toggle-maximize");
  },
  onState(callback) {
    if (typeof callback !== "function") {
      return () => undefined;
    }
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("briefing-state", listener);
    return () => ipcRenderer.removeListener("briefing-state", listener);
  },
  onData(callback) {
    if (typeof callback !== "function") {
      return () => undefined;
    }
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("briefing-data", listener);
    return () => ipcRenderer.removeListener("briefing-data", listener);
  }
});
