const MODEL_ZOOM_STORAGE_KEY = "kuroPetModelZoomScale";

export function loadStoredModelZoomScale(): number {
  try {
    const raw = window.localStorage.getItem(MODEL_ZOOM_STORAGE_KEY);
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : 1.0;
  } catch {
    return 1.0;
  }
}

export function storeModelZoomScale(zoomScale: number): void {
  try {
    window.localStorage.setItem(MODEL_ZOOM_STORAGE_KEY, String(zoomScale));
  } catch {
    // Ignore localStorage write failures.
  }
}

export function resolveInitialZoomScale(configZoomScale: unknown): number {
  const normalized = Number(configZoomScale);
  const stored = loadStoredModelZoomScale();
  if (Number.isFinite(stored) && Math.abs(stored - 1.0) > 0.0001) {
    if (!Number.isFinite(normalized) || Math.abs(normalized - 1.0) <= 0.0001) {
      return stored;
    }
  }
  if (Number.isFinite(normalized)) {
    return normalized;
  }
  return stored;
}
