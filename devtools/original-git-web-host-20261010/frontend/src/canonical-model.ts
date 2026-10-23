// Candidate-only import boundary. The archived Git model remains byte-identical.
export * from "./work-panel/model";
import { normalizeViewItem, sourceLabel as originalSourceLabel, statusLabel as originalStatusLabel } from "./work-panel/model";
import type { BriefingData, ViewItem } from "./work-panel/types";

export const SOURCE_ORDER = ["all", "calendar", "japanese_study", "english_study", "mail", "omi"];
export function sourceLabel(source: unknown): string {
  return ({japanese_study:"日文學習", english_study:"英文學習", mail:"Gmail 郵件", omi:"市場觀測"} as Record<string,string>)[String(source)] || originalSourceLabel(source);
}
export function statusLabel(status: unknown): string {
  return ({auth_required:"需要授權", disconnected:"未連線", available:"資料可用", unavailable:"尚不可用", disabled:"已停用"} as Record<string,string>)[String(status)] || originalStatusLabel(status);
}

export function todayItems(data: BriefingData): ViewItem[] {
  const items = data.snapshot?.today?.items;
  if (!Array.isArray(items)) return [];
  return items.map((item, index) => {
    const view = normalizeViewItem(item, "today", index);
    if (!view) throw new Error("Canonical Core item cannot be displayed");
    // Keep canonical raw reasons in evidence; primary copy is human-readable.
    return {...view, meta: "來源提供的工作；資料品質與限制請見來源狀態。"};
  });
}

export function priorityItems(data: BriefingData): ViewItem[] {
  // Presentation truncation only: no filtering, deduplication, rank or severity rewrite.
  return todayItems(data).slice(0, 5);
}

export function sourceItems(data: BriefingData, source: string): ViewItem[] {
  return todayItems(data).filter(item => source === "all" || item.source === source);
}

export function sourceCount(data: BriefingData, source: string): number {
  return sourceItems(data, source).length;
}
