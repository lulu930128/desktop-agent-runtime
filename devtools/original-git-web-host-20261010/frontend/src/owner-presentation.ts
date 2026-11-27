import type { OwnerTransport } from "./owner-bridge";

type WindowEdge = "top" | "bottom" | "left" | "right" | "top-left" | "top-right" | "bottom-left" | "bottom-right";
const windowControls = "button, input, textarea, select, option, a, label, [contenteditable]:not([contenteditable='false']), [role='button'], [role='slider'], [role='dialog'], .window-actions, .privacy-indicators, [data-privacy-indicators]";

// CSS viewport coordinates, not physical pixels: Qt/Chromium owns DPI scaling.
export function windowResizeEdge(x: number, y: number, width: number, height: number, maximized: boolean): WindowEdge | null {
  if (maximized || ![x, y, width, height].every(Number.isFinite) || width < 12 || height < 12 || x < 0 || y < 0 || x >= width || y >= height) return null;
  const horizontal = x < 6 ? "left" : x >= width - 6 ? "right" : "";
  const vertical = y < 6 ? "top" : y >= height - 6 ? "bottom" : "";
  return (vertical && horizontal ? `${vertical}-${horizontal}` : vertical || horizontal || null) as WindowEdge | null;
}

export function windowGestureTarget(target: Element): "blocked" | "header" | "content" {
  if (target.closest(windowControls)) return "blocked";
  return target.closest(".chrome") && !target.closest(".rail") ? "header" : "content";
}

export function installWindowGestures(transport: OwnerTransport): void {
  let maximized = true; // No resize until the owner supplies authoritative state.
  let doubleClickInterval = 0;
  let startDragDistance = 0;
  let previous: {time: number; x: number; y: number} | null = null;
  const root = document.documentElement;
  const setState = (value: any) => {
    if (typeof value?.maximized === "boolean") maximized = value.maximized;
    if (maximized) root.style.cursor = "";
  };
  transport.on("onWindowState", setState);
  void transport.call("getWindowState").then(value => {
    if (!value.ok) return;
    setState(value);
    doubleClickInterval = value.doubleClickInterval;
    startDragDistance = value.startDragDistance;
  });
  const invoke = (method: string, payload = {}) => {
    void transport.call(method, payload).then(value => {
      // Keep native refusal inspectable; never retry a late mouse gesture.
      if (value.ok) delete root.dataset.ownerWindowError;
      else root.dataset.ownerWindowError = String(value.error || "window_gesture_failed");
    });
  };
  document.addEventListener("pointerdown", event => {
    if (!event.isTrusted || event.pointerType !== "mouse" || !event.isPrimary || event.button !== 0 || event.buttons !== 1
        || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || !(event.target instanceof Element)) return;
    const target = windowGestureTarget(event.target);
    if (target === "blocked") { previous = null; return; }
    const edge = windowResizeEdge(event.clientX, event.clientY, window.innerWidth, window.innerHeight, maximized);
    if (edge) {
      previous = null;
      event.preventDefault(); event.stopImmediatePropagation();
      invoke("startWindowResize", {edge});
    } else if (target === "header") {
      event.preventDefault(); event.stopImmediatePropagation();
      // Native move may consume mouseup/click. Recognize the second press
      // using the OS interval/distance instead of depending on DOM dblclick.
      const doubleClick = previous && event.timeStamp - previous.time >= 0 && event.timeStamp - previous.time <= doubleClickInterval
        && Math.abs(event.screenX - previous.x) < startDragDistance && Math.abs(event.screenY - previous.y) < startDragDistance;
      previous = doubleClick ? null : {time: event.timeStamp, x: event.screenX, y: event.screenY};
      invoke(doubleClick ? "toggleMaximizeWindow" : "startWindowMove");
    } else previous = null;
  }, true);
  document.addEventListener("pointermove", event => {
    const edge = event.target instanceof Element && windowGestureTarget(event.target) !== "blocked"
      ? windowResizeEdge(event.clientX, event.clientY, window.innerWidth, window.innerHeight, maximized) : null;
    const cursors = {top: "ns-resize", bottom: "ns-resize", left: "ew-resize", right: "ew-resize",
      "top-left": "nwse-resize", "bottom-right": "nwse-resize", "top-right": "nesw-resize", "bottom-left": "nesw-resize"};
    root.style.cursor = edge ? cursors[edge] : "";
  }, true);
  window.addEventListener("blur", () => { previous = null; root.style.cursor = ""; });
}

export function isImeSubmit(event: Pick<KeyboardEvent, "key" | "isComposing" | "keyCode">, composing: boolean): boolean {
  return event.key === "Enter" && (event.isComposing || composing || event.keyCode === 229);
}

