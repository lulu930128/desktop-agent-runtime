import "./styles.css";
import {
  SOURCE_ORDER,
  formatDateLabel,
  formatFullDate,
  levelLabel,
  priorityItems,
  scheduleItems,
  sourceCount,
  sourceItems,
  sourceLabel,
  sourceStatus,
  statusLabel,
  statusTone,
  text
} from "./model";
import type {
  AttachmentPayload,
  BriefingData,
  ChatHistoryPayload,
  ChatState,
  HistoryMessage,
  HistorySummary,
  MemoryEntry,
  MemoryState,
  ProfileState,
  RuntimeState,
  SelectOption,
  ToolPolicyState,
  ViewItem,
  WorkMode,
  WorkPanelBridge
} from "./types";

const ICONS = {
  chat: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.5h14v10H9l-4 3v-13Z"/><path d="M8 9h8M8 12h5"/></svg>`,
  today: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14v12H5zM8 4v5M16 4v5M5 10h14"/><path d="M9 14h2M13 14h2"/></svg>`,
  settings: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.6-.6-1.4 1-1.8-2.1-2.1-1.8 1-1.4-.6-.6-2h-3l-.6 2-1.4.6-1.8-1-2.1 2.1 1 1.8L3 9.9v3l2 .6.6 1.4-1 1.8 2.1 2.1 1.8-1 1.4.6.6 2h3l.6-2 1.4-.6 1.8 1 2.1-2.1-1-1.8.6-1.4Z"/></svg>`,
  history: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h12M4 17h9"/><path d="M18 14v6M15 17h6"/></svg>`,
  attach: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 12.5 5.7-5.7a3 3 0 1 1 4.2 4.2l-7.8 7.8a5 5 0 0 1-7.1-7.1l7.4-7.4"/><path d="m7.2 14.5 7-7"/></svg>`,
  mic: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4M8 21h8"/></svg>`,
  pause: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6v12M15 6v12"/></svg>`,
  resume: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 9 6-9 6Z"/></svg>`,
  cancel: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg>`,
  camera: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h4l2-2h4l2 2h4v12H4z"/><circle cx="12" cy="13" r="3"/></svg>`,
  screen: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="1"/><path d="M8 21h8M12 17v4"/></svg>`,
  delete: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>`,
  send: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 4 16 8-16 8 3-8-3-8Z"/><path d="M7 12h13"/></svg>`,
  stop: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10"/></svg>`,
  minimize: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 11.5h10"/></svg>`,
  maximize: `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="3" width="10" height="10"/></svg>`,
  close: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3 3 10 10M13 3 3 13"/></svg>`
};

const EMPTY_DATA: BriefingData = {
  ok: true,
  snapshot: {
    sections: [],
    sourceStatus: [],
    today: { items: [], levels: {}, counts: {} }
  },
  memoryCandidates: []
};

const fallbackBridge: WorkPanelBridge = {
  async getState() { return { ok: false, wsConnected: false }; },
  async getData() { return EMPTY_DATA; },
  async getChatState() { return { ok: false, wsConnected: false }; },
  async getChatHistory() { return { ok: true, messages: [] }; },
  async getProfile() { return { ok: false, error: "desktop-bridge-unavailable" }; },
  async applyProfile() { return { ok: false, error: "desktop-bridge-unavailable" }; },
  async getHistories() { return { ok: false, histories: [], messages: [] }; },
  async createHistory() { return { ok: false, histories: [], messages: [] }; },
  async selectHistory() { return { ok: false, histories: [], messages: [] }; },
  async deleteHistory() { return { ok: false, histories: [], messages: [] }; },
  async getMemories() { return { ok: false, memories: [] }; },
  async memoryAction() { return { ok: false, memories: [] }; },
  async getTools() { return { ok: false, tools: [] }; },
  async sendText() { return { ok: false, error: "desktop-bridge-unavailable" }; },
  async refreshMail() { return { ok: false, error: "desktop-bridge-unavailable" }; },
  async getMailMessage() { return { ok: false, error: "desktop-bridge-unavailable" }; },
  async control() { return { ok: false, error: "desktop-bridge-unavailable" }; },
  closeWindow() { window.close(); },
  minimizeWindow() { /* Browser preview has no native window controls. */ },
  toggleMaximizeWindow() { /* Browser preview has no native window controls. */ },
  onState() { return () => undefined; },
  onData() { return () => undefined; },
  onChatState() { return () => undefined; }
};

const bridge = window.kuroWorkPanel || fallbackBridge;
const appRoot = document.querySelector<HTMLDivElement>("#app");

if (!appRoot) {
  throw new Error("Kuro work panel root is missing.");
}

function createElement<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className = "",
  content = ""
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content) element.textContent = content;
  return element;
}

function button(className: string, label: string, onClick: () => void): HTMLButtonElement {
  const element = createElement("button", className, label);
  element.type = "button";
  element.addEventListener("click", onClick);
  return element;
}

function toBoolean(value: string | null, fallback = false): boolean {
  if (value === null) return fallback;
  return value === "true";
}

function normalizeMode(value: string | null): WorkMode {
  return value === "chat" || value === "settings" ? value : "today";
}

function isBusyState(aiState: unknown): boolean {
  return ["thinking", "speaking", "loading", "processing"].includes(text(aiState).toLowerCase());
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function messageRoleLabel(role: string): string {
  const normalized = text(role).toLowerCase();
  if (["human", "user"].includes(normalized)) return "YOU";
  if (["ai", "assistant"].includes(normalized)) return "KURO";
  return "EVENT";
}

function messageRoleClass(role: string): string {
  const normalized = text(role).toLowerCase();
  if (["human", "user"].includes(normalized)) return "is-user";
  if (["ai", "assistant"].includes(normalized)) return "is-assistant";
  return "is-event";
}

function fileExtension(name: string): string {
  const normalized = text(name).toLowerCase();
  const compound = [".tar.gz", ".tar.bz2", ".tar.xz"].find((extension) => normalized.endsWith(extension));
  if (compound) return compound;
  const index = normalized.lastIndexOf(".");
  return index >= 0 ? normalized.slice(index) : "";
}

function classifyFile(file: File): string {
  const mime = text(file.type).toLowerCase();
  const extension = fileExtension(file.name);
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("audio/")) return "audio";
  if ([".zip", ".tar", ".tgz", ".tar.gz", ".gz", ".7z", ".rar"].includes(extension)) return "archive";
  if ([".exe", ".dll", ".bin", ".dat"].includes(extension)) return "binary";
  if ([".js", ".ts", ".tsx", ".jsx", ".py", ".css", ".html", ".json", ".yaml", ".yml", ".md", ".sql", ".ps1", ".sh"].includes(extension)) return "code";
  if (mime.startsWith("text/") || [".txt", ".csv", ".xml", ".toml"].includes(extension)) return "text";
  return "binary";
}

function attachmentLimit(kind: string): number {
  if (kind === "image") return 8 * 1024 * 1024;
  if (kind === "audio") return 12 * 1024 * 1024;
  if (kind === "archive") return 24 * 1024 * 1024;
  if (kind === "binary") return 16 * 1024 * 1024;
  return 4 * 1024 * 1024;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("file-read-failed"));
    reader.readAsDataURL(file);
  });
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

class KuroWorkPanel {
  private mode: WorkMode = normalizeMode(window.localStorage.getItem("kuro.work-panel.mode"));
  private selectedSource = window.localStorage.getItem("kuro.work-panel.source") || "all";
  private runtime: RuntimeState = { wsConnected: false, aiState: "idle" };
  private chat: ChatState = { wsConnected: false, aiState: "idle" };
  private history: ChatHistoryPayload = { ok: true, messages: [] };
  private profile: ProfileState = { ok: false, characters: [], projects: [], models: [] };
  private memories: MemoryState = { ok: false, memories: [] };
  private tools: ToolPolicyState = { ok: false, tools: [] };
  private data: BriefingData = EMPTY_DATA;
  private selectedItem: ViewItem | null = null;
  private mailDetail: Record<string, unknown> | null = null;
  private contextItem: ViewItem | null = null;
  private attachments: AttachmentPayload[] = [];
  private draft = "";
  private sending = false;
  private historyOpen = false;
  private historyQuery = "";
  private profileApplying = false;
  private pendingProfileSelection: NonNullable<ProfileState["selected"]> | null = null;
  private sensorPending = "";
  private settingsSection = window.localStorage.getItem("kuro.work-panel.settings-section") || "assistant";
  private compact = toBoolean(window.localStorage.getItem("kuro.work-panel.compact"));
  private reduceMotion = toBoolean(window.localStorage.getItem("kuro.work-panel.reduce-motion"));
  private toastTimer = 0;
  private historyRefreshTimer = 0;

  constructor() {
    this.renderShell();
    this.applyPreferences();
    this.bindShell();
    this.renderActiveView();
    this.refreshAll();
    bridge.onState((state) => this.onRuntimeState(state));
    bridge.onData((data) => this.onBriefingData(data));
    bridge.onChatState((state) => this.onChatState(state));
  }

  private renderShell(): void {
    appRoot.innerHTML = `
      <div class="work-panel">
        <aside class="rail" aria-label="Kuro 主導航">
          <div class="brand">
            <div class="brand-orbit" aria-hidden="true">K<span class="state-pulse" data-state-pulse></span></div>
            <div class="brand-copy">
              <div class="brand-name">Kuro</div>
              <div class="brand-role">work companion</div>
            </div>
          </div>
          <nav class="rail-nav">
            <button class="rail-button" type="button" data-mode="chat" aria-label="普通對話">${ICONS.chat}<span class="rail-label">對話</span></button>
            <button class="rail-button" type="button" data-mode="today" aria-label="今天與行事曆">${ICONS.today}<span class="rail-label">今天</span></button>
          </nav>
          <div class="rail-spacer"></div>
          <div class="rail-footer">
            <div class="presence"><span class="presence-dot" data-presence-dot></span><span class="presence-label" data-presence-label>正在確認連線</span></div>
            <button class="rail-button" type="button" data-mode="settings" aria-label="設定">${ICONS.settings}<span class="rail-label">設定</span></button>
          </div>
        </aside>
        <section class="workspace">
          <header class="chrome">
            <div class="chrome-context">
              <span class="chrome-title" data-chrome-title>Kuro 工作面板</span>
              <span class="chrome-meta" data-chrome-meta>LOCAL-FIRST</span>
            </div>
            <div class="chrome-right">
              <div class="privacy-indicators" data-privacy-indicators aria-label="感知功能狀態"></div>
              <div class="window-actions" aria-label="視窗控制">
                <button class="window-button" type="button" data-window="minimize" aria-label="最小化">${ICONS.minimize}</button>
                <button class="window-button" type="button" data-window="maximize" aria-label="最大化或還原">${ICONS.maximize}</button>
                <button class="window-button close" type="button" data-window="close" aria-label="關閉">${ICONS.close}</button>
              </div>
            </div>
          </header>
          <div class="stage" data-stage>
            <button class="history-scrim" type="button" data-history-scrim aria-label="關閉對話紀錄"></button>
            <aside class="history-drawer" data-history-drawer aria-label="對話紀錄"></aside>
            <main class="view-root" data-view-root></main>
            <aside class="detail-drawer" data-detail-drawer aria-label="項目詳情"></aside>
          </div>
          <div class="toast" role="status" aria-live="polite" data-toast></div>
        </section>
      </div>
    `;
  }

