export type ModelBounds = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type ModelInteractionProfile = {
  id: string;
  faceOrigin: { x: number; y: number };
  lookRange: { x: number; y: number };
};

const KURO_PROFILE: ModelInteractionProfile = {
  id: "kuro-v1",
  faceOrigin: { x: 0.5, y: 0.83 },
  lookRange: { x: 0.45, y: 0.38 }
};

const GENERIC_PROFILE: ModelInteractionProfile = {
  id: "generic-humanoid-v1",
  faceOrigin: { x: 0.5, y: 0.82 },
  lookRange: { x: 0.46, y: 0.4 }
};

function normalizeModelUrl(modelUrl: string): string {
  try {
    return decodeURIComponent(String(modelUrl || "")).replace(/\\/g, "/").toLowerCase();
  } catch {
    return String(modelUrl || "").replace(/\\/g, "/").toLowerCase();
  }
}

export function resolveModelInteractionProfile(modelUrl: string): ModelInteractionProfile {
  const normalized = normalizeModelUrl(modelUrl);
  return normalized.includes("/kuro/") || normalized.includes("小黑")
    ? KURO_PROFILE
    : GENERIC_PROFILE;
}

export function modelPointToNormalized(
  point: { x: number; y: number },
  bounds: ModelBounds
): { x: number; y: number } | null {
  const width = bounds.right - bounds.left;
  const height = bounds.bottom - bounds.top;
  if (!(width > 0) || !(height > 0)) {
    return null;
  }
  return {
    x: (point.x - bounds.left) / width,
    y: (point.y - bounds.top) / height
  };
}