export function installPresentationGuards(transport: OwnerTransport): void {
  installWindowGestures(transport);
  const projectAssistantSettings = installAssistantSettings(transport);
  const projectChatSpeechSettings = installChatSpeechSettings(transport);
  const projectToolSettings = installToolSettings(transport);
  const projectSources = installSourceOverview();
  const projectAttachments = installAttachmentHelp();
  const projectHistory = installHistoryListGuards(transport);
  let composing = false;
  document.addEventListener("compositionstart", () => { composing = true; }, true);
  document.addEventListener("compositionend", () => { composing = false; }, true);
  document.addEventListener("keydown", event => {
    if (event.target instanceof HTMLTextAreaElement && isImeSubmit(event, composing)) event.stopImmediatePropagation();
  }, true);
  // Project owner presentation without changing the immutable renderer sources.
  let timeline: Array<Record<string, unknown>> = [];
  let speechStatus = "";
  let missingSpeech = "";
  let data: Record<string, any> | null = null;
  let notificationWrites = false;
  transport.on("onNotificationCapability", value => { notificationWrites = value?.consumerWriteContract === "kuro.core.notification-command.v1"; queueMicrotask(project); });
  transport.on("onData", value => { data = value; queueMicrotask(project); });
  transport.on("onChatState", state => { timeline = Array.isArray(state.timeline) ? state.timeline : []; speechStatus = String(state.speechStatus || "");
    const missing = state.speechMissing || {};
    missingSpeech = [missing.missing_segments?.length ? "音訊段 " + missing.missing_segments.join("、") : "",
      missing.missing_units?.length ? "內容段 " + missing.missing_units.join("、") : ""].filter(Boolean).join("，"); queueMicrotask(project); });
  const unsupported = new Set(["手動更新 Mail", "重試啟動對話", "停止對話服務", "重新啟動 Kuro", "播放待機動作", "顯示桌寵"]);
  function project(): void {
    // Diagnostics remains in Settings; remove the redundant banner and its action.
    // Only existing nodes are removed, so the observer's follow-up is a no-op.
    for (const node of document.querySelectorAll('[data-runtime-status]')) node.remove();
    projectAssistantSettings();
    projectChatSpeechSettings();
    projectToolSettings();
    projectSources(data);
    projectAttachments();
    projectHistory();
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
    const speechLabels: Record<string, string> = {
      partial: "語音僅部分播完，完整回答已保留。", unconfirmed: "尚未確認必要段落已播完。", preparing: "正在整理語音…", unavailable: "語音暫時無法使用，完整回答已保留。",
      failed: "語音播放失敗，完整回答已保留。", timeout: "尚未確認語音播放完成。",
      interrupted: "語音已中斷。", skipped_after_failure: "後續語音因合成失敗而停止。",
      fallback: "這次只有簡短語音提示，完整回答請見文字。"
    };
    const message = speechLabels[speechStatus] || "";
    const label = message && missingSpeech ? message + " 未確認範圍：" + missingSpeech : message;
    let speechNote = list?.querySelector<HTMLElement>("[data-owner-speech]");
    if (speechNote && !label) speechNote.remove();
    if (list && label) {
      if (!speechNote) { speechNote = document.createElement("p"); speechNote.dataset.ownerSpeech = "true"; speechNote.setAttribute("role", "status"); list.appendChild(speechNote); }
      if (speechNote.textContent !== label) speechNote.textContent = label;
    }
    const previous = list?.querySelector<HTMLElement>("[data-owner-tools]");
    const toolKey = JSON.stringify(timeline);
    if (previous && previous.dataset.key !== toolKey) previous.remove();
    if (list && timeline.length && !list.querySelector("[data-owner-tools]")) {
      const box = document.createElement("div"); box.className = "message"; box.dataset.ownerTools = "true"; box.dataset.key = toolKey;
      box.setAttribute("role", "log"); box.setAttribute("aria-label", "工具執行事件");
      for (const row of timeline) {
        const entry = document.createElement("p");
        entry.textContent = `工具事件 · ${String(row.tool_name || "")} · ${String(row.status || "")} · ${String(row.reason_code || row.execution_status || "")}`;
        box.appendChild(entry);
      }
      list.appendChild(box);
    }
    if (data) {
      const canonical = data.canonical;
      const spans = document.querySelectorAll<HTMLElement>(".today-summary > span");
      const values = canonical
        ? [`${canonical.counts?.total ?? "未提供"} 個工作項目`, canonical.complete ? "已採集來源完整" : "來源資料受限", `資料投影時間 ${canonical.generatedAt ?? "時間未提供"}`]
        : ["Core 項目未提供", "無法確認來源", "尚未收到正式 Today"];
      if (!data.ok || data.transportStale) values[1] = "Core 讀取失敗；既有資料尚未重新確認";
      spans.forEach((span, index) => { if (span.textContent !== values[index]) span.textContent = values[index]; });
      const source = document.querySelector<HTMLElement>(".source-status-copy");
      if (source && canonical) {
        const global = `工作清單只呈現來源提供的工作，不代表全部來源正常。資料限制：${(canonical.limitations || []).map(reasonLabel).join("、") || "未提供額外限制"}；各來源狀態請見上方。`;
        if (source.textContent !== global) source.textContent = global;
      }
    }
    for (const note of document.querySelectorAll<HTMLElement>(".settings-note")) {
      if (note.textContent?.includes("Electron 會先顯示原生確認視窗"))
        note.textContent = note.textContent.replace("Electron 會先顯示原生確認視窗", "Qt 會先顯示原生確認視窗");
    }
  }
  new MutationObserver(() => { project(); }).observe(document.getElementById("app")!, {childList: true, subtree: true});
}

export function installHistoryListGuards(transport: Pick<OwnerTransport, "on">): () => void {
  let state = "loading";
  let reading = false;
  let ready = false;
  let opening = false;
  const project = () => {
    const header = document.querySelector<HTMLElement>(".chat-header");
    let progress = header?.querySelector<HTMLElement>("[data-owner-history-progress]");
    if (header && reading && !progress) {
      progress = document.createElement("div"); progress.className = "chat-subtitle";
      progress.dataset.ownerHistoryProgress = "true"; progress.setAttribute("role", "status");
      progress.textContent = "正在讀取對話紀錄…"; header.appendChild(progress);
    }
    if (!reading) progress?.remove();
    const drawer = document.querySelector<HTMLElement>("[data-history-drawer]");
    const list = drawer?.querySelector<HTMLElement>(".history-list");
    if (!drawer || !list) return;
    drawer.setAttribute("aria-busy", String(state === "loading"));
    list.hidden = state !== "ready";
    let status = drawer.querySelector<HTMLElement>("[data-owner-history-status]");
    if (state === "ready") { status?.remove(); return; }
    if (!status) {
      status = document.createElement("div"); status.className = "history-empty";
      status.dataset.ownerHistoryStatus = "true"; status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite"); drawer.appendChild(status);
    }
    const copy = state === "loading" ? "正在等待對話服務並讀取紀錄…" : "對話紀錄讀取失敗；請重新開啟側欄再試。";
    if (status.textContent !== copy) status.textContent = copy;
  };
  transport.on("onHistoryReadState", value => {
    state = value.state; reading = state === "loading";
    if (!reading) opening = false;
    queueMicrotask(project);
  });
  transport.on("onIdentityChange", () => { ready = false; state = "loading"; queueMicrotask(project); });
  transport.on("onChatState", value => {
    const next = value.wsConnected === true && value.historyReady === true;
    if (!next) { state = "loading"; queueMicrotask(project); }
    if (next && !ready && !reading) {
      // Reuse the immutable renderer's existing close/open read handler.
      // No list data or selection is held by this presentation adapter.
      queueMicrotask(() => {
        if (!document.querySelector("[data-stage]")?.classList.contains("has-history")) return;
        document.querySelector<HTMLButtonElement>("[data-history-drawer] .history-drawer-header .icon-button")?.click();
        document.querySelector<HTMLButtonElement>("[data-history-toggle]")?.click();
      });
    }
    ready = next;
  });
  document.addEventListener("click", event => {
    if (!(event.target instanceof Element) || !event.target.closest("[data-history-toggle]")) return;
    if (document.querySelector("[data-stage]")?.classList.contains("has-history")) return;
    if (opening) { event.preventDefault(); event.stopImmediatePropagation(); }
    else opening = true;
  }, true);
  return project;
}