  private bindShell(): void {
    appRoot.querySelectorAll<HTMLButtonElement>("[data-mode]").forEach((element) => {
      element.addEventListener("click", () => this.setMode(normalizeMode(element.dataset.mode || "today")));
    });
    appRoot.querySelector<HTMLButtonElement>("[data-window='minimize']")
      ?.addEventListener("click", () => bridge.minimizeWindow());
    appRoot.querySelector<HTMLButtonElement>("[data-window='maximize']")
      ?.addEventListener("click", () => bridge.toggleMaximizeWindow());
    appRoot.querySelector<HTMLButtonElement>("[data-window='close']")
      ?.addEventListener("click", () => bridge.closeWindow());
    appRoot.querySelector<HTMLButtonElement>("[data-history-scrim]")
      ?.addEventListener("click", () => this.setHistoryOpen(false));
  }

  private async refreshAll(): Promise<void> {
    const [runtimeResult, dataResult, chatResult, profileResult, memoryResult, toolResult] = await Promise.allSettled([
      bridge.getState(),
      bridge.getData(),
      bridge.getChatState(),
      bridge.getProfile(),
      bridge.getMemories(),
      bridge.getTools()
    ]);
    if (runtimeResult.status === "fulfilled") this.runtime = { ...this.runtime, ...runtimeResult.value };
    if (dataResult.status === "fulfilled" && dataResult.value) this.data = dataResult.value;
    if (chatResult.status === "fulfilled") this.chat = { ...this.chat, ...chatResult.value };
    if (profileResult.status === "fulfilled") this.profile = profileResult.value;
    if (memoryResult.status === "fulfilled") this.memories = memoryResult.value;
    if (toolResult.status === "fulfilled") this.tools = toolResult.value;
    await this.refreshHistory();
    this.renderChrome();
    this.renderActiveView();
  }

  private async refreshHistory(): Promise<void> {
    try {
      const result = await bridge.getHistories();
      this.history = result?.ok ? result : await bridge.getChatHistory();
    } catch (_error) {
      this.history = { ok: false, error: "history-unavailable", messages: [] };
    }
  }

  private async refreshMemories(): Promise<void> {
    try {
      this.memories = await bridge.getMemories();
    } catch (_error) {
      this.memories = { ok: false, error: "memory-unavailable", memories: [] };
    }
  }

