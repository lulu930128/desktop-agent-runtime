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
  const projectToolSettings = installToolSettings(transport);
  const projectSources = installSourceOverview();
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
  const unsupported = new Set(["手動更新 Mail", "重試啟動對話", "停止對話服務", "重新啟動 Kuro", "播放待機動作", "顯示桌寵"]);
  function project(): void {
    projectAssistantSettings();
    projectToolSettings();
    projectSources(data);
    const composer = document.querySelector<HTMLElement>(".attachment-row");
    if (composer && !composer.parentElement?.querySelector("[data-owner-attachment-caps]")) {
      const note = document.createElement("p"); note.className = "settings-note"; note.dataset.ownerAttachmentCaps = "true";
      note.textContent = "附件：PNG／JPEG／WebP、TXT、PDF、WAV；最多 6 個，每個 4 MiB，合計 8 MiB。未支援格式會拒絕傳送。";
      composer.after(note);
    }
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
      panel.querySelectorAll<HTMLInputElement>("input").forEach(input => { input.disabled = busy || !snapshot; });
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
    && value.runtime_adoption === 'UNVERIFIED' && value.confirmation_available === false
    && Array.isArray(value.tools) && value.tools.length === 21
    && new Set(value.tools.map((r: any) => r.name)).size === 21
    && value.tools.every((r: any) => ['name','label','description','service','serviceLabel','mode'].every(k => typeof r[k] === 'string')
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
  const sync = () => {
    if (!panel) return;
    setCopy(panel.querySelector<HTMLElement>('[data-tool-status]')!, message);
    panel.querySelectorAll<HTMLInputElement>('[data-tool-toggle]').forEach(input => {
      input.disabled = busy || !snapshot;
      const row = snapshot?.tools.find((r: any) => r.name === input.dataset.toolToggle);
      if (row) input.checked = row.enabled;
    });
    panel.querySelector<HTMLButtonElement>('[data-tool-reload]')!.disabled = busy;
  };
  const fill = () => {
    if (!panel || !snapshot) return;
    panel.querySelectorAll<HTMLDetailsElement>('[data-tool-service]').forEach(d => folds.set(d.dataset.toolService!,d.open));
    const list = panel.querySelector<HTMLElement>('[data-tool-groups]')!; list.replaceChildren();
    for (const service of [...new Set<string>(snapshot.tools.map((r: any) => r.service))]) {
      const rows = snapshot.tools.filter((r: any) => r.service === service);
      const group = element('details'); group.dataset.toolService = service; group.open = folds.get(service) ?? true;
      const summary = element('summary'); const heading = element('h3', `${rows[0].serviceLabel}（${rows.length} 項）`);
      heading.style.display = 'inline'; summary.style.padding = '14px 0'; summary.style.cursor = 'pointer'; summary.append(heading);
      group.append(summary); group.addEventListener('toggle', () => folds.set(service,group.open));
      for (const row of rows) {
        const item = element('div','','setting-row'); item.style.alignItems = 'start';
        const copy = element('div','','setting-copy'); copy.append(element('h4',row.label),element('p',row.description));
        const policy = !row.enabled ? '已停用（儲存的設定）' : row.mode === 'confirm'
          ? '需確認，但執行流程尚未完成；目前仍封鎖' : row.mode === 'read_only'
          ? '允許受限唯讀；是否已載入仍待驗證' : '原政策封鎖或未支援，開啟此設定仍不會放行';
        copy.append(element('p',policy,'settings-note'));
        const diagnostic = element('details'); diagnostic.append(element('summary','診斷資料'),
          element('code',`${row.name} · mode=${row.mode} · ${row.reason_code}`)); copy.append(diagnostic);
        const label = element('label', '啟用此工具');
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
  };
  const load = async () => {
    if (busy) return;
    busy = true; const expected = generation; message = '正在讀取工具政策…'; sync();
    try {
      const value = await transport.call('getTools');
      if (expected !== generation) return;
      snapshot = validToolSettings(value) ? value : null;
      if (snapshot) { fill(); message = '已讀取儲存的政策；目前執行環境採用狀態尚未驗證。'; }
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
      panel = element('section','','settings-group'); panel.dataset.ownerToolSettings = 'true';
      panel.append(element('h2','工具與權限'),element('p','每項開關只控制此工具是否啟用，原權限與參數限制不變。這是對話工具政策，不控制獨立的 Study／Mail 背景來源或 OMI 自動觀測。','settings-note'));
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
export function installSourceOverview(): (data: any) => void {
  let panel: HTMLElement | null = null, key = '';
  return data => {
    const header = document.querySelector<HTMLElement>('.today-frame > header'); if (!header) return;
    const rows = data?.canonical?.sourceOverview;
    const next = JSON.stringify([rows,data?.ok,data?.transportStale]);
    if (!panel) { panel = element('section','','settings-group'); panel.dataset.ownerSourceOverview = 'true'; }
    if (key !== next) {
      key = next; panel.replaceChildren(element('h2','來源狀態'));
      if (!data?.ok || data.transportStale) panel.append(element('p','Core 讀取失敗；以下來源資料尚未重新確認。','settings-note'));
      if (!Array.isArray(rows)) panel.append(element('p','目前執行環境尚未提供來源概覽；請在自行重啟採用後驗證。OMI 背景觀測仍未就緒。'));
      else {
        const grid = element('div'); grid.style.display = 'grid'; grid.style.gap = '12px 24px';
        grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))'; panel.append(grid);
        for (const row of rows) {
        const card = element('article','','setting-row'); const copy = element('div','','setting-copy');
        card.style.minWidth = '0'; copy.style.overflowWrap = 'anywhere';
        copy.append(element('h3',sourceNames[row.sourceId] || '其他來源'),element('p',sourceCopy(row)),
          element('p',`資料：${stateNames[row.availability] || '未知'} · 連線：${stateNames[row.connection] || '未知'} · 時效：${stateNames[row.freshness] || '未知'}`),
          element('p',`來源時間：${row.observedAt || '未提供'}；Core 取得／讀取時間：${row.receivedAt || '未提供'}`,'settings-note'));
        if (row.limitations?.length) copy.append(element('p',[...new Set<string>(row.limitations.map(reasonLabel))].join('；'),'settings-note'));
        const detail = element('details'); const raw = element('pre',JSON.stringify(row,null,2)); raw.style.whiteSpace = 'pre-wrap';
        detail.append(element('summary','診斷資料'),raw); copy.append(detail);
        card.append(copy); grid.append(card);
        }
      }
    }
    if (!panel.isConnected) header.after(panel);
  };
}