export function validChatSpeechSettings(value: any): boolean {
  const s = value?.settings;
  return value?.ok === true && value.contract === "kuro.chat-speech-settings.v1"
    && /^[a-f0-9]{64}$/.test(value.revision) && typeof value.persisted === "boolean"
    && value.consumer === "conversation-runtime" && value.effective === "next_turn"
    && ["ja-JP", "zh-Hant", "en-US"].includes(s?.locale)
    && ["brief", "summary", "detailed"].includes(s?.policy)
    && ["dual_lane", "legacy_bridge"].includes(s?.route)
    && (s.route !== "legacy_bridge" || s.locale === "ja-JP")
    && value.locales?.["ja-JP"] === "default" && value.locales?.["zh-Hant"] === "unverified"
    && value.locales?.["en-US"] === "unverified";
}

export async function saveChatSpeechSettings(transport: Pick<OwnerTransport, "call">, snapshot: any, settings: any): Promise<any> {
  if (!validChatSpeechSettings(snapshot)) return {ok:false, error:"chat_speech_not_loaded"};
  const written = await transport.call("updateChatSpeechSettings", {settings, expectedRevision:snapshot.revision});
  if (!written?.ok) return written;
  if (!validChatSpeechSettings(written) || !written.persisted) return {ok:false, unknownResult:true};
  const read = await transport.call("getChatSpeechSettings");
  if (!validChatSpeechSettings(read) || read.revision !== written.revision
      || ["locale", "policy", "route"].some(key => read.settings[key] !== settings[key]))
    return {ok:false, unknownResult:true};
  return read;
}

export function installChatSpeechSettings(transport: Pick<OwnerTransport, "call" | "on">): () => void {
  let panel: HTMLElement | null = null, snapshot: any = null, busy = false, generation = 0;
  let message = "尚未讀取一般聊天朗讀設定。";
  function render(sync = false): void {
    if (!panel) return;
    const status = panel.querySelector<HTMLElement>("[data-chat-speech-status]")!;
    if (status.textContent !== message) status.textContent = message;
    panel.querySelectorAll<HTMLSelectElement>("select").forEach(input => { input.disabled = busy || !snapshot || snapshot.preview === true; });
    panel.querySelector<HTMLButtonElement>("[data-chat-speech-save]")!.disabled = busy || !snapshot;
    panel.querySelector<HTMLButtonElement>("[data-chat-speech-reload]")!.disabled = busy;
    if (sync && snapshot) {
      panel.querySelector<HTMLSelectElement>("[name=chatSpeechLocale]")!.value = snapshot.settings.locale;
      panel.querySelector<HTMLSelectElement>("[name=chatSpeechPolicy]")!.value = snapshot.settings.policy;
    }
  }
  async function load(): Promise<void> {
    if (busy) return;
    busy = true; const expected = generation; message = "正在讀取 Launcher 朗讀設定…"; render();
    try {
      const result = await transport.call("getChatSpeechSettings");
      if (expected !== generation) return;
      snapshot = validChatSpeechSettings(result) ? result : null;
      message = snapshot ? "已讀回設定；更改後從下一回合套用。" : "設定讀取失敗，請重新讀取。";
    } catch { snapshot = null; message = "設定讀取失敗，請重新讀取。"; }
    finally { busy = false; render(true); }
  }
  transport.on("onIdentityChange", () => {
    generation++; snapshot = null; message = "工作階段已變更，請重新讀取。"; render();
  });
  return () => {
    if (document.querySelector(".settings-nav-item.is-active strong")?.textContent !== "語音與感知") return;
    const content = document.querySelector<HTMLElement>(".settings-content");
    if (!content || content.querySelector("[data-owner-chat-speech]")) return;
    if (panel) { content.appendChild(panel); return; }
    panel = document.createElement("section"); panel.className = "settings-group"; panel.dataset.ownerChatSpeech = "true";
    const heading = document.createElement("h2"); heading.textContent = "一般聊天朗讀"; panel.appendChild(heading);
    const select = (title: string, name: string, options: Array<[string, string]>) => {
      const row = document.createElement("label"); row.className = "setting-row";
      const label = document.createElement("span"); label.className = "setting-copy"; label.textContent = title;
      const input = document.createElement("select"); input.name = name; input.setAttribute("aria-label", title);
      for (const [value, caption] of options) { const option = document.createElement("option"); option.value = value; option.textContent = caption; input.appendChild(option); }
      row.append(label, input); panel!.appendChild(row);
    };
    select("朗讀策略", "chatSpeechPolicy", [["brief", "極簡"], ["summary", "摘要"], ["detailed", "詳細"]]);
    select("朗讀語言", "chatSpeechLocale", [["ja-JP", "日文（目前預設）"], ["zh-Hant", "繁體中文（語音未驗證）"], ["en-US", "English（語音未驗證）"]]);
    const note = document.createElement("p"); note.className = "settings-note";
    note.textContent = "文字與語音輸入會自動理解語言。朗讀設定與主動通知分開；目前中央角色模型以日文為預設。其他語言可儲存並用於口播稿，語音未驗證前暫不送合成，完整文字仍會顯示。";
    panel.appendChild(note);
    const status = document.createElement("p"); status.className = "settings-note"; status.dataset.chatSpeechStatus = "true";
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); panel.appendChild(status);
    const actions = document.createElement("div"); actions.className = "settings-actions";
    const reload = document.createElement("button"); reload.type = "button"; reload.className = "quiet-button";
    reload.textContent = "重新讀取"; reload.dataset.chatSpeechReload = "true"; reload.addEventListener("click", () => { void load(); });
    const save = document.createElement("button"); save.type = "button"; save.className = "quiet-button";
    save.textContent = "儲存朗讀設定"; save.dataset.chatSpeechSave = "true";
    save.addEventListener("click", async () => {
      if (!panel || busy || !snapshot) return;
      const desired = {...snapshot.settings,
        locale:panel.querySelector<HTMLSelectElement>("[name=chatSpeechLocale]")!.value,
        policy:panel.querySelector<HTMLSelectElement>("[name=chatSpeechPolicy]")!.value};
      if (desired.route === "legacy_bridge" && desired.locale !== "ja-JP") {
        message = "目前為舊語音回退模式，只支援日文。"; render(); return;
      }
      busy = true; const expected = generation; message = "正在儲存並讀回…"; render();
      try {
        const result = await saveChatSpeechSettings(transport, snapshot, desired);
        if (expected !== generation) return;
        snapshot = validChatSpeechSettings(result) ? result : null;
        message = snapshot ? "朗讀設定已儲存並讀回，從下一回合套用。" : "無法確認儲存結果；請重新讀取，不會自動重送。";
      } catch { snapshot = null; message = "無法確認儲存結果，請重新讀取。"; }
      finally { busy = false; render(true); }
    });
    actions.append(reload, save); panel.appendChild(actions); content.appendChild(panel); render(); void load();
  };
}

