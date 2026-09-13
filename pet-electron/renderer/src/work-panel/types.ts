export type WorkMode = "chat" | "today" | "settings";

export interface AttachmentPayload {
  kind: string;
  name: string;
  size: number;
  mime_type: string;
  data: string;
}

export interface ChatState {
  ok?: boolean;
  aiState?: string;
  wsConnected?: boolean;
  latestAssistantText?: string;
  latestUserText?: string;
  wsUrl?: string;
  baseUrl?: string;
  confName?: string;
  confUid?: string;
  currentHistoryUid?: string;
  currentHistoryTitle?: string;
  micEnabled?: boolean;
  micPaused?: boolean;
  cameraEnabled?: boolean;
  screenEnabled?: boolean;
  browserPanelEnabled?: boolean;
}

export interface HistoryMessage {
  role: string;
  timestamp?: string;
  content: string;
}

export interface ChatHistoryPayload {
  ok?: boolean;
  cancelled?: boolean;
  error?: string;
  confUid?: string;
  historyUid?: string;
  title?: string;
  messages?: HistoryMessage[];
  current_history_uid?: string;
  selected_history_uid?: string;
  histories?: HistorySummary[];
}

export interface HistorySummary {
  uid: string;
  title: string;
  preview?: string;
  timestamp?: string;
  is_empty?: boolean;
}

export interface SelectOption {
  id: string;
  name?: string;
  label?: string;
  model?: string;
  default_project_id?: string;
  parameters?: Record<string, number>;
}

export interface ProfileState {
  ok?: boolean;
  error?: string;
  characters?: SelectOption[];
  projects?: SelectOption[];
  models?: string[];
  thinking_options?: string[];
  expressions?: SelectOption[];
  outfits?: SelectOption[];
  selected?: {
    character_id?: string;
    project_id?: string;
    model?: string;
    thinking_power?: string;
  };
}

export interface MemoryEntry {
  id: string;
  content: string;
  memory_type?: string;
  enabled?: boolean;
  status?: string;
  scope?: string;
  source?: string;
  updated_at?: string;
  content_digest?: string;
}

export interface MemoryState {
  ok?: boolean;
  cancelled?: boolean;
  error?: string;
  changed?: boolean;
  character_id?: string;
  character_name?: string;
  memories?: MemoryEntry[];
}

export interface ToolPolicyEntry {
  name: string;
  category?: string;
  mode?: string;
  allowed?: boolean;
  reason?: string;
}

export interface ToolPolicyState {
  ok?: boolean;
  error?: string;
  version?: number;
  default_mode?: string;
  confirmation_available?: boolean;
  categories?: Array<{ id: string; title?: string; description?: string }>;
  tools?: ToolPolicyEntry[];
}

export interface RuntimeState {
  speechStatus?: string;
  capabilities?: {
    launcher: { contractVersion: number; phase: string; reason: string; restartRequired: boolean;
      sourceRevision: string; desiredRunning: boolean; recoveryExhausted: boolean;
      voice: { state: string; reason: string } } | null;
    pet: { state: string; modelReady?: boolean; visible?: boolean; responsive?: boolean };
  };
  ok?: boolean;
  aiState?: string;
  wsConnected?: boolean;
  confName?: string;
  confUid?: string;
  currentHistoryUid?: string;
  currentHistoryTitle?: string;
  latestAssistantText?: string;
  forceIgnoreMouse?: boolean;
  petGameMode?: boolean;
  currentOutfitId?: string;
  currentExpressionId?: string;
  currentExpressionLabel?: string;
  micEnabled?: boolean;
  micPaused?: boolean;
  cameraEnabled?: boolean;
  screenEnabled?: boolean;
  browserPanelEnabled?: boolean;
  briefingVisible?: boolean;
  briefingDate?: string;
  briefingUpdatedAt?: string;
  mailBriefing?: Record<string, unknown> | null;
  pendingMemoryCount?: number;
  updatedAt?: string;
}

