const { contextBridge, ipcRenderer } = require("electron");

function onChannel(channel, callback) {
  if (typeof callback !== "function") {
    return () => undefined;
  }
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

const briefingBridge = {
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
    return onChannel("briefing-state", callback);
  },
  onData(callback) {
    return onChannel("briefing-data", callback);
  }
};

contextBridge.exposeInMainWorld("kuroBriefing", briefingBridge);

contextBridge.exposeInMainWorld("kuroWorkPanel", {
  ...briefingBridge,
  schedule(action, payload) {
    return ipcRenderer.invoke("work-panel-schedule", action, payload || {});
  },
  getChatState() {
    return ipcRenderer.invoke("reader-get-state");
  },
  getChatHistory() {
    return ipcRenderer.invoke("work-panel-get-chat-history");
  },
  getProfile() {
    return ipcRenderer.invoke("work-panel-get-profile");
  },
  applyProfile(payload) {
    return ipcRenderer.invoke("work-panel-apply-profile", payload || {});
  },
  getHistories(historyUid) {
    return ipcRenderer.invoke("work-panel-get-histories", historyUid || "");
  },
  createHistory() {
    return ipcRenderer.invoke("work-panel-create-history");
  },
  selectHistory(historyUid) {
    return ipcRenderer.invoke("work-panel-select-history", historyUid);
  },
  deleteHistory(historyUid, historyTitle) {
    return ipcRenderer.invoke("work-panel-delete-history", historyUid, historyTitle || "");
  },
  getMemories() {
    return ipcRenderer.invoke("work-panel-get-memories");
  },
  memoryAction(action, payload) {
    return ipcRenderer.invoke("work-panel-memory-action", action, payload || {});
  },
  getTools() {
    return ipcRenderer.invoke("work-panel-get-tools");
  },
  sendText(text, attachments) {
    return ipcRenderer.invoke("reader-send-text", text, attachments || []);
  },
  control(action, payload) {
    return ipcRenderer.invoke("work-panel-control", action, payload || {});
  },
  onChatState(callback) {
    return onChannel("reader-state", callback);
  }
});