export function validAssistantSettings(value: any): boolean {
  const settings = value?.settings, omi = settings?.omi;
  return value?.ok === true && value.contract === "kuro.core.assistant-settings.v1"
    && typeof value.revision === "string" && /^[a-f0-9]{64}$/.test(value.revision)
    && typeof value.persisted === "boolean" && typeof settings?.proactiveVoice === "boolean"
    && typeof omi?.enabled === "boolean" && Number.isSafeInteger(omi.intervalMinutes)
    && omi.intervalMinutes >= 5 && omi.intervalMinutes <= 1440
    && Number.isSafeInteger(omi.dailyQueryBudget) && omi.dailyQueryBudget >= 0 && omi.dailyQueryBudget <= 24
    && value.runtime?.consumer === "kuro-core" && value.runtime.executionAvailable === false
    && value.runtime.omi?.allowed === false && value.runtime.proactiveVoice?.allowed === false;
}

export async function saveAssistantSettings(transport: Pick<OwnerTransport, "call">, snapshot: any, settings: any): Promise<any> {
  if (!validAssistantSettings(snapshot)) return {ok:false, error:"settings_not_loaded"};
  const written = await transport.call("updateAssistantSettings", {settings, expectedRevision:snapshot.revision});
  if (!written?.ok) return written;
  if (!validAssistantSettings(written) || !written.persisted) return {ok:false, error:"settings_write_unverified", unknownResult:true};
  const readback = await transport.call("getAssistantSettings");
  if (!validAssistantSettings(readback) || readback.revision !== written.revision
      || readback.settings.proactiveVoice !== settings.proactiveVoice
      || ["enabled", "intervalMinutes", "dailyQueryBudget"].some(key => readback.settings.omi[key] !== settings.omi[key]))
    return {ok:false, error:"settings_readback_unverified", unknownResult:true};
  return readback;
}