export interface SourceStatus {
  id?: string;
  label?: string;
  status?: string;
  updatedAt?: string;
  message?: string;
}

export interface BriefingItem {
  id?: string;
  refId?: string;
  text?: string;
  title?: string;
  label?: string;
  meta?: string;
  status?: string;
  time?: string;
  date?: string;
  dueAt?: string;
  remindAt?: string;
  source?: string;
  kind?: string;
  level?: string;
  priority?: string;
  score?: number;
  evidence?: string;
  summary?: string;
  description?: string;
  subject?: string;
  from?: string;
  senderEmail?: string;
  snippet?: string;
  priorityLevel?: string;
}

export interface BriefingModule {
  id?: string;
  title?: string;
  tag?: string;
  value?: string;
  unit?: string;
  wide?: boolean;
  items?: BriefingItem[];
}

export interface BriefingSection {
  key?: string;
  label?: string;
  icon?: string;
  count?: number;
  subtitle?: string;
  modules?: BriefingModule[];
}

export interface TodaySnapshot {
  updatedAt?: string;
  levels?: Record<string, BriefingItem[]>;
  counts?: Record<string, number>;
  items?: BriefingItem[];
}

export interface MailSnapshot {
  messages?: BriefingItem[];
  [key: string]: unknown;
}

export interface BriefingSnapshot {
  date?: string;
  title?: string;
  updatedAt?: string;
  sections?: BriefingSection[];
  sourceStatus?: SourceStatus[];
  mail?: MailSnapshot | null;
  study?: Record<string, unknown> | null;
  today?: TodaySnapshot;
}

export interface BriefingData {
  ok?: boolean;
  error?: string;
  updatedAt?: string;
  snapshot?: BriefingSnapshot;
  memoryCandidates?: Array<Record<string, unknown>>;
}

export interface ViewItem {
  id: string;
  refId: string;
  source: string;
  kind: string;
  level: string;
  title: string;
  meta: string;
  date: string;
  evidence: string;
  raw: BriefingItem;
}

export interface WorkPanelBridge {
  schedule(action: "status" | "view" | "item" | "mutate" | "materialize" | "prepare" | "notifications" | "notification-action", payload?: Record<string, unknown>): Promise<Record<string, unknown> & { ok: boolean; error?: string }>;
  getState(): Promise<RuntimeState>;
  getData(): Promise<BriefingData>;
  getChatState(): Promise<ChatState>;
  getChatHistory(): Promise<ChatHistoryPayload>;
  getProfile(): Promise<ProfileState>;
  applyProfile(payload: Record<string, unknown>): Promise<Record<string, unknown>>;
  getHistories(historyUid?: string): Promise<ChatHistoryPayload>;
  createHistory(): Promise<ChatHistoryPayload>;
  selectHistory(historyUid: string): Promise<ChatHistoryPayload>;
  deleteHistory(historyUid: string, historyTitle?: string): Promise<ChatHistoryPayload>;
  getMemories(): Promise<MemoryState>;
  memoryAction(action: string, payload?: Record<string, unknown>): Promise<MemoryState & Record<string, unknown>>;
  getTools(): Promise<ToolPolicyState>;
  sendText(text: string, attachments: AttachmentPayload[]): Promise<Record<string, unknown>>;
  refreshMail(): Promise<Record<string, unknown>>;
  getMailMessage(messageId: string): Promise<Record<string, unknown>>;
  control(action: string, payload?: Record<string, unknown>): Promise<Record<string, unknown>>;
  closeWindow(): void;
  minimizeWindow(): void;
  toggleMaximizeWindow(): void;
  onState(callback: (state: RuntimeState) => void): () => void;
  onData(callback: (data: BriefingData) => void): () => void;
  onChatState(callback: (state: ChatState) => void): () => void;
}

declare global {
  interface Window {
    kuroWorkPanel: WorkPanelBridge;
  }
}
