import type { WorkPanelBridge } from "./work-panel/types";
import fixture from "./synthetic.json";

export type Request = (command: string, payload?: Record<string, unknown>) => Promise<any>;
export const unavailable = () => ({ ok: false, error: "SYNTHETIC preview: unavailable; no operation performed" });
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));

// No provider, IPC, filesystem or business owner is available in this preview.
export const syntheticRequest: Request = async (command, payload = {}) => {
  if (command === "getHistories" && payload.historyUid && payload.historyUid !== "synthetic-history") return unavailable();
  if (Object.prototype.hasOwnProperty.call(fixture, command) && command !== "context" && command !== "revision") {
    return copy(fixture[command]);
  }
  return unavailable();
};

export function makeBridge(request: Request): WorkPanelBridge {
  return {
    schedule: (action, payload) => request(`schedule.${action}`, payload),
    getState: () => request("getState"),
    getData: () => request("getData"),
    getChatState: () => request("getChatState"),
    getChatHistory: () => request("getHistories"),
    getProfile: () => request("getProfile"),
    getHistories: (historyUid) => request("getHistories", { historyUid }),
    getMemories: () => request("getMemories"),
    getTools: () => request("getTools"),
    applyProfile: async () => unavailable(),
    createHistory: async () => unavailable(),
    selectHistory: async () => unavailable(),
    deleteHistory: async () => unavailable(),
    memoryAction: async () => unavailable(),
    sendText: async () => unavailable(),
    refreshMail: async () => unavailable(),
    getMailMessage: async () => unavailable(),
    control: async () => unavailable(),
    closeWindow: showUnavailable,
    minimizeWindow: showUnavailable,
    toggleMaximizeWindow: showUnavailable,
    onState: () => () => undefined,
    onData: () => () => undefined,
    onChatState: () => () => undefined
  };
}

function showUnavailable(): void {
  const toast = document.querySelector<HTMLElement>("[data-toast]");
  if (toast) {
    toast.textContent = unavailable().error;
    toast.className = "toast is-visible is-error";
  }
}

export async function boot(bridge: WorkPanelBridge): Promise<void> {
  window.kuroWorkPanel = bridge;
  const mode = new URLSearchParams(location.search).get("view") || "chat";
  for (const [key, value] of Object.entries({mode, source: "all", "settings-section": "assistant", compact: "false", "reduce-motion": "true"})) {
    localStorage.setItem(`kuro.work-panel.${key}`, value);
  }
  document.title = "SYNTHETIC · Original Git Work Companion · NOT ACCEPTED";
  await import("./work-panel/main");
  // Original source remains untouched. Block the only local file-picker path
  // before its original handler; no private attachment reads in a preview.
  document.addEventListener("click", (event) => {
    const target = event.target as Element;
    if (target.closest("[data-attach], [data-file-input]")) {
      event.preventDefault(); event.stopImmediatePropagation(); showUnavailable();
    }
  }, true);
  document.addEventListener("drop", (event) => { event.preventDefault(); event.stopImmediatePropagation(); }, true);
}