export function installAssistantSettings(transport: Pick<OwnerTransport, "call" | "on">): () => void {
  let snapshot: any = null;
  let busy = false;
  let message = "尚未讀取 Core 設定。";
  let generation = 0;
  const panels = new Map<string, HTMLElement>();
  const text = (element: HTMLElement, value: string) => { if (element.textContent !== value) element.textContent = value; };
  const load = async () => {
    if (busy) return;
    busy = true; message = "正在讀取 Core 設定…"; const expected = generation; render();
    try {
      const value = await transport.call("getAssistantSettings");
      if (expected !== generation) return;
      snapshot = validAssistantSettings(value) ? value : null;
      message = snapshot ? (snapshot.persisted ? "已讀回儲存的偏好。" : "目前使用安全預設，尚未儲存偏好。")
        : "Core 設定無法確認；控制已停用。";
    } catch { if (expected === generation) { snapshot = null; message = "Core 設定讀取失敗。"; } }
    finally { busy = false; render(true); }
  };
  transport.on("onIdentityChange", () => { generation++; snapshot = null; message = "工作階段已變更，請重新讀取設定。"; render(); });

  function render(syncValues = false): void {
    for (const panel of panels.values()) {
      const status = panel.querySelector<HTMLElement>("[data-settings-status]")!;
      text(status, message);
      panel.querySelectorAll<HTMLInputElement>("input").forEach(input => { input.disabled = busy || !snapshot || snapshot.preview === true; });
      const save = panel.querySelector<HTMLButtonElement>("[data-settings-save]")!;
      save.disabled = busy || !snapshot;
      panel.querySelector<HTMLButtonElement>("[data-settings-reload]")!.disabled = busy;
      if (syncValues) applyValues(panel);
    }
  }

  function applyValues(panel: HTMLElement): void {
    if (!snapshot) return;
    const voice = panel.querySelector<HTMLInputElement>("[name='proactiveVoice']");
    const omi = panel.querySelector<HTMLInputElement>("[name='omiEnabled']");
    if (voice) voice.checked = snapshot.settings.proactiveVoice;
    if (omi) {
      omi.checked = snapshot.settings.omi.enabled;
      panel.querySelector<HTMLInputElement>("[name='intervalMinutes']")!.value = String(snapshot.settings.omi.intervalMinutes);
      panel.querySelector<HTMLInputElement>("[name='dailyQueryBudget']")!.value = String(snapshot.settings.omi.dailyQueryBudget);
    }
  }

  return () => {
    const section = document.querySelector(".settings-nav-item.is-active strong")?.textContent;
    const content = document.querySelector<HTMLElement>(".settings-content");
    if (!content || !["語音與感知", "工具與權限"].includes(section || "")) return;
    if (content.querySelector("[data-owner-assistant-settings]")) return;
    // Original runtime polling rebuilds Settings. Reattach the same form so
    // in-progress input and handlers survive without a second preferences store.
    const existing = panels.get(section!);
    if (existing) { content.appendChild(existing); return; }
    const panel = document.createElement("section"); panel.className = "settings-group"; panel.dataset.ownerAssistantSettings = "true";
    const heading = document.createElement("h2"); heading.textContent = section === "工具與權限" ? "OMI 觀測" : "主動語音通知";
    panel.appendChild(heading);
    const addInput = (title: string, name: string, type: string, min?: number, max?: number) => {
      const row = document.createElement("label"); row.className = "setting-row";
      const label = document.createElement("span"); label.className = "setting-copy"; label.textContent = title;
      const input = document.createElement("input"); input.name = name; input.type = type; input.setAttribute("aria-label", title);
      if (min !== undefined) { input.min = String(min); input.max = String(max); input.step = "1"; }
      row.append(label, input); panel.appendChild(row); return input;
    };
    const isOmi = section === "工具與權限";
    if (isOmi) {
      addInput("允許 OMI 自動觀測", "omiEnabled", "checkbox");
      addInput("觀測間隔（分鐘，5–1440）", "intervalMinutes", "number", 5, 1440);
      addInput("每日安全查詢上限（0–24；0 表示不查詢）", "dailyQueryBudget", "number", 0, 24);
    } else addInput("主動語音通知", "proactiveVoice", "checkbox");
    const note = document.createElement("p"); note.className = "settings-note";
    note.textContent = isOmi
      ? "背景觀測尚未可用：設定可保存，但不會啟動排程、不刷新提供者、不呼叫付費 LLM。實際用量及上次觀測時間尚未提供。"
      : "主動語音配送尚未可用。與一般聊天 TTS 分開；此開關目前只儲存偏好，不會立即播報。";
    panel.appendChild(note);
    if (isOmi) {
      const debt = document.createElement("p"); debt.className = "settings-note";
      debt.textContent = "Mail 摘要沿用 Core Today；全文讀取與手動刷新尚無受控的 Core 操作介面，維持停用。";
      panel.appendChild(debt);
    }
    const status = document.createElement("p"); status.className = "settings-note"; status.dataset.settingsStatus = "true";
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); panel.appendChild(status);
    const actions = document.createElement("div"); actions.className = "settings-actions";
    const reload = document.createElement("button"); reload.type = "button"; reload.className = "quiet-button"; reload.textContent = "重新讀取"; reload.dataset.settingsReload = "true";
    reload.addEventListener("click", () => { void load(); });
    const save = document.createElement("button"); save.type = "button"; save.className = "quiet-button"; save.textContent = "儲存偏好"; save.dataset.settingsSave = "true";
    save.addEventListener("click", async () => {
      if (busy || !snapshot) return;
      const desired = {proactiveVoice:snapshot.settings.proactiveVoice, omi:{...snapshot.settings.omi}};
      if (isOmi) {
        desired.omi.enabled = panel.querySelector<HTMLInputElement>("[name='omiEnabled']")!.checked;
        desired.omi.intervalMinutes = panel.querySelector<HTMLInputElement>("[name='intervalMinutes']")!.valueAsNumber;
        desired.omi.dailyQueryBudget = panel.querySelector<HTMLInputElement>("[name='dailyQueryBudget']")!.valueAsNumber;
        if (![...panel.querySelectorAll<HTMLInputElement>("input[type='number']")].every(input => input.checkValidity())
            || !Number.isInteger(desired.omi.intervalMinutes) || !Number.isInteger(desired.omi.dailyQueryBudget)) {
          message = "請輸入範圍內的整數；尚未送出。"; text(status, message); return;
        }
      } else desired.proactiveVoice = panel.querySelector<HTMLInputElement>("[name='proactiveVoice']")!.checked;
      const before = snapshot, expected = generation;
      busy = true; message = "等待確認與 Core 儲存…"; render();
      try {
        const result = await saveAssistantSettings(transport, before, desired);
        if (expected !== generation) return;
        if (validAssistantSettings(result)) { snapshot = result; message = "偏好已儲存並由 Core 讀回；自動觀測與主動播報仍未啟用。"; }
        else { snapshot = null; message = result?.cancelled ? "已取消，未儲存。請重新讀取。" : "無法確認儲存結果；請重新讀取，不會自動重送。"; }
      } catch { snapshot = null; message = "無法確認儲存結果；請重新讀取。"; }
      finally { busy = false; render(true); }
    });
    actions.append(reload, save); panel.appendChild(actions); content.appendChild(panel);
    panels.set(section!, panel); applyValues(panel);
    render(); if (!snapshot && !busy) void load();
  };
}

export function validToolSettings(value: any): boolean {
  return value?.ok === true && value.contract === 'kuro.tool-policy-settings.v1'
    && typeof value.digest === 'string' && /^[a-f0-9]{64}$/.test(value.digest)
    && ['MATCHED','UNVERIFIED'].includes(value.runtime_adoption) && value.confirmation_available === false
    && Array.isArray(value.catalog?.toolNames) && value.catalog.groups !== null
    && typeof value.catalog.groups === 'object' && !Array.isArray(value.catalog.groups)
    && Array.isArray(value.tools) && (value.tools.length > 0 || !!value.services)
    && value.catalog.toolNames.length === value.tools.length
    && new Set(value.catalog.toolNames).size === value.tools.length
    && new Set(value.tools.map((r: any) => r.name)).size === value.tools.length
    && value.tools.every((r: any) => ['name','label','description','service','serviceLabel','mode'].every(k => typeof r[k] === 'string')
      && value.catalog.toolNames.includes(r.name) && r.name.startsWith(r.service + '::')
      && value.catalog.groups[r.service] === r.serviceLabel
      && typeof r.enabled === 'boolean' && typeof r.allowed === 'boolean');
}