  private async reconcileProfileRuntime(expectedCharacterId: string): Promise<boolean> {
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const [runtimeResult, chatResult, profileResult] = await Promise.allSettled([
        bridge.getState(),
        bridge.getChatState(),
        bridge.getProfile()
      ]);
      if (runtimeResult.status === "fulfilled") {
        this.runtime = { ...this.runtime, ...runtimeResult.value };
      }
      if (chatResult.status === "fulfilled") {
        this.chat = { ...this.chat, ...chatResult.value };
      }
      if (profileResult.status === "fulfilled" && profileResult.value?.ok) {
        this.profile = profileResult.value;
      }

      const runtimeCharacterId = text(this.chat.confUid || this.runtime.confUid);
      if (!expectedCharacterId || runtimeCharacterId === expectedCharacterId) {
        return true;
      }
      if (attempt < 3) await wait(250);
    }
    return false;
  }

  private scheduleHistoryRefresh(): void {
    if (this.historyRefreshTimer) window.clearTimeout(this.historyRefreshTimer);
    this.historyRefreshTimer = window.setTimeout(async () => {
      await this.refreshHistory();
      if (this.mode === "chat") this.renderChatTranscript();
    }, 420);
  }

  private onRuntimeState(state: RuntimeState): void {
    this.runtime = { ...this.runtime, ...(state || {}) };
    this.renderChrome();
    if (this.mode === "chat") this.updateSensorControls();
    if (this.mode === "settings") this.renderSettings();
  }

  private onBriefingData(data: BriefingData): void {
    if (!data) return;
    this.data = data;
    if (this.mode === "today") this.renderToday();
  }

  private onChatState(state: ChatState): void {
    const previousHistory = this.chat.currentHistoryUid;
    const previousAiState = this.chat.aiState;
    this.chat = { ...this.chat, ...(state || {}) };
    this.runtime = {
      ...this.runtime,
      aiState: this.chat.aiState,
      wsConnected: this.chat.wsConnected,
      confName: this.chat.confName,
      confUid: this.chat.confUid,
      currentHistoryUid: this.chat.currentHistoryUid,
      currentHistoryTitle: this.chat.currentHistoryTitle,
      latestAssistantText: this.chat.latestAssistantText,
      micEnabled: this.chat.micEnabled,
      micPaused: this.chat.micPaused,
      cameraEnabled: this.chat.cameraEnabled,
      screenEnabled: this.chat.screenEnabled,
      browserPanelEnabled: this.chat.browserPanelEnabled
    };
    this.renderChrome();
    if (this.mode === "chat") {
      this.updateChatHeader();
      this.renderChatTranscript();
      this.updateComposerState();
      this.updateSensorControls();
    }
    if (previousHistory !== this.chat.currentHistoryUid || (isBusyState(previousAiState) && !isBusyState(this.chat.aiState))) {
      this.scheduleHistoryRefresh();
    }
  }

  private setMode(mode: WorkMode, persist = true): void {
    this.mode = mode;
    this.setHistoryOpen(false, false);
    if (persist) window.localStorage.setItem("kuro.work-panel.mode", mode);
    if (mode !== "today") this.closeDetail(false);
    this.renderChrome();
    this.renderActiveView();
  }

  private setHistoryOpen(open: boolean, render = true): void {
    this.historyOpen = Boolean(open && this.mode === "chat");
    appRoot.querySelector<HTMLElement>("[data-stage]")?.classList.toggle("has-history", this.historyOpen);
    if (render) this.renderHistoryDrawer();
  }

  private renderHistoryDrawer(): void {
    const drawer = appRoot.querySelector<HTMLElement>("[data-history-drawer]");
    if (!drawer) return;
    drawer.replaceChildren();

    const header = createElement("div", "history-drawer-header");
    const heading = createElement("div");
    heading.appendChild(createElement("div", "detail-eyebrow", "LOCAL CONVERSATIONS"));
    heading.appendChild(createElement("h2", "history-drawer-title", "對話紀錄"));
    header.appendChild(heading);
    const close = button("icon-button", "×", () => this.setHistoryOpen(false));
    close.setAttribute("aria-label", "關閉對話紀錄");
    header.appendChild(close);
    drawer.appendChild(header);

    const actions = createElement("div", "history-drawer-actions");
    actions.appendChild(button("primary-button", "＋ 新對話", () => this.createNewHistory()));
    const search = createElement("input", "history-search") as HTMLInputElement;
    search.type = "search";
    search.placeholder = "搜尋對話";
    search.value = this.historyQuery;
    search.setAttribute("aria-label", "搜尋對話紀錄");
    search.addEventListener("input", () => {
      this.historyQuery = search.value;
      this.renderHistoryDrawer();
      window.setTimeout(() => {
        const next = appRoot.querySelector<HTMLInputElement>("[data-history-drawer] .history-search");
        next?.focus();
        next?.setSelectionRange(next.value.length, next.value.length);
      }, 0);
    });
    actions.appendChild(search);
    drawer.appendChild(actions);

    const list = createElement("div", "history-list");
    const records = Array.isArray(this.history.histories) ? this.history.histories : [];
    const query = this.historyQuery.trim().toLowerCase();
    const filtered = records.filter((record) => {
      if (!query) return true;
      return `${text(record.title)} ${text(record.preview)}`.toLowerCase().includes(query);
    });
    const activeUid = text(this.history.current_history_uid ?? this.chat.currentHistoryUid);

    if (!this.history.ok && !records.length) {
      const empty = createElement("div", "history-empty");
      empty.appendChild(createElement("strong", "", "對話服務尚未連線"));
      empty.appendChild(createElement("span", "", text(this.history.error, "Launcher control API 暫時無法使用。")));
      list.appendChild(empty);
    } else if (!filtered.length) {
      const empty = createElement("div", "history-empty");
      empty.appendChild(createElement("strong", "", query ? "找不到符合的對話" : "目前沒有對話紀錄"));
      empty.appendChild(createElement("span", "", query ? "換個關鍵字，或建立新對話。" : "按上方按鈕開始第一段對話。"));
      list.appendChild(empty);
    } else {
      filtered.forEach((record) => list.appendChild(this.historyRow(record, record.uid === activeUid)));
    }
    drawer.appendChild(list);
  }

  private historyRow(record: HistorySummary, active: boolean): HTMLElement {
    const row = createElement("div", `history-row${active ? " is-active" : ""}`);
    const open = button("history-open", "", () => this.selectHistory(record.uid));
    const title = createElement("strong", "history-title", text(record.title, "新對話"));
    const preview = createElement("span", "history-preview", text(record.preview, record.is_empty ? "尚未開始" : "沒有預覽"));
    const meta = createElement("span", "history-meta", `${formatDateLabel(record.timestamp, true) || "時間未知"}${active ? " · 目前" : ""}`);
    open.append(title, preview, meta);
    row.appendChild(open);
    const remove = button("history-delete", "", () => this.deleteHistory(record));
    remove.innerHTML = ICONS.delete;
    remove.setAttribute("aria-label", `刪除 ${text(record.title, "這段對話")}`);
    row.appendChild(remove);
    return row;
  }

  private applyHistoryPayload(payload: ChatHistoryPayload): void {
    this.history = payload || { ok: false, histories: [], messages: [] };
    const currentUid = text(payload.current_history_uid ?? payload.selected_history_uid);
    if (currentUid) {
      this.chat.currentHistoryUid = currentUid;
      this.runtime.currentHistoryUid = currentUid;
    }
    if (payload.title) {
      this.chat.currentHistoryTitle = payload.title;
      this.runtime.currentHistoryTitle = payload.title;
    }
    this.renderHistoryDrawer();
    if (this.mode === "chat") {
      this.updateChatHeader();
      this.renderChatTranscript();
    }
  }

  private async createNewHistory(): Promise<void> {
    this.showToast("正在建立新對話…");
    const result = await bridge.createHistory();
    if (!result?.ok) {
      this.showToast(text(result?.error, "新對話建立失敗。"), true);
      return;
    }
    this.contextItem = null;
    this.draft = "";
    this.applyHistoryPayload(result);
    this.setHistoryOpen(false);
    this.showToast("已建立新對話。");
  }

  private async selectHistory(historyUid: string): Promise<void> {
    if (!historyUid || historyUid === text(this.chat.currentHistoryUid)) {
      this.setHistoryOpen(false);
      return;
    }
    this.showToast("正在切換對話…");
    const result = await bridge.selectHistory(historyUid);
    if (!result?.ok) {
      this.showToast(text(result?.error, "對話切換失敗。"), true);
      return;
    }
    this.contextItem = null;
    this.draft = "";
    this.applyHistoryPayload(result);
    this.setHistoryOpen(false);
    this.showToast("已切換對話。");
  }

  private async deleteHistory(record: HistorySummary): Promise<void> {
    const result = await bridge.deleteHistory(record.uid, record.title);
    if (result?.cancelled) return;
    if (!result?.ok) {
      this.showToast(text(result?.error, "對話刪除失敗。"), true);
      return;
    }
    this.applyHistoryPayload(result);
    this.showToast("對話已刪除。");
  }

  private renderChrome(): void {
    const titleByMode: Record<WorkMode, string> = {
      chat: "普通對話",
      today: "今天與行事曆",
      settings: "設定"
    };
    const chromeTitle = appRoot.querySelector<HTMLElement>("[data-chrome-title]");
    const chromeMeta = appRoot.querySelector<HTMLElement>("[data-chrome-meta]");
    const presenceDot = appRoot.querySelector<HTMLElement>("[data-presence-dot]");
    const presenceLabel = appRoot.querySelector<HTMLElement>("[data-presence-label]");
    const statePulse = appRoot.querySelector<HTMLElement>("[data-state-pulse]");
    const privacy = appRoot.querySelector<HTMLElement>("[data-privacy-indicators]");
    if (chromeTitle) chromeTitle.textContent = titleByMode[this.mode];
    if (chromeMeta) {
      const profile = text(this.runtime.confName ?? this.chat.confName, "Kuro");
      const state = text(this.runtime.aiState ?? this.chat.aiState, "idle").toUpperCase();
      chromeMeta.textContent = `${profile} · ${state}`;
    }
    const online = Boolean(this.runtime.wsConnected ?? this.chat.wsConnected);
    presenceDot?.classList.toggle("is-online", online);
    if (presenceLabel) presenceLabel.textContent = online ? "Kuro 已連線" : "Kuro 離線";
    const aiState = text(this.runtime.aiState ?? this.chat.aiState, "idle").toLowerCase();
    if (statePulse) statePulse.dataset.state = online ? aiState : "offline";
    if (privacy) {
      privacy.replaceChildren();
      const activeSensors: Array<[string, boolean]> = [
        [this.microphonePaused() ? "麥克風暫停" : "麥克風", Boolean(this.runtime.micEnabled ?? this.chat.micEnabled)],
        ["鏡頭", Boolean(this.runtime.cameraEnabled ?? this.chat.cameraEnabled)],
        ["螢幕", Boolean(this.runtime.screenEnabled ?? this.chat.screenEnabled)]
      ];
      activeSensors.filter(([, enabled]) => enabled).forEach(([label]) => {
        privacy.appendChild(createElement("span", "privacy-chip", label));
      });
    }
    appRoot.querySelectorAll<HTMLButtonElement>("[data-mode]").forEach((element) => {
      const active = element.dataset.mode === this.mode;
      element.classList.toggle("is-active", active);
      element.setAttribute("aria-current", active ? "page" : "false");
    });
  }

  private renderActiveView(): void {
    this.renderChrome();
    if (this.mode === "chat") this.renderChat();
    if (this.mode === "today") this.renderToday();
    if (this.mode === "settings") this.renderSettings();
  }

  private viewRoot(): HTMLElement {
    const root = appRoot.querySelector<HTMLElement>("[data-view-root]");
    if (!root) throw new Error("Kuro work panel view root is missing.");
    return root;
  }

  private renderChat(): void {
    const root = this.viewRoot();
    root.replaceChildren();
    const frame = createElement("section", "chat-frame");
    frame.innerHTML = `
      <header class="chat-header">
        <div class="chat-heading-row">
          <div class="chat-title-cluster">
            <button class="history-toggle" type="button" data-history-toggle aria-label="開啟對話紀錄">${ICONS.history}</button>
            <div>
              <h1 class="chat-title" data-chat-title>普通對話</h1>
              <div class="chat-subtitle" data-chat-subtitle>目前對話</div>
            </div>
          </div>
          <div class="chat-header-actions">
            <label class="inline-select character-select"><span>角色</span><select data-character-select aria-label="目前角色"></select></label>
            <span class="runtime-pill" data-chat-runtime>正在確認連線</span>
          </div>
        </div>
        <div class="chat-context" data-chat-context>
          <div class="chat-context-copy" data-chat-context-copy></div>
          <button class="text-button" type="button" data-clear-context>清除</button>
        </div>
      </header>
      <div class="message-list" data-message-list aria-live="polite"><div class="message-list-inner" data-message-inner></div></div>
      <div class="composer-wrap">
        <div class="attachment-row" data-attachment-row></div>
        <div class="conversation-controls">
          <div class="sensor-controls" aria-label="語音與畫面輸入">
            <button class="sensor-button" type="button" data-sensor="microphone" aria-label="開啟麥克風">${ICONS.mic}<span>麥克風</span></button>
            <button class="sensor-button mic-submit" type="button" data-mic-action="submit" aria-label="完成並送出錄音" hidden>${ICONS.send}<span>送出錄音</span></button>
            <button class="sensor-button mic-cancel" type="button" data-mic-action="cancel" aria-label="取消錄音" hidden>${ICONS.cancel}<span>取消</span></button>
            <button class="sensor-button" type="button" data-sensor="camera" aria-label="開啟鏡頭">${ICONS.camera}<span>鏡頭</span></button>
            <button class="sensor-button" type="button" data-sensor="screen" aria-label="本回合擷取螢幕">${ICONS.screen}<span>本回合螢幕</span></button>
          </div>
          <div class="response-controls">
            <label class="inline-select"><span>模型</span><select data-model-select aria-label="LLM 模型"></select></label>
            <label class="inline-select"><span>推理</span><select data-thinking-select aria-label="推理深度"></select></label>
          </div>
        </div>
        <div class="composer">
          <button class="composer-button" type="button" data-attach aria-label="加入附件">${ICONS.attach}</button>
          <textarea rows="1" data-composer-input aria-label="輸入普通對話" placeholder="問 Kuro，或從今天的項目延伸討論…"></textarea>
          <button class="composer-button send" type="button" data-composer-action aria-label="送出訊息">${ICONS.send}</button>
          <input type="file" data-file-input hidden multiple />
        </div>
        <div class="composer-foot"><span data-composer-notice>Enter 送出 · Shift + Enter 換行</span><span data-ai-state>IDLE</span></div>
      </div>
    `;
    root.appendChild(frame);

    const input = root.querySelector<HTMLTextAreaElement>("[data-composer-input]");
    if (input) {
      input.value = this.draft;
      input.addEventListener("input", () => {
        this.draft = input.value;
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 144)}px`;
      });
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          this.sendCurrentText();
        }
      });
    }
    root.querySelector<HTMLButtonElement>("[data-attach]")?.addEventListener("click", () => {
      root.querySelector<HTMLInputElement>("[data-file-input]")?.click();
    });
    root.querySelector<HTMLInputElement>("[data-file-input]")?.addEventListener("change", (event) => {
      const fileInput = event.currentTarget as HTMLInputElement;
      this.addFiles(fileInput.files).finally(() => { fileInput.value = ""; });
    });
    root.querySelector<HTMLButtonElement>("[data-composer-action]")?.addEventListener("click", () => {
      if (this.profileApplying) return;
      if (isBusyState(this.chat.aiState) || this.sending) this.stopOutput();
      else this.sendCurrentText();
    });
    root.querySelector<HTMLButtonElement>("[data-clear-context]")?.addEventListener("click", () => {
      this.contextItem = null;
      this.renderChatContext();
    });
    root.querySelector<HTMLButtonElement>("[data-history-toggle]")?.addEventListener("click", async () => {
      if (!this.historyOpen) await this.refreshHistory();
      this.setHistoryOpen(!this.historyOpen);
    });
    root.querySelectorAll<HTMLButtonElement>("[data-sensor]").forEach((element) => {
      element.addEventListener("click", () => {
        const kind = String(element.dataset.sensor || "");
        if (kind === "microphone") void this.handleMicrophonePrimary();
        else void this.toggleSensor(kind);
      });
    });
    root.querySelectorAll<HTMLButtonElement>("[data-mic-action]").forEach((element) => {
      element.addEventListener("click", () => {
        void this.runMicrophoneAction(String(element.dataset.micAction || ""));
      });
    });
    this.populateChatControls();
    this.updateChatHeader();
    this.renderChatContext();
    this.renderChatTranscript();
    this.renderAttachments();
    this.updateComposerState();
    this.updateSensorControls();
  }

  private updateChatHeader(): void {
    if (this.mode !== "chat") return;
    const titleElement = this.viewRoot().querySelector<HTMLElement>("[data-chat-title]");
    const subtitleElement = this.viewRoot().querySelector<HTMLElement>("[data-chat-subtitle]");
    const runtimeElement = this.viewRoot().querySelector<HTMLElement>("[data-chat-runtime]");
    const historyTitle = text(this.chat.currentHistoryTitle ?? this.history.title, "普通對話");
    if (titleElement) titleElement.textContent = historyTitle;
    if (subtitleElement) {
      subtitleElement.textContent = this.chat.currentHistoryUid
        ? `目前對話 · ${text(this.chat.confName, "Kuro")}`
        : "尚未選取對話 · 可直接開始聊天";
    }
    if (runtimeElement) {
      const online = Boolean(this.chat.wsConnected);
      runtimeElement.classList.toggle("is-online", online);
      runtimeElement.textContent = online ? `已連線 · ${text(this.chat.aiState, "idle")}` : "離線 · 訊息暫時無法送出";
    }
  }

  private populateChatControls(): void {
    if (this.mode !== "chat") return;
    const selected = this.pendingProfileSelection || this.profile.selected || {};
    const character = this.viewRoot().querySelector<HTMLSelectElement>("[data-character-select]");
    const model = this.viewRoot().querySelector<HTMLSelectElement>("[data-model-select]");
    const thinking = this.viewRoot().querySelector<HTMLSelectElement>("[data-thinking-select]");

    if (character) {
      character.replaceChildren();
      const configured = Array.isArray(this.profile.characters) ? this.profile.characters : [];
      const options = configured.length
        ? configured
        : [{ id: text(this.chat.confUid, "__unavailable__"), name: text(this.chat.confName, "Kuro") }];
      options.filter((item) => item.id).forEach((item) => {
        const option = createElement("option") as HTMLOptionElement;
        option.value = item.id;
        option.textContent = text(item.name, item.id);
        character.appendChild(option);
      });
      character.value = text(selected.character_id ?? this.chat.confUid, options[0]?.id);
      character.disabled = this.profileApplying || !this.profile.ok;
      character.addEventListener("change", () => this.applyProfilePatch({ character_id: character.value }));
    }

    if (model) {
      model.replaceChildren();
      const configured = Array.isArray(this.profile.models) ? this.profile.models : [];
      const models = configured.length ? configured : [text(selected.model, "Launcher 未連線")];
      models.forEach((item) => {
        const option = createElement("option") as HTMLOptionElement;
        option.value = item;
        option.textContent = item;
        model.appendChild(option);
      });
      model.value = text(selected.model, models[0]);
      model.disabled = this.profileApplying || !this.profile.ok || models.length < 2;
      model.addEventListener("change", () => this.applyProfilePatch({ model: model.value }));
    }

    if (thinking) {
      thinking.replaceChildren();
      const labels: Record<string, string> = { fast: "快速", normal: "普通", deep: "深度" };
      const options = Array.isArray(this.profile.thinking_options)
        ? this.profile.thinking_options
        : ["fast", "normal", "deep"];
      options.forEach((item) => {
        const option = createElement("option") as HTMLOptionElement;
        option.value = item;
        option.textContent = labels[item] || item;
        thinking.appendChild(option);
      });
      thinking.value = text(selected.thinking_power, "normal");
      thinking.disabled = this.profileApplying || !this.profile.ok;
      thinking.addEventListener("change", () => this.applyProfilePatch({ thinking_power: thinking.value }));
    }
  }

  private async applyProfilePatch(patch: Record<string, string>): Promise<void> {
    if (this.profileApplying) return;
    const selected = this.profile.selected || {};
    const payload = {
      character_id: text(patch.character_id ?? selected.character_id),
      project_id: text(patch.project_id ?? selected.project_id),
      model: text(patch.model ?? selected.model),
      thinking_power: text(patch.thinking_power ?? selected.thinking_power, "normal")
    };
    if (!payload.character_id || !payload.project_id || !payload.model) {
      this.showToast("助理設定資料不完整，請到進階診斷確認 launcher。", true);
      this.renderActiveView();
      return;
    }
    this.pendingProfileSelection = payload;
    this.profileApplying = true;
    this.renderActiveView();
    this.showToast("正在套用助理設定；角色語音不同時可能需要約 30 秒…", false, null);
    try {
      const result = await bridge.applyProfile(payload) as Record<string, unknown> & {
        cancelled?: boolean;
        profile?: ProfileState;
        result?: { warning?: string };
      };
      if (result?.cancelled) {
        await this.reconcileProfileRuntime("");
        this.hideToast();
        return;
      }
      if (!result?.ok) {
        await this.reconcileProfileRuntime("");
        this.showToast(text(result?.error, "助理設定套用失敗。"), true);
        return;
      }
      if (result.profile) this.profile = result.profile;
      const runtimeSynced = await this.reconcileProfileRuntime(payload.character_id);
      await Promise.all([this.refreshHistory(), this.refreshMemories()]);
      const characterName = text(
        this.profile.characters?.find((item) => item.id === payload.character_id)?.name,
        payload.character_id
      );
      const warning = text(result.result?.warning);
      if (warning) {
        this.showToast(`已切換為 ${characterName}，但有警告：${warning}`, true, 5200);
      } else if (!runtimeSynced) {
        this.showToast(`Launcher 已切換為 ${characterName}，但桌寵狀態尚未同步；請稍候或重新載入前端。`, true, 5200);
      } else {
        this.showToast(`已切換為 ${characterName}。`);
      }
    } catch (error) {
      await this.reconcileProfileRuntime("");
      const message = error instanceof Error ? error.message : text(error);
      this.showToast(`助理設定套用失敗：${text(message, "未知錯誤")}`, true, 5200);
    } finally {
      this.pendingProfileSelection = null;
      this.profileApplying = false;
      this.renderActiveView();
    }
  }

  private sensorEnabled(kind: string): boolean {
    if (kind === "microphone") return Boolean(this.runtime.micEnabled ?? this.chat.micEnabled);
    if (kind === "camera") return Boolean(this.runtime.cameraEnabled ?? this.chat.cameraEnabled);
    if (kind === "screen") return Boolean(this.runtime.screenEnabled ?? this.chat.screenEnabled);
    return false;
  }

  private microphonePaused(): boolean {
    return Boolean(this.runtime.micPaused ?? this.chat.micPaused);
  }

  private updateSensorControls(): void {
    if (this.mode !== "chat") return;
    this.viewRoot().querySelectorAll<HTMLButtonElement>("[data-sensor]").forEach((element) => {
      const kind = String(element.dataset.sensor || "");
      const enabled = this.sensorEnabled(kind);
      const paused = kind === "microphone" && this.microphonePaused();
      element.classList.toggle("is-on", enabled);
      element.classList.toggle("is-paused", paused);
      element.classList.toggle("is-pending", this.sensorPending.startsWith(kind));
      element.disabled = Boolean(this.sensorPending);
      element.setAttribute("aria-pressed", String(enabled));
      const label = element.querySelector<HTMLElement>("span");
      if (kind === "microphone") {
        element.innerHTML = enabled
          ? `${paused ? ICONS.resume : ICONS.pause}<span>${paused ? "繼續錄音" : "暫停"}</span>`
          : `${ICONS.mic}<span>麥克風</span>`;
        element.setAttribute("aria-label", enabled ? (paused ? "繼續錄音" : "暫停錄音") : "開啟麥克風");
      }
      if (label && kind === "camera") label.textContent = enabled ? "鏡頭開啟" : "鏡頭";
      if (label && kind === "screen") label.textContent = enabled ? "螢幕擷取中" : "本回合螢幕";
    });
    const micEnabled = this.sensorEnabled("microphone");
    this.viewRoot().querySelectorAll<HTMLButtonElement>("[data-mic-action]").forEach((element) => {
      element.hidden = !micEnabled;
      element.disabled = Boolean(this.sensorPending);
    });
  }

  private async handleMicrophonePrimary(): Promise<void> {
    if (!this.sensorEnabled("microphone")) {
      await this.runMicrophoneAction("start");
      return;
    }
    await this.runMicrophoneAction(this.microphonePaused() ? "resume" : "pause");
  }

  private async runMicrophoneAction(action: string): Promise<void> {
    if (this.sensorPending || !["start", "pause", "resume", "submit", "cancel"].includes(action)) return;
    this.sensorPending = `microphone-${action}`;
    this.updateSensorControls();
    const result = await bridge.control(`mic-${action}`, {});
    this.sensorPending = "";
    if (!result?.ok) {
      this.showToast(text(result?.error, "麥克風操作失敗；請確認 Windows 權限。"), true);
      this.updateSensorControls();
      if (this.mode === "settings") this.renderSettings();
      return;
    }

    const micEnabled = typeof result.micEnabled === "boolean"
      ? result.micEnabled
      : !["submit", "cancel"].includes(action);
    const micPaused = typeof result.micPaused === "boolean"
      ? result.micPaused
      : action === "pause";
    this.runtime = { ...this.runtime, micEnabled, micPaused };
    this.chat = { ...this.chat, micEnabled, micPaused };
    this.renderChrome();
    this.updateSensorControls();
    if (this.mode === "settings") this.renderSettings();

    const message = action === "start"
      ? "已開始錄音。"
      : action === "pause"
        ? "錄音已暫停，內容尚未送出。"
        : action === "resume"
          ? "已繼續錄音。"
          : action === "cancel"
            ? "錄音已取消，內容未送出。"
            : result.empty
              ? "沒有錄到內容，未送出。"
              : "錄音已送出。";
    this.showToast(message, Boolean(result.empty));
  }

  private async toggleSensor(kind: string): Promise<void> {
    if (this.sensorPending || !["camera", "screen"].includes(kind)) return;
    const action = kind === "camera" ? "toggle-camera" : "toggle-screen";
    const enabled = !this.sensorEnabled(kind);
    this.sensorPending = kind;
    this.updateSensorControls();
    const result = await bridge.control(action, { enabled });
    this.sensorPending = "";
    if (!result?.ok) {
      this.showToast(text(result?.error, "感知功能無法開啟；請確認 Windows 權限。"), true);
      this.updateSensorControls();
      if (this.mode === "settings") this.renderSettings();
      return;
    }
    const key = kind === "camera" ? "cameraEnabled" : "screenEnabled";
    this.runtime = { ...this.runtime, [key]: enabled };
    this.chat = { ...this.chat, [key]: enabled };
    this.renderChrome();
    this.updateSensorControls();
    if (this.mode === "settings") this.renderSettings();
    this.showToast(
      enabled
        ? `${kind === "camera" ? "鏡頭" : "本回合螢幕擷取"}已開啟。`
        : "感知功能已關閉。"
    );
  }

  private mergedChatMessages(): HistoryMessage[] {
    const messages = Array.isArray(this.history.messages) ? [...this.history.messages] : [];
    const latestUser = text(this.chat.latestUserText);
    const latestAssistant = text(this.chat.latestAssistantText);
    const lastUser = [...messages].reverse().find((item) => ["human", "user"].includes(text(item.role).toLowerCase()));
    const lastAssistant = [...messages].reverse().find((item) => ["ai", "assistant"].includes(text(item.role).toLowerCase()));
    if (latestUser && text(lastUser?.content) !== latestUser) {
      messages.push({ role: "human", content: latestUser });
    }
    if (latestAssistant && text(lastAssistant?.content) !== latestAssistant) {
      messages.push({ role: "assistant", content: latestAssistant });
    }
    return messages.slice(-120);
  }

  private renderChatTranscript(): void {
    if (this.mode !== "chat") return;
    const list = this.viewRoot().querySelector<HTMLElement>("[data-message-list]");
    const inner = this.viewRoot().querySelector<HTMLElement>("[data-message-inner]");
    if (!list || !inner) return;
    const wasNearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 120;
    inner.replaceChildren();
    const messages = this.mergedChatMessages();
    if (!messages.length && !isBusyState(this.chat.aiState)) {
      const empty = createElement("div", "chat-empty");
      const content = createElement("div");
      content.innerHTML = `<div class="chat-empty-mark" aria-hidden="true">K</div><h2>這裡就是普通對話</h2><p>不用先選專案。你可以直接聊天、附上檔案；從 Today 帶入的項目也會回到同一個對話框。</p>`;
      empty.appendChild(content);
      inner.appendChild(empty);
    } else {
      messages.forEach((message) => {
        const row = createElement("article", `message ${messageRoleClass(message.role)}`);
        row.appendChild(createElement("div", "message-role", messageRoleLabel(message.role)));
        const content = createElement("div");
        content.appendChild(createElement("div", "message-copy", text(message.content)));
        const timeValue = formatDateLabel(message.timestamp, true);
        if (timeValue) content.appendChild(createElement("div", "message-time", timeValue));
        row.appendChild(content);
        inner.appendChild(row);
      });
      if (isBusyState(this.chat.aiState) && !text(this.chat.latestAssistantText)) {
        const row = createElement("article", "message is-assistant");
        row.appendChild(createElement("div", "message-role", "KURO"));
        const typing = createElement("div", "typing-line");
        typing.innerHTML = `<span>正在整理回覆</span><i></i><i></i><i></i>`;
        row.appendChild(typing);
        inner.appendChild(row);
      }
    }
    if (wasNearBottom || !messages.length) list.scrollTop = list.scrollHeight;
  }

  private renderChatContext(): void {
    if (this.mode !== "chat") return;
    const context = this.viewRoot().querySelector<HTMLElement>("[data-chat-context]");
    const copy = this.viewRoot().querySelector<HTMLElement>("[data-chat-context-copy]");
    if (!context || !copy) return;
    context.classList.toggle("is-visible", Boolean(this.contextItem));
    copy.replaceChildren();
    if (this.contextItem) {
      copy.append("目前帶入：");
      copy.appendChild(createElement("strong", "", this.contextItem.title));
      copy.append(` · ${sourceLabel(this.contextItem.source)}`);
    }
  }

  private updateComposerState(): void {
    if (this.mode !== "chat") return;
    const action = this.viewRoot().querySelector<HTMLButtonElement>("[data-composer-action]");
    const attach = this.viewRoot().querySelector<HTMLButtonElement>("[data-attach]");
    const input = this.viewRoot().querySelector<HTMLTextAreaElement>("[data-composer-input]");
    const notice = this.viewRoot().querySelector<HTMLElement>("[data-composer-notice]");
    const state = this.viewRoot().querySelector<HTMLElement>("[data-ai-state]");
    const busy = this.sending || isBusyState(this.chat.aiState);
    if (action) {
      action.classList.toggle("send", !busy);
      action.classList.toggle("stop", busy);
      action.innerHTML = busy ? ICONS.stop : ICONS.send;
      action.setAttribute("aria-label", busy ? "停止目前輸出" : "送出訊息");
      action.disabled = this.profileApplying;
    }
    if (attach) attach.disabled = this.sending || this.profileApplying;
    if (input) input.disabled = this.profileApplying;
    if (notice && !notice.classList.contains("is-error")) {
      notice.textContent = this.profileApplying
        ? "角色切換中；完成前暫停送出新訊息"
        : this.chat.wsConnected
          ? "Enter 送出 · Shift + Enter 換行"
          : "Kuro 離線；可先保留草稿";
    }
    if (state) {
      state.textContent = this.profileApplying
        ? "SWITCHING"
        : text(this.chat.aiState, "idle").toUpperCase();
    }
  }

  private setComposerNotice(message: string, error = false): void {
    if (this.mode !== "chat") return;
    const notice = this.viewRoot().querySelector<HTMLElement>("[data-composer-notice]");
    if (!notice) return;
    notice.textContent = message;
    notice.classList.toggle("is-error", error);
    window.setTimeout(() => {
      if (!notice.isConnected) return;
      notice.classList.remove("is-error");
      notice.textContent = this.chat.wsConnected ? "Enter 送出 · Shift + Enter 換行" : "Kuro 離線；可先保留草稿";
    }, 2600);
  }

  private async addFiles(fileList: FileList | null): Promise<void> {
    const files = Array.from(fileList || []);
    for (const file of files) {
      if (this.attachments.length >= 6) {
        this.setComposerNotice("一次最多加入 6 個附件。", true);
        break;
      }
      const kind = classifyFile(file);
      if (file.size > attachmentLimit(kind)) {
        this.setComposerNotice(`${file.name} 超過附件大小限制。`, true);
        continue;
      }
      try {
        this.attachments.push({
          kind,
          name: file.name,
          size: file.size,
          mime_type: text(file.type, "application/octet-stream"),
          data: await readFileAsDataUrl(file)
        });
      } catch (_error) {
        this.setComposerNotice(`${file.name} 讀取失敗。`, true);
      }
    }
    this.renderAttachments();
  }

  private renderAttachments(): void {
    if (this.mode !== "chat") return;
    const row = this.viewRoot().querySelector<HTMLElement>("[data-attachment-row]");
    if (!row) return;
    row.replaceChildren();
    this.attachments.forEach((attachment, index) => {
      const chip = createElement("div", "attachment-chip");
      chip.appendChild(createElement("span", "", `${attachment.name} · ${formatFileSize(attachment.size)}`));
      const remove = button("", "×", () => {
        this.attachments.splice(index, 1);
        this.renderAttachments();
      });
      remove.setAttribute("aria-label", `移除 ${attachment.name}`);
      chip.appendChild(remove);
      row.appendChild(chip);
    });
  }

  private async sendCurrentText(): Promise<void> {
    if (this.profileApplying || this.sending || isBusyState(this.chat.aiState)) return;
    const input = this.mode === "chat"
      ? this.viewRoot().querySelector<HTMLTextAreaElement>("[data-composer-input]")
      : null;
    const message = text(input?.value ?? this.draft);
    if (!message && !this.attachments.length) return;
    this.sending = true;
    this.updateComposerState();
    try {
      const result = await bridge.sendText(message, this.attachments);
      if (result?.ok) {
        this.draft = "";
        this.attachments = [];
        if (input) {
          input.value = "";
          input.style.height = "auto";
        }
        this.renderAttachments();
        this.scheduleHistoryRefresh();
      } else {
        this.setComposerNotice(text(result?.error, "訊息送出失敗。"), true);
      }
    } catch (_error) {
      this.setComposerNotice("訊息送出失敗。", true);
    } finally {
      this.sending = false;
      this.updateComposerState();
    }
  }

  private async stopOutput(): Promise<void> {
    const result = await bridge.control("interrupt");
    this.showToast(result?.ok ? "已要求停止目前輸出。" : text(result?.error, "停止輸出失敗。"), !result?.ok);
  }

  private renderToday(): void {
    const root = this.viewRoot();
    root.replaceChildren();
    const frame = createElement("section", "view-frame today-frame");
    const snapshot = this.data.snapshot || {};
    const counts = snapshot.today?.counts || {};
    const attention = Number(counts.attention || 0);
    const actionable = Number(counts.actionable || 0);
    const updatedAt = formatDateLabel(snapshot.updatedAt, true) || "尚未更新";

    const header = createElement("header");
    header.innerHTML = `
      <p class="section-kicker">${formatFullDate()}</p>
      <h1 class="today-question">現在有什麼<em>值得注意</em>？</h1>
      <div class="today-summary">
        <span><strong>${attention}</strong> 個注意項目</span>
        <span><strong>${actionable}</strong> 個需要處理</span>
        <span>Snapshot ${updatedAt}</span>
      </div>
    `;
    frame.appendChild(header);

    const primary = createElement("div", "today-primary");
    primary.appendChild(this.renderPriorityBlock());
    primary.appendChild(this.renderScheduleBlock());
    frame.appendChild(primary);
    frame.appendChild(this.renderSourcesBlock());
    root.appendChild(frame);
    this.renderDetail();
  }

  private renderPriorityBlock(): HTMLElement {
    const block = createElement("section");
    const items = priorityItems(this.data);
    const heading = createElement("div", "block-heading");
    heading.innerHTML = `<h2>優先處理</h2><span>${items.length ? `TOP ${items.length}` : "CLEAR"}</span>`;
    block.appendChild(heading);
    const list = createElement("div", "priority-list");
    if (!items.length) {
      const empty = createElement("div", "empty-state");
      empty.innerHTML = `<div><strong>目前沒有高優先項目</strong><span>這不代表所有來源都已更新；請同時查看下方來源狀態。</span></div>`;
      list.appendChild(empty);
    } else {
      items.forEach((item) => {
        const row = button("priority-item", "", () => this.openDetail(item));
        row.classList.toggle("is-selected", this.selectedItem?.id === item.id);
        row.appendChild(createElement("div", "priority-source", sourceLabel(item.source)));
        const copy = createElement("div");
        copy.appendChild(createElement("div", "priority-title", item.title));
        copy.appendChild(createElement("div", "priority-meta", item.meta || formatDateLabel(item.date, true) || "等待進一步資料"));
        row.appendChild(copy);
        row.appendChild(createElement("span", `level-pill level-${item.level}`, levelLabel(item.level)));
        list.appendChild(row);
      });
    }
    block.appendChild(list);
    return block;
  }

  private renderScheduleBlock(): HTMLElement {
    const block = createElement("section");
    const items = scheduleItems(this.data);
    const heading = createElement("div", "block-heading");
    heading.innerHTML = `<h2>今日行程</h2><span>${items.length} EVENTS</span>`;
    block.appendChild(heading);
    const schedule = createElement("div", "schedule");
    if (!items.length) {
      const empty = createElement("div", "schedule-empty");
      empty.textContent = "目前 snapshot 沒有可顯示的行事曆項目。Kuro 不會用其他來源的內容假裝成行程。";
      schedule.appendChild(empty);
    } else {
      items.slice(0, 7).forEach((item) => {
        const row = button("schedule-item", "", () => this.openDetail(item));
        row.appendChild(createElement("div", "schedule-time", formatDateLabel(item.date, true) || item.meta || "未指定時間"));
        row.appendChild(createElement("div", "schedule-title", item.title));
        row.appendChild(createElement("div", "schedule-meta", item.evidence || sourceLabel(item.source)));
        schedule.appendChild(row);
      });
    }
    block.appendChild(schedule);
    return block;
  }

  private renderSourcesBlock(): HTMLElement {
    const block = createElement("section", "sources-block");
    const heading = createElement("div", "block-heading");
    heading.innerHTML = `<h2>來源預覽</h2><span>FILTER, NOT NAVIGATION</span>`;
    block.appendChild(heading);
    const filters = createElement("div", "source-filters");
    SOURCE_ORDER.forEach((source) => {
      const filter = button("source-filter", sourceLabel(source), () => {
        this.selectedSource = source;
        window.localStorage.setItem("kuro.work-panel.source", source);
        this.renderToday();
      });
      filter.classList.toggle("is-active", this.selectedSource === source);
      const count = createElement("small", "", String(sourceCount(this.data, source)));
      filter.appendChild(count);
      filters.appendChild(filter);
    });
    block.appendChild(filters);

    const status = sourceStatus(this.data, this.selectedSource);
    const statusLine = createElement("div", "source-status-line");
    const statusCopy = createElement("div", "source-status-copy");
    if (this.selectedSource === "all") {
      statusCopy.textContent = `顯示目前 snapshot 內可用的全部來源 · ${formatDateLabel(this.data.snapshot?.updatedAt, true) || "更新時間未知"}`;
    } else if (status) {
      statusCopy.textContent = `${text(status.label, sourceLabel(this.selectedSource))} · ${text(status.message, "沒有額外狀態說明")}`;
    } else {
      statusCopy.textContent = `${sourceLabel(this.selectedSource)} · 尚未提供來源狀態`;
    }
    statusLine.appendChild(statusCopy);
    const controls = createElement("div");
    if (this.selectedSource === "mail") {
      controls.appendChild(button("quiet-button", "手動更新 Mail", () => this.refreshMail()));
    } else {
      controls.appendChild(createElement("span", `status-pill tone-${statusTone(status?.status)}`, statusLabel(status?.status)));
    }
    statusLine.appendChild(controls);
    block.appendChild(statusLine);

    const list = createElement("div", "source-list");
    const items = sourceItems(this.data, this.selectedSource).slice(0, 18);
    if (!items.length) {
      const empty = createElement("div", "empty-state");
      const emptyTitle = this.selectedSource === "all"
        ? "目前沒有可顯示的來源項目"
        : `${sourceLabel(this.selectedSource)} 目前沒有項目`;
      empty.innerHTML = `<div><strong>${emptyTitle}</strong><span>空白不等於完成；若來源狀態未知，請到設定查看連線資訊。</span></div>`;
      list.appendChild(empty);
    } else {
      items.forEach((item) => {
        const row = button("source-item", "", () => this.openDetail(item));
        const copy = createElement("div");
        copy.appendChild(createElement("div", "source-item-title", item.title));
        copy.appendChild(createElement("div", "source-item-meta", `${sourceLabel(item.source)} · ${item.meta || formatDateLabel(item.date, true) || levelLabel(item.level)}`));
        row.appendChild(copy);
        row.appendChild(createElement("span", "source-item-arrow", "↗"));
        list.appendChild(row);
      });
    }
    block.appendChild(list);
    return block;
  }

  private async refreshMail(): Promise<void> {
    const confirmed = window.confirm("要現在手動更新 Mail 摘要嗎？這會呼叫既有的唯讀 Mail refresh 流程。");
    if (!confirmed) return;
    this.showToast("正在更新 Mail…");
    try {
      const result = await bridge.refreshMail();
      this.showToast(result?.ok ? "Mail 更新完成。" : text(result?.error, "Mail 更新失敗。"), !result?.ok);
    } catch (_error) {
      this.showToast("Mail 更新失敗。", true);
    }
  }

  private openDetail(item: ViewItem): void {
    this.selectedItem = item;
    this.mailDetail = null;
    this.renderDetail();
    if (item.source === "mail" && item.refId) this.loadMailDetail(item.refId);
  }

  private async loadMailDetail(messageId: string): Promise<void> {
    try {
      const result = await bridge.getMailMessage(messageId);
      if (result?.ok && result.message && typeof result.message === "object") {
        this.mailDetail = result.message as Record<string, unknown>;
      } else {
        this.mailDetail = { error: text(result?.error, "信件內容讀取失敗。") };
      }
    } catch (_error) {
      this.mailDetail = { error: "信件內容讀取失敗。" };
    }
    this.renderDetail();
  }

  private closeDetail(clearSelection = true): void {
    if (clearSelection) {
      this.selectedItem = null;
      this.mailDetail = null;
    }
    this.renderDetail();
  }

  private renderDetail(): void {
    const stage = appRoot.querySelector<HTMLElement>("[data-stage]");
    const drawer = appRoot.querySelector<HTMLElement>("[data-detail-drawer]");
    if (!stage || !drawer) return;
    const visible = this.mode === "today" && Boolean(this.selectedItem);
    stage.classList.toggle("has-detail", visible);
    drawer.replaceChildren();
    if (!visible || !this.selectedItem) return;

    const item = this.selectedItem;
    const scroll = createElement("div", "detail-scroll");
    const topline = createElement("div", "detail-topline");
    topline.appendChild(createElement("div", "detail-eyebrow", `${sourceLabel(item.source)} / ${levelLabel(item.level)}`));
    const close = button("icon-button", "×", () => this.closeDetail());
    close.setAttribute("aria-label", "關閉詳情");
    topline.appendChild(close);
    scroll.appendChild(topline);
    scroll.appendChild(createElement("h2", "detail-title", text(this.mailDetail?.subject, item.title)));

    const meta = createElement("dl", "detail-meta-list");
    const rows: Array<[string, string]> = [
      ["來源", sourceLabel(item.source)],
      ["優先度", levelLabel(item.level)],
      ["時間", formatDateLabel(this.mailDetail?.date ?? item.date, true) || item.meta || "未提供"],
      ["狀態", statusLabel(sourceStatus(this.data, item.source)?.status)]
    ];
    if (this.mailDetail) {
      const sender = text(this.mailDetail.from ?? this.mailDetail.senderEmail);
      if (sender) rows.splice(1, 0, ["寄件者", sender]);
    }
    rows.forEach(([key, value]) => {
      meta.appendChild(createElement("dt", "", key));
      meta.appendChild(createElement("dd", "", value));
    });
    scroll.appendChild(meta);

    const error = text(this.mailDetail?.error);
    const fullBody = text(this.mailDetail?.bodyText);
    const copy = createElement("div", "detail-copy");
    if (error) copy.textContent = error;
    else if (fullBody) copy.textContent = fullBody;
    else if (item.source === "mail" && item.refId && !this.mailDetail) copy.textContent = "正在按需讀取完整信件內容…";
    else copy.textContent = item.evidence || item.meta || "這個項目目前沒有更多內容。";
    scroll.appendChild(copy);

    if (item.source === "mail") {
      scroll.appendChild(createElement("p", "detail-note", "信件本文只在你開啟這個項目時按需讀取；附件不會自動下載，信箱也不會被修改。"));
    } else {
      scroll.appendChild(createElement("p", "detail-note", "此處只呈現來源已提供的內容與狀態；Kuro 前端不會自行補做市場、新聞或排程判斷。"));
    }
    const actions = createElement("div", "detail-actions");
    actions.appendChild(button("primary-button", "帶到普通對話", () => this.bringItemToChat(item)));
    actions.appendChild(button("quiet-button", "關閉詳情", () => this.closeDetail()));
    scroll.appendChild(actions);
    drawer.appendChild(scroll);
  }

  private bringItemToChat(item: ViewItem): void {
    this.contextItem = item;
    this.draft = `關於「${item.title}」：`;
    this.setMode("chat");
    window.setTimeout(() => {
      const input = this.viewRoot().querySelector<HTMLTextAreaElement>("[data-composer-input]");
      input?.focus();
      input?.setSelectionRange(input.value.length, input.value.length);
    }, 0);
  }

  private renderSettings(): void {
    const root = this.viewRoot();
    root.replaceChildren();
    const frame = createElement("section", "view-frame settings-frame");
    const header = createElement("div", "section-heading-row");
    const heading = createElement("div");
    heading.innerHTML = `<p class="section-kicker">CONTROL & PRIVACY</p><h1 class="section-title">設定</h1><p class="section-description">在同一個工作面板管理助理、記憶、感知功能與桌寵。資料與權限仍由 launcher／runtime 擁有，寫入操作會由桌面原生視窗再次確認。</p>`;
    header.appendChild(heading);
    frame.appendChild(header);

    const shell = createElement("div", "settings-shell");
    const navigation = createElement("nav", "settings-nav");
    const sections: Array<[string, string, string]> = [
      ["assistant", "助理", "角色、專案、模型與推理"],
      ["conversation", "對話與記憶", "紀錄、保存與長期記憶"],
      ["perception", "語音與感知", "麥克風、鏡頭與螢幕"],
      ["tools", "工具與權限", "目前可用能力與限制"],
      ["pet", "桌寵與外觀", "服裝、表情與桌面行為"],
      ["diagnostics", "進階診斷", "runtime、來源與本機偏好"]
    ];
    sections.forEach(([id, label, description]) => {
      const item = button(`settings-nav-item${this.settingsSection === id ? " is-active" : ""}`, "", () => {
        this.settingsSection = id;
        window.localStorage.setItem("kuro.work-panel.settings-section", id);
        this.renderSettings();
      });
      item.appendChild(createElement("strong", "", label));
      item.appendChild(createElement("span", "", description));
      navigation.appendChild(item);
    });
    const content = createElement("div", "settings-content");
    if (this.settingsSection === "assistant") content.appendChild(this.settingsAssistantGroup());
    else if (this.settingsSection === "conversation") content.append(this.settingsConversationGroup(), this.settingsMemoryGroup());
    else if (this.settingsSection === "perception") content.appendChild(this.settingsPerceptionGroup());
    else if (this.settingsSection === "tools") content.appendChild(this.settingsToolsGroup());
    else if (this.settingsSection === "pet") content.appendChild(this.settingsPetGroup());
    else content.append(this.settingsExperienceGroup(), this.settingsRuntimeGroup(), this.settingsSourceGroup());
    shell.append(navigation, content);
    frame.appendChild(shell);
    root.appendChild(frame);
  }

  private settingsSelectRow(
    title: string,
    description: string,
    options: SelectOption[],
    currentValue: string,
    labels?: Record<string, string>
  ): { row: HTMLElement; select: HTMLSelectElement } {
    const row = createElement("div", "setting-row setting-row-select");
    const copy = createElement("div", "setting-copy");
    copy.appendChild(createElement("strong", "", title));
    copy.appendChild(createElement("span", "", description));
    const select = createElement("select", "settings-select") as HTMLSelectElement;
    options.forEach((item) => {
      const option = createElement("option") as HTMLOptionElement;
      option.value = item.id;
      option.textContent = labels?.[item.id] || text(item.name ?? item.label, item.id);
      select.appendChild(option);
    });
    select.value = currentValue;
    select.disabled = this.profileApplying || !options.length;
    row.append(copy, select);
    return { row, select };
  }

  private settingsAssistantGroup(): HTMLElement {
    const group = this.settingsGroup("助理設定", "LAUNCHER OWNED");
    if (!this.profile.ok) {
      const empty = createElement("div", "empty-state");
      empty.innerHTML = `<div><strong>Launcher control 尚未連線</strong><span>${text(this.profile.error, "重新啟動 Kuro 後即可在這裡切換角色與模型。")}</span></div>`;
      group.appendChild(empty);
      return group;
    }
    const selected = this.pendingProfileSelection || this.profile.selected || {};
    const characters = this.settingsSelectRow(
      "角色",
      "切換人物、聲音、Live2D 與角色語氣；共享工作狀態不會分裂。",
      this.profile.characters || [],
      text(selected.character_id)
    );
    const projects = this.settingsSelectRow(
      "目前專案",
      "決定工作 prompt 與工具使用脈絡。",
      this.profile.projects || [],
      text(selected.project_id)
    );
    const models = this.settingsSelectRow(
      "LLM 模型",
      "只列出 kuro_launcher.settings.yaml 明確允許的本機模型。",
      (this.profile.models || []).map((id) => ({ id, name: id })),
      text(selected.model)
    );
    const thinkingLabels = { fast: "快速", normal: "普通", deep: "深度" };
    const thinking = this.settingsSelectRow(
      "推理深度",
      "快速適合一般互動；深度會增加搜尋與推理預算。",
      (this.profile.thinking_options || ["fast", "normal", "deep"]).map((id) => ({ id })),
      text(selected.thinking_power, "normal"),
      thinkingLabels
    );
    group.append(characters.row, projects.row, models.row, thinking.row);
    const actions = createElement("div", "settings-actions");
    const apply = button("primary-button", this.profileApplying ? "正在套用…" : "套用助理設定", () => this.applyProfilePatch({
      character_id: characters.select.value,
      project_id: projects.select.value,
      model: models.select.value,
      thinking_power: thinking.select.value
    }));
    apply.disabled = this.profileApplying;
    actions.appendChild(apply);
    group.appendChild(actions);
    group.appendChild(createElement("p", "settings-note", "套用時可能重新載入 TTS 與 conversation runtime；Electron 會先顯示原生確認視窗。"));
    return group;
  }

  private settingsConversationGroup(): HTMLElement {
    const group = this.settingsGroup("對話保存", "LOCAL AUTOMATIC");
    const histories = Array.isArray(this.history.histories) ? this.history.histories : [];
    const list = createElement("dl", "diagnostic-list");
    const rows: Array<[string, string]> = [
      ["保存方式", "每則訊息自動保存到本機"],
      ["目前對話", text(this.chat.currentHistoryTitle ?? this.history.title, "尚未命名")],
      ["對話數量", this.history.ok ? `${histories.length} 段` : "Launcher control 未連線"]
    ];
    rows.forEach(([key, value]) => {
      const row = createElement("div", "diagnostic-row");
      row.append(createElement("dt", "", key), createElement("dd", "", value));
      list.appendChild(row);
    });
    group.appendChild(list);
    const actions = createElement("div", "settings-actions");
    actions.appendChild(button("quiet-button", "開啟對話紀錄", async () => {
      this.setMode("chat");
      await this.refreshHistory();
      this.setHistoryOpen(true);
    }));
    actions.appendChild(button("quiet-button", "建立新對話", () => this.createNewHistory()));
    group.appendChild(actions);
    return group;
  }

  private settingsMemoryGroup(): HTMLElement {
    const records = Array.isArray(this.memories.memories) ? this.memories.memories : [];
    const pendingCount = records.filter((item) => item.status === "pending_confirmation").length;
    const group = this.settingsGroup(
      "長期記憶",
      this.memories.ok ? `${records.length} ITEMS · ${pendingCount} PENDING` : "UNAVAILABLE"
    );
    if (!this.memories.ok) {
      const empty = createElement("div", "empty-state");
      empty.innerHTML = `<div><strong>記憶服務尚未連線</strong><span>${text(this.memories.error, "Launcher control API 暫時無法使用。")}</span></div>`;
      group.appendChild(empty);
      return group;
    }
    const addBox = createElement("div", "memory-add");
    const input = createElement("textarea", "memory-input") as HTMLTextAreaElement;
    input.rows = 2;
    input.maxLength = 1200;
    input.placeholder = "輸入要加入目前角色的長期記憶…";
    const add = button("primary-button", "新增記憶", () => this.addMemoryFromSettings(input));
    addBox.append(input, add);
    group.appendChild(addBox);

    const list = createElement("div", "memory-list");
    if (!records.length) {
      const empty = createElement("div", "history-empty");
      empty.append(createElement("strong", "", "目前沒有長期記憶"), createElement("span", "", "新增後會保留來源、狀態與更新時間。"));
      list.appendChild(empty);
    } else {
      records.slice(0, 80).forEach((record) => list.appendChild(this.memoryRow(record)));
    }
    group.appendChild(list);
    if (records.length) {
      const actions = createElement("div", "settings-actions");
      actions.appendChild(button("quiet-button", "整理記憶", () => this.runMemoryAction("compact", {})));
      group.appendChild(actions);
    }
    return group;
  }

  private memoryRow(record: MemoryEntry): HTMLElement {
    const row = createElement("article", "memory-row");
    const top = createElement("div", "memory-row-top");
    top.appendChild(createElement("span", `status-pill tone-${record.status === "active" ? "good" : record.status === "pending_confirmation" ? "warn" : "quiet"}`, text(record.status, "unknown")));
    top.appendChild(createElement("span", "memory-meta", `${text(record.memory_type, "fact")} · ${text(record.scope, "character")}`));
    row.append(top, createElement("div", "memory-content", record.content));
    const actions = createElement("div", "memory-actions");
    if (record.status === "pending_confirmation") {
      actions.appendChild(button("text-button", "核准", () => this.runMemoryAction("status", { entry_id: record.id, status: "active" })));
      actions.appendChild(button("text-button", "拒絕", () => this.runMemoryAction("status", { entry_id: record.id, status: "disabled" })));
    } else {
      actions.appendChild(button("text-button", record.status === "active" ? "停用" : "啟用", () => this.runMemoryAction("status", {
        entry_id: record.id,
        status: record.status === "active" ? "disabled" : "active"
      })));
    }
    actions.appendChild(button("text-button is-danger", "刪除", () => this.runMemoryAction("delete", { entry_id: record.id })));
    row.appendChild(actions);
    return row;
  }

  private async addMemoryFromSettings(input: HTMLTextAreaElement): Promise<void> {
    const content = input.value.trim();
    if (!content) {
      this.showToast("記憶內容不可空白。", true);
      return;
    }
    await this.runMemoryAction("add", { content });
  }

  private async runMemoryAction(action: string, payload: Record<string, unknown>): Promise<void> {
    const result = await bridge.memoryAction(action, payload);
    if (result?.cancelled) return;
    if (!result?.ok) {
      this.showToast(text(result?.error, "記憶操作失敗。"), true);
      return;
    }
    this.memories = result;
    this.showToast(result.changed === false ? "記憶沒有變更；內容可能重複或已是目前狀態。" : "記憶已更新。");
    if (this.mode === "settings") this.renderSettings();
  }

  private settingsPerceptionGroup(): HTMLElement {
    const group = this.settingsGroup("語音與感知", "VISIBLE WHILE ACTIVE");
    group.appendChild(this.settingsMicrophoneRow());
    group.appendChild(this.settingToggle(
      "鏡頭",
      "啟用後，下一個對話回合可附上鏡頭畫面。",
      this.sensorEnabled("camera"),
      () => this.toggleSensor("camera")
    ));
    group.appendChild(this.settingToggle(
      "本回合螢幕擷取",
      "以低幀率擷取螢幕，供你下一次送出的訊息使用；不是背景持續監控。",
      this.sensorEnabled("screen"),
      () => this.toggleSensor("screen")
    ));
    group.appendChild(createElement("p", "settings-note", "任何感知功能開啟時，視窗頂部都會持續顯示狀態；Windows 權限失敗會直接回報。"));
    return group;
  }

  private settingsMicrophoneRow(): HTMLElement {
    const enabled = this.sensorEnabled("microphone");
    const paused = this.microphonePaused();
    const row = createElement("div", "setting-row microphone-setting-row");
    const copy = createElement("div", "setting-copy");
    copy.appendChild(createElement("strong", "", "麥克風"));
    copy.appendChild(createElement(
      "span",
      "",
      enabled
        ? paused
          ? "錄音已暫停，內容保留在本機且尚未送出。"
          : "正在錄音；可暫停、完成送出或取消。"
        : "錄音不會在關閉時自動送出；只有按下「完成並送出」才會建立對話回合。"
    ));
    const actions = createElement("div", "microphone-setting-actions");
    if (!enabled) {
      actions.appendChild(button("quiet-button", "開始錄音", () => { void this.runMicrophoneAction("start"); }));
    } else {
      actions.appendChild(button("quiet-button", paused ? "繼續" : "暫停", () => {
        void this.runMicrophoneAction(paused ? "resume" : "pause");
      }));
      actions.appendChild(button("primary-button", "完成並送出", () => { void this.runMicrophoneAction("submit"); }));
      actions.appendChild(button("text-button is-danger", "取消", () => { void this.runMicrophoneAction("cancel"); }));
    }
    actions.querySelectorAll<HTMLButtonElement>("button").forEach((element) => {
      element.disabled = Boolean(this.sensorPending);
    });
    row.append(copy, actions);
    return row;
  }

  private settingsToolsGroup(): HTMLElement {
    const records = Array.isArray(this.tools.tools) ? this.tools.tools : [];
    const group = this.settingsGroup("工具與權限", this.tools.ok ? `${records.length} REGISTERED` : "UNAVAILABLE");
    if (!this.tools.ok) {
      const empty = createElement("div", "empty-state");
      empty.innerHTML = `<div><strong>工具政策尚未載入</strong><span>${text(this.tools.error, "Launcher control API 暫時無法使用。")}</span></div>`;
      group.appendChild(empty);
      return group;
    }
    const summary = createElement("div", "tool-policy-summary");
    summary.appendChild(createElement("strong", "", `預設模式：${text(this.tools.default_mode, "blocked")}`));
    summary.appendChild(createElement("span", "", this.tools.confirmation_available
      ? "逐次確認流程可用。"
      : "逐次工具確認流程尚未完成；需要確認的工具目前會保持封鎖。"));
    group.appendChild(summary);
    const list = createElement("div", "tool-list");
    records.forEach((tool) => {
      const row = createElement("div", "tool-row");
      const copy = createElement("div", "tool-copy");
      copy.append(createElement("strong", "", tool.name), createElement("span", "", `${text(tool.category, "other")} · ${text(tool.reason)}`));
      row.append(copy, createElement("span", `status-pill tone-${tool.allowed ? "good" : "bad"}`, text(tool.mode, "blocked")));
      list.appendChild(row);
    });
    group.appendChild(list);
    group.appendChild(createElement("p", "settings-note", "此頁只呈現 runtime policy 的真實狀態，不提供會繞過確認流程的全域開關。"));
    return group;
  }

  private settingsGroup(title: string, meta: string): HTMLElement {
    const group = createElement("section", "settings-group");
    const header = createElement("div", "settings-group-header");
    header.appendChild(createElement("h2", "", title));
    header.appendChild(createElement("span", "", meta));
    group.appendChild(header);
    return group;
  }

  private settingToggle(
    title: string,
    description: string,
    enabled: boolean,
    onToggle: () => void
  ): HTMLElement {
    const row = createElement("div", "setting-row");
    const copy = createElement("div", "setting-copy");
    copy.appendChild(createElement("strong", "", title));
    copy.appendChild(createElement("span", "", description));
    const toggle = button(`switch${enabled ? " is-on" : ""}`, "", onToggle);
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-checked", String(enabled));
    toggle.setAttribute("aria-label", title);
    row.append(copy, toggle);
    return row;
  }

  private settingsExperienceGroup(): HTMLElement {
    const group = this.settingsGroup("工作面板", "THIS DEVICE");
    group.appendChild(this.settingToggle(
      "緊湊顯示",
      "縮短列表與對話的垂直間距，資料內容不變。",
      this.compact,
      () => {
        this.compact = !this.compact;
        window.localStorage.setItem("kuro.work-panel.compact", String(this.compact));
        this.applyPreferences();
        this.renderSettings();
      }
    ));
    group.appendChild(this.settingToggle(
      "降低動態效果",
      "停用詳情滑入與處理中動畫。系統的 reduced motion 設定仍會優先。",
      this.reduceMotion,
      () => {
        this.reduceMotion = !this.reduceMotion;
        window.localStorage.setItem("kuro.work-panel.reduce-motion", String(this.reduceMotion));
        this.applyPreferences();
        this.renderSettings();
      }
    ));
    return group;
  }

  private settingsPetGroup(): HTMLElement {
    const group = this.settingsGroup("桌寵", "SAFE CONTROLS");
    const outfit = this.settingsSelectRow(
      "服裝",
      "切換目前桌寵模型支援的服裝參數。",
      this.profile.outfits || [{ id: "normal", label: "一般" }, { id: "hoodie", label: "帽T" }],
      text(this.runtime.currentOutfitId, "normal")
    );
    const expression = this.settingsSelectRow(
      "表情",
      "套用既有表情 preset，不改動角色人格或工具權限。",
      this.profile.expressions || [{ id: "neutral", label: "一般", parameters: {} }],
      text(this.runtime.currentExpressionId, "neutral")
    );
    group.append(outfit.row, expression.row);
    const appearanceActions = createElement("div", "settings-actions");
    appearanceActions.appendChild(button("quiet-button", "套用服裝", () => this.applyOutfit(outfit.select.value)));
    appearanceActions.appendChild(button("quiet-button", "套用表情", () => this.applyExpression(expression.select.value)));
    appearanceActions.appendChild(button("quiet-button", "播放待機動作", () => this.runControl("play-motion", "已播放桌寵動作。", { group: "Idle" })));
    group.appendChild(appearanceActions);
    group.appendChild(this.settingToggle(
      "滑鼠穿透",
      "開啟後整個桌寵層完全穿透；關閉後只有角色本體可操作，透明區域仍會穿透。",
      Boolean(this.runtime.forceIgnoreMouse),
      () => this.setPetBoolean("set-force-ignore-mouse", "forceIgnoreMouse", !Boolean(this.runtime.forceIgnoreMouse))
    ));
    group.appendChild(this.settingToggle(
      "遊戲模式",
      "套用既有桌寵遊戲模式的 focus 與滑鼠行為。",
      Boolean(this.runtime.petGameMode),
      () => this.setPetBoolean("set-game-mode", "petGameMode", !Boolean(this.runtime.petGameMode))
    ));
    const actions = createElement("div", "settings-actions");
    actions.appendChild(button("quiet-button", "顯示桌寵", () => this.runControl("show-pet", "已顯示桌寵。")));
    actions.appendChild(button("quiet-button", "移到下一個螢幕", () => this.runControl("move-next-display", "已移動桌寵。")));
    actions.appendChild(button("quiet-button", "重置桌寵位置", () => this.runControl("reset-pet-position", "已重置桌寵位置。")));
    group.appendChild(actions);
    return group;
  }

  private async applyOutfit(outfitId: string): Promise<void> {
    const hoodie = outfitId === "hoodie";
    const result = await bridge.control("set-outfit", {
      outfitId: hoodie ? "hoodie" : "normal",
      parameterId: "Param10",
      value: hoodie ? 1 : 0
    });
    if (!result?.ok) {
      this.showToast(text(result?.error, "服裝套用失敗。"), true);
      return;
    }
    this.runtime.currentOutfitId = hoodie ? "hoodie" : "normal";
    this.showToast("服裝已套用。");
    this.renderSettings();
  }

  private async applyExpression(expressionId: string): Promise<void> {
    const preset = (this.profile.expressions || []).find((item) => item.id === expressionId);
    if (!preset) {
      this.showToast("找不到這個表情 preset。", true);
      return;
    }
    const result = await bridge.control("set-expression", {
      expressionId: preset.id,
      expressionLabel: text(preset.label ?? preset.name, preset.id),
      parameters: preset.parameters || {}
    });
    if (!result?.ok) {
      this.showToast(text(result?.error, "表情套用失敗。"), true);
      return;
    }
    this.runtime.currentExpressionId = preset.id;
    this.runtime.currentExpressionLabel = text(preset.label ?? preset.name, preset.id);
    this.showToast("表情已套用。");
    this.renderSettings();
  }

  private settingsRuntimeGroup(): HTMLElement {
    const group = this.settingsGroup("目前 Runtime", "READ ONLY");
    const list = createElement("dl", "diagnostic-list");
    const rows: Array<[string, string]> = [
      ["Connection", this.runtime.wsConnected ? "connected" : "offline"],
      ["AI state", text(this.runtime.aiState, "unknown")],
      ["Character", text(this.runtime.confName, "unknown")],
      ["Conversation", text(this.runtime.currentHistoryTitle ?? this.runtime.currentHistoryUid, "not selected")],
      ["Outfit", text(this.runtime.currentOutfitId, "unknown")],
      ["Expression", text(this.runtime.currentExpressionLabel, "unknown")]
    ];
    rows.forEach(([key, value]) => {
      const row = createElement("div", "diagnostic-row");
      row.appendChild(createElement("dt", "", key));
      row.appendChild(createElement("dd", "", value));
      list.appendChild(row);
    });
    group.appendChild(list);
    const actions = createElement("div", "settings-actions");
    actions.appendChild(button("quiet-button is-danger", "停止目前輸出", () => this.stopOutput()));
    group.appendChild(actions);
    return group;
  }

  private settingsSourceGroup(): HTMLElement {
    const group = this.settingsGroup("資料來源", "STATUS ONLY");
    const statuses = Array.isArray(this.data.snapshot?.sourceStatus) ? this.data.snapshot?.sourceStatus || [] : [];
    if (!statuses.length) {
      const empty = createElement("div", "empty-state");
      empty.innerHTML = `<div><strong>尚未收到來源狀態</strong><span>這不會被解讀為資料正常或已完成。</span></div>`;
      group.appendChild(empty);
      return group;
    }
    const list = createElement("dl", "diagnostic-list");
    statuses.forEach((status) => {
      const row = createElement("div", "diagnostic-row");
      row.appendChild(createElement("dt", "", text(status.label, sourceLabel(status.id))));
      row.appendChild(createElement("dd", "", `${statusLabel(status.status)} · ${formatDateLabel(status.updatedAt, true) || "時間未知"}`));
      list.appendChild(row);
    });
    group.appendChild(list);
    return group;
  }

  private async setPetBoolean(action: string, key: "forceIgnoreMouse" | "petGameMode", enabled: boolean): Promise<void> {
    const result = await bridge.control(action, { enabled });
    if (result?.ok) {
      this.runtime = { ...this.runtime, [key]: enabled };
      this.showToast("桌寵設定已更新。", false);
      this.renderSettings();
    } else {
      this.showToast(text(result?.error, "桌寵設定更新失敗。"), true);
    }
  }

  private async runControl(action: string, successMessage: string, payload: Record<string, unknown> = {}): Promise<void> {
    const result = await bridge.control(action, payload);
    this.showToast(result?.ok ? successMessage : text(result?.error, "操作失敗。"), !result?.ok);
  }

  private applyPreferences(): void {
    document.body.classList.toggle("is-compact", this.compact);
    document.body.classList.toggle("reduce-motion", this.reduceMotion);
  }

  private hideToast(): void {
    const toast = appRoot.querySelector<HTMLElement>("[data-toast]");
    if (!toast) return;
    if (this.toastTimer) window.clearTimeout(this.toastTimer);
    this.toastTimer = 0;
    toast.classList.remove("is-visible", "is-error");
  }

  private showToast(message: string, error = false, durationMs: number | null = 2600): void {
    const toast = appRoot.querySelector<HTMLElement>("[data-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("is-error", error);
    toast.classList.add("is-visible");
    if (this.toastTimer) window.clearTimeout(this.toastTimer);
    this.toastTimer = 0;
    if (durationMs !== null && durationMs > 0) {
      this.toastTimer = window.setTimeout(() => {
        toast.classList.remove("is-visible");
        this.toastTimer = 0;
      }, durationMs);
    }
  }
}

new KuroWorkPanel();
