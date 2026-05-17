const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kuroReader", {
  getState() {
    return ipcRenderer.invoke("reader-get-state");
  },
  sendText(text) {
    return ipcRenderer.invoke("reader-send-text", text);
  },
  closeWindow() {
    ipcRenderer.send("reader-close");
  },
  onState(callback) {
    if (typeof callback !== "function") {
      return () => undefined;
    }
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("reader-state", listener);
    return () => ipcRenderer.removeListener("reader-state", listener);
  }
});