export async function saveToolSetting(transport: Pick<OwnerTransport,'call'>, snapshot: any, name: string, enabled: boolean): Promise<any> {
  if (!validToolSettings(snapshot) || !snapshot.tools.some((r: any) => r.name === name) || typeof enabled !== 'boolean')
    return {ok:false,error:'tool_policy_not_loaded'};
  const written = await transport.call('updateToolPolicy', {name, enabled, expectedDigest:snapshot.digest});
  if (!written?.ok) return written;
  if (!validToolSettings(written) || written.persisted !== true) return {ok:false,unknownResult:true};
  const read = await transport.call('getTools');
  if (!validToolSettings(read) || read.digest !== written.digest
      || JSON.stringify(read.catalog) !== JSON.stringify(snapshot.catalog)
      || read.tools.find((r: any) => r.name === name)?.enabled !== enabled
      || snapshot.tools.some((old: any) => {
        const row = read.tools.find((r: any) => r.name === old.name);
        return row?.mode !== old.mode || (old.name !== name && row?.enabled !== old.enabled);
      })) return {ok:false,unknownResult:true};
  return read;
}

const element = <K extends keyof HTMLElementTagNameMap>(tag: K, text = '', cls = ''): HTMLElementTagNameMap[K] => {
  const node = document.createElement(tag); node.textContent = text; node.className = cls; return node;
};
const setCopy = (node: HTMLElement, text: string) => { if (node.textContent !== text) node.textContent = text; };

export function installToolSettings(transport: Pick<OwnerTransport,'call'|'on'>): () => void {
  let panel: HTMLElement | null = null, snapshot: any = null, busy = false, generation = 0;
  let message = '尚未讀取工具設定。';
  const folds = new Map<string,boolean>();
  const diagnostics = new Map<string,boolean>();
  const sync = () => {
    if (!panel) return;
    setCopy(panel.querySelector<HTMLElement>('[data-tool-status]')!, message);
    panel.querySelectorAll<HTMLInputElement>('[data-tool-toggle]').forEach(input => {
      input.disabled = busy || !snapshot || snapshot.preview === true;
      const row = snapshot?.tools.find((r: any) => r.name === input.dataset.toolToggle);
      if (row) input.checked = row.enabled;
    });
    panel.querySelector<HTMLButtonElement>('[data-tool-reload]')!.disabled = busy;
  };
  const fill = () => {
    if (!panel || !snapshot) return;
    panel.querySelectorAll<HTMLDetailsElement>('[data-tool-service]').forEach(d => folds.set(d.dataset.toolService!,d.open));
    panel.querySelectorAll<HTMLDetailsElement>('[data-tool-diagnostic]').forEach(d => diagnostics.set(d.dataset.toolDiagnostic!,d.open));
    const focused = (document.activeElement as HTMLElement | null)?.dataset.toolToggle;
    const list = panel.querySelector<HTMLElement>('[data-tool-groups]')!; list.replaceChildren();
    if (snapshot.events?.length) {
      const history = element('details'); history.append(element('summary', '本輪工具呼叫紀錄'));
      for (const event of snapshot.events) {
        history.append(element('h3', event.tool_name),
          element('p', [event.tool_id, event.outcome || event.status, event.reason_code || event.execution_status].filter(Boolean).join(' · ')),
          element('p', event.call_summary || '', 'owner-tool-purpose'),
          element('pre', event.content || ''));
      }
      list.append(history);
    }
    for (const service of new Set<string>([...Object.keys(snapshot.services || {}),
        ...snapshot.tools.map((r: any) => r.service)])) {
      const rows = snapshot.tools.filter((r: any) => r.service === service);
      const group = element('details','','owner-tool-group'); group.dataset.toolService = service; group.open = folds.get(service) ?? false;
      const summary = element('summary'); const heading = element('span', snapshot.catalog.groups[service] || service, 'owner-tool-heading');
      summary.append(heading, element('span', snapshot.services?.[service]?.connected ? `發現 ${snapshot.services[service].count} · 可呼叫 ${rows.filter((r: any) => r.allowed).length}` : (snapshot.services?.[service]?.reason || '尚無連線紀錄'), 'owner-tool-count'));
      group.append(summary); group.addEventListener('toggle', () => folds.set(service,group.open));
      const scope = snapshot.services?.[service]?.scope;
      if (scope) group.append(element('p',
        [scope.mode, scope.write_enabled === true ? '來源已授權寫入' : scope.write_enabled === false ? '來源未授權寫入' : '寫入權限未知',
          scope.reason, scope.contract].filter(Boolean).join(' · '), 'owner-tool-policy'));
      for (const row of rows) {
        const item = element('div','','owner-tool-row');
        const copy = element('div','','owner-tool-copy'); copy.append(element('h3',row.label),element('p',row.description,'owner-tool-purpose'));
        const policy = !row.enabled ? '已停用' : row.mode === 'confirm'
          ? '需確認 · 執行流程未就緒' : row.mode === 'read_only'
          ? '受限唯讀' : row.mode === 'owner' ? '依來源授權' : '政策封鎖';
        copy.append(element('p', [policy, ({read:'讀取',write:'寫入',destructive:'破壞性操作',owner_defined:'來源未標示操作類型'} as Record<string,string>)[row.operation], row.allowed ? '可呼叫' : row.reason_code].filter(Boolean).join(' · '),'owner-tool-policy'));
        const diagnostic = element('details','','owner-diagnostic'); diagnostic.dataset.toolDiagnostic = row.name;
        diagnostic.open = diagnostics.get(row.name) ?? false;
        diagnostic.append(element('summary','診斷資料'),
          element('code',`${row.name} · mode=${row.mode} · ${row.reason_code}`)); copy.append(diagnostic);
        const label = element('label', '啟用', 'owner-tool-toggle');
        const input = element('input'); input.type = 'checkbox'; input.dataset.toolToggle = row.name;
        input.setAttribute('aria-label',`啟用${row.label}`); input.checked = row.enabled;
        input.addEventListener('change', async () => {
          if (busy || !snapshot) return;
          const enabled = input.checked, before = snapshot, expected = generation;
          busy = true; message = '等待 Qt 原生確認與設定保存…'; sync();
          try {
            const result = await saveToolSetting(transport,before,row.name,enabled);
            if (expected !== generation) return;
            if (validToolSettings(result)) {
              snapshot = result; fill(); message = '儲存成功並已讀回；執行環境尚未驗證採用。請自行重啟後驗證，這裡不會重啟服務。';
            } else {
              snapshot = null;
              message = result?.cancelled ? '已取消，未儲存；請重新讀取。' : '無法確認儲存結果；請重新讀取。不會自動重送。';
            }
          } catch { snapshot = null; message = '儲存失敗或結果不明；請重新讀取，不會自動重送。'; }
          finally { busy = false; sync(); }
        });
        label.prepend(input); item.append(copy,label); group.append(item);
      }
      list.append(group);
    }
    if (focused) [...list.querySelectorAll<HTMLInputElement>('[data-tool-toggle]')].find(n => n.dataset.toolToggle === focused)?.focus();
  };
  const load = async () => {
    if (busy) return;
    busy = true; const expected = generation; message = '正在讀取工具政策…'; sync();
    try {
      const value = await transport.call('getTools');
      if (expected !== generation) return;
      snapshot = validToolSettings(value) ? value : null;
      if (snapshot) { fill(); message = snapshot.preview ? '隔離預覽 · 正式服務清單與隔離呼叫紀錄' : snapshot.runtime_adoption === 'MATCHED' ? '執行中的工具清單與政策版本一致。' : (snapshot.inventory_error || '執行中的政策版本尚待確認。'); }
      else message = '工具政策不可用或不符合契約；控制已停用。';
    } catch { snapshot = null; message = '讀取失敗；控制已停用。'; }
    finally { busy = false; sync(); }
  };
  transport.on('onIdentityChange', () => { generation++; snapshot = null; message = '工作階段變更；請重新讀取。'; sync(); });
  return () => {
    if (document.querySelector('.settings-nav-item.is-active strong')?.textContent !== '工具與權限') return;
    const content = document.querySelector<HTMLElement>('.settings-content'); if (!content) return;
    const original = [...content.querySelectorAll<HTMLElement>('.settings-group')].find(g => !g.dataset.ownerToolSettings
      && g.querySelector('h2')?.textContent === '工具與權限');
    if (!panel) {
      panel = element('section','','settings-group owner-tool-settings'); panel.dataset.ownerToolSettings = 'true';
      panel.append(element('h2','工具與權限'),element('p','展開服務查看來源宣告的操作類型、可呼叫狀態與原因。','settings-note'));
      const status = element('p','','settings-note'); status.dataset.toolStatus = 'true'; status.setAttribute('role','status'); status.setAttribute('aria-live','polite');
      const reload = element('button','重新讀取','quiet-button'); reload.type = 'button'; reload.dataset.toolReload = 'true'; reload.addEventListener('click',() => { void load(); });
      const groups = element('div'); groups.dataset.toolGroups = 'true'; panel.append(status,reload,groups);
      content.prepend(panel); void load();
    }
    if (original) original.replaceWith(panel);
    else if (!panel.isConnected) content.prepend(panel);
  };
}

