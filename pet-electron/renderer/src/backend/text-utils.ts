import type { UserAttachmentPayload } from "./types";

export function normalizeText(value: unknown): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

export function buildVisibleInputText(text: string, attachments: UserAttachmentPayload[] = []): string {
  const attachmentNames = (Array.isArray(attachments) ? attachments : [])
    .map((item, index) => String(item?.name || `file-${index + 1}`).trim())
    .filter(Boolean);
  if (!attachmentNames.length) {
    return text;
  }

  return [text, `附件：${attachmentNames.join("、")}`].filter(Boolean).join("\n");
}

export function mergeTextFragments(parts: string[]): string {
  let merged = "";
  for (const part of parts) {
    if (!part) {
      continue;
    }
    if (!merged) {
      merged = part;
      continue;
    }
    const needsSpace = /[A-Za-z0-9]$/.test(merged) && /^[A-Za-z0-9]/.test(part);
    merged += needsSpace ? ` ${part}` : part;
  }
  return merged;
}

export function buildAbsoluteModelUrl(baseUrl: string, relativeOrAbsoluteUrl: string): string {
  try {
    return new URL(relativeOrAbsoluteUrl, baseUrl).toString();
  } catch {
    return relativeOrAbsoluteUrl;
  }
}
