// Original renderer uses five presentation preferences. Keep only bounded,
// process-local values; native Web Storage remains disabled by the Qt host.
const allowed: Record<string, ReadonlySet<string>> = {
  "kuro.work-panel.mode": new Set(["chat", "today", "settings"]),
  "kuro.work-panel.source": new Set(["all", "study", "mail", "stocks", "news", "messages", "notes"]),
  "kuro.work-panel.settings-section": new Set(["assistant", "conversation", "perception", "tools", "pet", "diagnostics"]),
  "kuro.work-panel.compact": new Set(["true", "false"]),
  "kuro.work-panel.reduce-motion": new Set(["true", "false"]),
};

export function presentationPreferences(): Storage {
  const values = new Map<string, string>();
  return Object.freeze({
    get length() { return values.size; },
    key(index: number) { return [...values.keys()][index] ?? null; },
    getItem(key: string) { return values.get(String(key)) ?? null; },
    setItem(key: string, value: string) {
      if (!Object.prototype.hasOwnProperty.call(allowed, key) || !allowed[key].has(value)) throw new DOMException("Presentation preference denied", "SecurityError");
      values.set(key, value);
    },
    removeItem(key: string) { values.delete(key); },
    clear() { values.clear(); },
  });
}

export function installPresentationPreferences(target: Window): void {
  Object.defineProperty(target, "localStorage", {value: presentationPreferences(), writable: false, configurable: false});
  for (const key of ["sessionStorage", "indexedDB", "caches"]) {
    Object.defineProperty(target, key, {configurable: false, get() {
      throw new DOMException("Web storage unavailable", "SecurityError");
    }});
  }
}