const sourceNames: Record<string,string> = {japanese_study:'日文學習',english_study:'英文學習',mail:'Gmail 郵件',omi:'OMI 市場觀測',study:'舊版學習來源'};
const stateNames: Record<string,string> = {available:'可取得資料',partial:'部分資料',missing:'尚無資料',unavailable:'尚不可用',offline:'離線',
  connected:'已連線',disconnected:'未連線',auth_required:'需要授權',unknown:'未知',current:'目前有效',stale:'資料過期',expired:'已失效',disabled:'已停用'};
export function reasonLabel(raw: string): string {
  const reasons: Record<string,string> = {disabled:'來源已停用',snapshot_pending:'等待首次取得資料',snapshot_missing:'尚未取得快照',
    source_missing:'缺少來源資料',source_limitations:'部分來源資料受限',source_stale:'含過期來源',
    auth_required:'需要來源授權',provider_error:'來源讀取失敗',timeout:'來源讀取逾時',transport_error:'來源連線失敗',
    output_budget_exceeded:'只呈現輸出預算內的項目',canonical_cache_consumer_unavailable:'安全的唯讀快取介面尚未提供',
    no_refresh_not_verified:'尚未證明不會刷新外部資料',quota_ledger_unavailable:'安全查詢額度機制尚未提供',
    query_budget_zero:'每日查詢預算為零',settings_unavailable:'無法確認設定',source_time_missing:'來源未提供資料時間',
    source_observed_at_missing:'來源未提供觀察時間',item_observed_at_missing:'部分項目未提供來源時間',
    bounded_page_may_be_partial:'清單已達本次讀取上限，可能還有其他項目',
    permission_denied:'來源讀取權限被拒絕',invalid_contract:'來源資料格式不符合契約',
    due_page_bounded:'複習清單為有界頁面',plan_page_bounded:'學習計畫為有界頁面',summary_bounded:'摘要僅含受限欄位',
    work_snapshot_missing:'尚未取得工作清單',work_timestamp_invalid:'來源時間無法確認'};
  return reasons[raw] || '另有來源限制（可展開診斷資料）';
}
export function sourceCopy(row: any): string {
  if (row.sourceId === 'omi' && row.executionAvailable === false) return '背景自動觀測尚未可用；設定可保存，但不會排程查詢。';
  if (row.enabled === false) return '來源已停用，不參與今日完整性評估。';
  if (row.availability === 'auth_required' || row.connection === 'auth_required') return '需要授權；未確認目前資料，不能視為沒有待辦。';
  if (row.connection === 'disconnected') return '來源未連線；既有內容可能是先前取得的資料。';
  if (row.availability === 'missing') return '尚無可用快照，等待來源提供資料；不代表零筆工作。';
  if (row.evidenceCount === 0 && ['available','partial'].includes(row.availability)) return row.freshness === 'stale'
    ? '先前清單沒有待辦，但資料已過期；目前狀態待確認。' : row.availability === 'partial'
    ? '本次取得的清單沒有待辦；來源資料仍有限制，請查看時效與說明。' : '本次取得的清單沒有待辦；不等於離線。';
  if (row.availability === 'partial') return '來源資料不完整；清單僅呈現可驗證的工作。';
  return row.evidenceCount == null ? '尚無法確認工作數量。' : `來源提供 ${row.evidenceCount} 筆工作證據；去重及顯示預算後的項目數可能不同。`;
}
export function sourceStatusLabel(row: any): string {
  if (row.sourceId === 'omi' && row.executionAvailable === false) return '自動觀測未開放';
  if (row.enabled === false) return '已停用';
  const status = row.availability === 'auth_required' || row.connection === 'auth_required' ? '需要授權'
    : row.connection === 'disconnected' ? '未連線'
    : ['available','partial'].includes(row.availability) && row.evidenceCount === 0
      ? row.availability === 'partial' ? '本次無待辦 · 資料有限制' : '本次無待辦'
    : stateNames[row.availability] || '未知';
  const freshness = row.freshness === 'stale' || row.freshness === 'expired' ? stateNames[row.freshness]
    : row.freshness !== 'current' ? '時效未知' : '';
  return [status, freshness].filter(Boolean).join(' · ');
}

