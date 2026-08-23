import type {
  BriefingData,
  BriefingItem,
  BriefingSection,
  SourceStatus,
  ViewItem
} from "./types";

export const SOURCE_ORDER = [
  "all",
  "calendar",
  "study",
  "mail",
  "stocks",
  "news",
  "messages",
  "notes"
];

const SOURCE_LABELS: Record<string, string> = {
  all: "全部",
  today: "今天",
  calendar: "行事曆",
  study: "學習計畫",
  mail: "Mail",
  stocks: "市場",
  market: "市場",
  news: "新聞",
  messages: "訊息",
  notes: "筆記",
  memory: "記憶",
  system: "系統",
  tasks: "待處理"
};

const LEVEL_LABELS: Record<string, string> = {
  urgent: "立即",
  must: "必做",
  focus: "重點",
  watch: "留意",
  normal: "一般"
};

const STATUS_LABELS: Record<string, string> = {
  current: "最新",
  connected: "已連線",
  ready: "可用",
  healthy: "正常",
  ok: "正常",
  stale: "稍舊",
  partial: "部分資料",
  missing: "缺少資料",
  offline: "離線",
  auth: "需要登入",
  error: "異常",
  unknown: "未知"
};

export function text(value: unknown, fallback = ""): string {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

export function sourceLabel(source: unknown): string {
  const key = text(source, "today").toLowerCase();
  return SOURCE_LABELS[key] || text(source, "來源");
}

export function levelLabel(level: unknown): string {
  const key = text(level, "normal").toLowerCase();
  return LEVEL_LABELS[key] || text(level, "一般");
}

export function statusLabel(status: unknown): string {
  const key = text(status, "unknown").toLowerCase();
  return STATUS_LABELS[key] || text(status, "未知");
}

export function statusTone(status: unknown): string {
  const key = text(status, "unknown").toLowerCase();
  if (["current", "connected", "ready", "healthy", "ok"].includes(key)) return "good";
  if (["stale", "partial", "warning"].includes(key)) return "warn";
  if (["missing", "offline", "auth", "error", "failed"].includes(key)) return "bad";
  return "quiet";
}

export function formatDateLabel(value: unknown, includeTime = false): string {
  const raw = text(value);
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat("zh-TW", {
    month: "short",
    day: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {})
  }).format(date);
}

export function formatFullDate(date = new Date()): string {
  return new Intl.DateTimeFormat("zh-TW", {
    month: "long",
    day: "numeric",
    weekday: "long"
  }).format(date);
}

export function normalizeViewItem(
  candidate: BriefingItem,
  fallbackSource: string,
  index: number
): ViewItem | null {
  const source = text(candidate.source, fallbackSource).toLowerCase();
  const title = text(candidate.text ?? candidate.title ?? candidate.label ?? candidate.subject);
  if (!title) return null;
  const id = text(candidate.id, `${source}:${index}:${title}`);
  const level = text(candidate.level ?? candidate.priority ?? candidate.priorityLevel, "normal").toLowerCase();
  return {
    id,
    refId: text(candidate.refId ?? candidate.id),
    source,
    kind: text(candidate.kind, source).toLowerCase(),
    level,
    title,
    meta: text(candidate.meta ?? candidate.status ?? candidate.time ?? candidate.from ?? candidate.senderEmail),
    date: text(candidate.date ?? candidate.dueAt ?? candidate.remindAt),
    evidence: text(candidate.evidence ?? candidate.summary ?? candidate.description ?? candidate.snippet),
    raw: candidate
  };
}

function sectionItems(section: BriefingSection): ViewItem[] {
  const source = text(section.key, "today").toLowerCase();
  const output: ViewItem[] = [];
  for (const module of Array.isArray(section.modules) ? section.modules : []) {
    const moduleTitle = text(module.title);
    const items = Array.isArray(module.items) ? module.items : [];
    items.forEach((item, index) => {
      const normalized = normalizeViewItem(item, source, output.length + index);
      if (!normalized) return;
      if (!normalized.meta && moduleTitle) normalized.meta = moduleTitle;
      output.push(normalized);
    });
  }
  return output;
}

function uniqueItems(items: ViewItem[]): ViewItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.source}:${item.refId || item.id}:${item.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function todayItems(data: BriefingData): ViewItem[] {
  const rawItems = data.snapshot?.today?.items;
  if (!Array.isArray(rawItems)) return [];
  return uniqueItems(
    rawItems
      .map((item, index) => normalizeViewItem(item, "today", index))
      .filter((item): item is ViewItem => Boolean(item))
  );
}

export function sourceItems(data: BriefingData, source: string): ViewItem[] {
  const normalizedSource = text(source, "all").toLowerCase();
  const sections = Array.isArray(data.snapshot?.sections) ? data.snapshot?.sections || [] : [];
  const ignoredSections = new Set(["overview", "tasks"]);
  const collected = sections
    .filter((section) => !ignoredSections.has(text(section.key).toLowerCase()))
    .filter((section) => normalizedSource === "all" || text(section.key).toLowerCase() === normalizedSource)
    .flatMap(sectionItems);

  const today = todayItems(data).filter((item) => normalizedSource === "all" || item.source === normalizedSource);
  const mailMessages = normalizedSource === "all" || normalizedSource === "mail"
    ? (Array.isArray(data.snapshot?.mail?.messages) ? data.snapshot?.mail?.messages || [] : [])
        .map((item, index) => normalizeViewItem(item, "mail", index))
        .filter((item): item is ViewItem => Boolean(item))
    : [];
  return uniqueItems([...today, ...mailMessages, ...collected]);
}

export function scheduleItems(data: BriefingData): ViewItem[] {
  return sourceItems(data, "calendar")
    .filter((item) => item.date || item.meta)
    .sort((left, right) => String(left.date).localeCompare(String(right.date)));
}

export function priorityItems(data: BriefingData): ViewItem[] {
  const rank: Record<string, number> = { urgent: 0, must: 1, focus: 2, watch: 3, normal: 4 };
  return todayItems(data)
    .filter((item) => item.level !== "normal")
    .sort((left, right) => (rank[left.level] ?? 9) - (rank[right.level] ?? 9))
    .slice(0, 5);
}

export function sourceCount(data: BriefingData, source: string): number {
  if (source === "all") return sourceItems(data, "all").length;
  const section = data.snapshot?.sections?.find((item) => text(item.key).toLowerCase() === source);
  const declared = Number(section?.count);
  if (Number.isFinite(declared) && declared > 0) return Math.round(declared);
  return sourceItems(data, source).length;
}

export function sourceStatus(data: BriefingData, source: string): SourceStatus | null {
  const statuses = Array.isArray(data.snapshot?.sourceStatus) ? data.snapshot?.sourceStatus || [] : [];
  return statuses.find((item) => text(item.id).toLowerCase() === source) || null;
}
