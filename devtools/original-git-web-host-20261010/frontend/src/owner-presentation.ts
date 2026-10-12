import type { OwnerTransport } from "./owner-bridge";

export function isImeSubmit(event: Pick<KeyboardEvent, "key" | "isComposing" | "keyCode">, composing: boolean): boolean {
  return event.key === "Enter" && (event.isComposing || composing || event.keyCode === 229);
}

export function installPresentationGuards(transport: OwnerTransport): void {
  let composing = false;
  document.addEventListener("compositionstart", () => { composing = true; }, true);
  document.addEventListener("compositionend", () => { composing = false; }, true);
  document.addEventListener("keydown", event => {
    if (event.target instanceof HTMLTextAreaElement && isImeSubmit(event, composing)) event.stopImmediatePropagation();
  }, true);
  // Use original styles and control positions. No CSS/geometry patch for W1 drift.
  let timeline: Array<Record<string, unknown>> = [];
  let data: Record<string, any> | null = null;
  let notificationWrites = false;
  transport.on("onNotificationCapability", value => { notificationWrites = value?.consumerWriteContract === "kuro.core.notification-command.v1"; queueMicrotask(project); });
  transport.on("onData", value => { data = value; queueMicrotask(project); });
  transport.on("onChatState", state => { timeline = Array.isArray(state.timeline) ? state.timeline : []; queueMicrotask(project); });
  const unsupported = new Set(["手動更新 Mail", "重試啟動對話", "停止對話服務", "重新啟動 Kuro"]);
  function project(): void {
    for (const node of document.querySelectorAll<HTMLButtonElement>("button")) {
      if (unsupported.has(node.textContent?.trim() || "")) {
        node.disabled = true;
        node.title = "目前尚無具備所需權限、版本與重複保護的正式操作介面。";
      }
      if (node.textContent?.trim() === "提醒設定") {
        node.disabled = !notificationWrites;
        node.title = notificationWrites ? "由 Core 驗證版本，Qt 確認後套用。" : "Core 尚未提供受控通知寫入 contract。";
      }
    }
    for (const node of document.querySelectorAll<HTMLTextAreaElement>(".memory-input")) {
      node.maxLength = 260; node.title = "每筆記憶最多 260 字；寫入前需確認。";
    }
    for (const node of document.querySelectorAll<HTMLButtonElement>(".reminder-row button")) {
      node.disabled = !notificationWrites; node.title = notificationWrites ? "由 Core 驗證版本，Qt 確認後套用。" : "此通知操作尚缺 Core 版本與重複保護 contract；既有 Qt 通知配送不受影響。";
    }
    const list = document.querySelector("[data-message-inner]");
    const previous = list?.querySelector<HTMLElement>("[data-owner-tools]");
    const toolKey = JSON.stringify(timeline);
    if (previous && previous.dataset.key !== toolKey) previous.remove();
    if (list && timeline.length && !list.querySelector("[data-owner-tools]")) {
      const box = document.createElement("div"); box.className = "message"; box.dataset.ownerTools = "true"; box.dataset.key = toolKey;
      box.setAttribute("role", "log"); box.setAttribute("aria-label", "工具執行事件");
      for (const row of timeline) {
        const entry = document.createElement("p");
        entry.textContent = `工具事件 · ${String(row.tool_name || "")} · ${String(row.status || "")}`;
        box.appendChild(entry);
      }
      list.appendChild(box);
    }
    if (data) {
      const canonical = data.canonical;
      const spans = document.querySelectorAll<HTMLElement>(".today-summary > span");
      const values = canonical
        ? [`${canonical.counts?.total ?? "未提供"} 個 Core 項目`, canonical.complete ? "已提供來源完整" : "來源不完整", `Snapshot ${canonical.generatedAt ?? "時間未提供"}`]
        : ["Core 項目未提供", "無法確認來源", "尚未收到正式 Today"];
      if (!data.ok || data.transportStale) values[1] = "Core 讀取失敗；既有資料尚未重新確認";
      spans.forEach((span, index) => { if (span.textContent !== values[index]) span.textContent = values[index]; });
      const source = document.querySelector<HTMLElement>(".source-status-copy");
      if (source && canonical) {
        const global = `Core · ${canonical.asOf ?? "時間未提供"} · ${canonical.timezone ?? "時區未提供"} · limitations: ${(canonical.limitations || []).join(", ") || "無"}`;
        if (!source.dataset.ownerGlobal || !source.textContent?.endsWith(global)) {
          const prior = source.textContent?.split("\nCore ·")[0] || "";
          source.textContent = `${prior}\n${global}`; source.dataset.ownerGlobal = "true";
        }
      }
    }
    for (const note of document.querySelectorAll<HTMLElement>(".settings-note")) {
      if (note.textContent?.includes("Electron 會先顯示原生確認視窗"))
        note.textContent = note.textContent.replace("Electron 會先顯示原生確認視窗", "Qt 會先顯示原生確認視窗");
    }
  }
  new MutationObserver(() => { project(); }).observe(document.getElementById("app")!, {childList: true, subtree: true});
}