export function installSourceOverview(): (data: any) => void {
  // Reuse these nodes, including native details state/focus, across renderer polls.
  const strip = element('section','','owner-source-strip'); strip.dataset.ownerSourceStrip = 'true';
  strip.setAttribute('aria-label','來源狀態');
  const notice = element('p','','owner-source-notice');
  const statuses = element('ul'); strip.append(notice,statuses);
  const panel = element('details','','owner-source-overview'); panel.dataset.ownerSourceOverview = 'true';
  panel.append(element('summary','來源詳情與限制'));
  const empty = element('p','目前尚未提供來源概覽；OMI 背景觀測仍未就緒。'); panel.append(empty);
  const entries = new Map<string, {status: HTMLElement; card: HTMLElement; key: string}>();
  return data => {
    const header = document.querySelector<HTMLElement>('.today-frame > header');
    const primary = document.querySelector<HTMLElement>('.today-primary'); if (!header || !primary) return;
    const rows = Array.isArray(data?.canonical?.sourceOverview) ? data.canonical.sourceOverview : [];
    const unavailable = !data?.ok || data.transportStale;
    setCopy(notice, unavailable ? 'Core 讀取失敗；來源狀態待重新確認。' : rows.length ? '' : '尚無來源狀態');
    notice.hidden = !notice.textContent;
    empty.hidden = rows.length > 0;
    const ids = new Set(rows.map((row: any) => row.sourceId));
    for (const [id, entry] of entries) if (!ids.has(id)) { entry.card.remove(); entry.status.remove(); entries.delete(id); }
    for (const row of rows) {
      let entry = entries.get(row.sourceId);
      if (!entry) {
        const status = element('li'); status.dataset.sourceId = row.sourceId;
        const card = element('article','','owner-source-detail'); card.dataset.sourceId = row.sourceId;
        card.append(element('h3'),element('p','','owner-source-copy'),element('p','','owner-source-axes'),
          element('p','','owner-source-time'),element('p','','owner-source-limits'));
        const raw = element('details','','owner-diagnostic'); raw.append(element('summary','診斷資料'),element('pre'));
        card.append(raw); statuses.append(status); panel.append(card);
        entry = {status,card,key:''}; entries.set(row.sourceId,entry);
      }
      const key = JSON.stringify(row);
      if (entry.key !== key) {
        entry.key = key;
        const name = sourceNames[row.sourceId] || '其他來源';
        setCopy(entry.status, `${name}：${sourceStatusLabel(row)}`);
        setCopy(entry.card.querySelector('h3')!, name);
        setCopy(entry.card.querySelector('.owner-source-copy')!, sourceCopy(row));
        setCopy(entry.card.querySelector('.owner-source-axes')!, `資料：${stateNames[row.availability] || '未知'} · 連線：${stateNames[row.connection] || '未知'} · 時效：${stateNames[row.freshness] || '未知'}`);
        setCopy(entry.card.querySelector('.owner-source-time')!, `來源時間：${row.observedAt || '未提供'}；Core 取得／讀取時間：${row.receivedAt || '未提供'}`);
        setCopy(entry.card.querySelector('.owner-source-limits')!, (row.limitations || []).map(reasonLabel).filter((v: string, i: number, a: string[]) => a.indexOf(v) === i).join('；'));
        setCopy(entry.card.querySelector('pre')!, JSON.stringify(row,null,2));
      }
    }
    if (header.nextElementSibling !== strip) header.after(strip);
    if (primary.nextElementSibling !== panel) primary.after(panel);
  };
}

export function installAttachmentHelp(): () => void {
  const copy = 'PNG／JPEG／WebP、TXT、PDF、WAV；最多 6 個，每個 4 MiB，合計 8 MiB。未支援格式會拒絕傳送。';
  const help = element('details','','owner-attachment-help'); help.dataset.ownerAttachmentHelp = 'true';
  const text = element('p',copy); text.id = 'owner-attachment-limits';
  help.append(element('summary','附件格式與大小'),text);
  return () => {
    const attach = document.querySelector<HTMLButtonElement>('[data-attach]');
    const foot = document.querySelector<HTMLElement>('.composer-foot'); if (!attach || !foot) return;
    attach.title = `加入附件：${copy}`;
    attach.setAttribute('aria-label','加入附件');
    attach.setAttribute('aria-describedby',text.id);
    if (foot.nextElementSibling !== help) foot.after(help);
  };
}
