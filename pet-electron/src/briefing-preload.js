const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kuroBriefing", {
  getState() {
    return ipcRenderer.invoke("briefing-get-state");
  },
  getData() {
    return ipcRenderer.invoke("briefing-get-data");
  },
  refreshMail() {
    return ipcRenderer.invoke("briefing-refresh-mail");
  },
  getMailPreferences() {
    return ipcRenderer.invoke("briefing-get-mail-preferences");
  },
  saveMailPreferences(preferences) {
    return ipcRenderer.invoke("briefing-save-mail-preferences", preferences);
  },
  getMailRules() {
    return ipcRenderer.invoke("briefing-get-mail-rules");
  },
  saveMailRules(rulesPayload) {
    return ipcRenderer.invoke("briefing-save-mail-rules", rulesPayload);
  },
  getMailMessage(messageId) {
    return ipcRenderer.invoke("briefing-get-mail-message", messageId);
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
