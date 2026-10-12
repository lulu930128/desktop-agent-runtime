// Candidate-only import boundary. The archived Git model remains byte-identical.
export * from "./work-panel/model";
import { normalizeViewItem } from "./work-panel/model";
import type { BriefingData, ViewItem } from "./work-panel/types";

export function todayItems(data: BriefingData): ViewItem[] {
  const items = data.snapshot?.today?.items;
  if (!Array.isArray(items)) return [];
  return items.map((item, index) => {
    const view = normalizeViewItem(item, "today", index);
    if (!view) throw new Error("Canonical Core item cannot be displayed");
    return view;
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
