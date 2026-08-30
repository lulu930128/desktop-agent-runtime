export type ZoomScreenPoint = {
  x: number;
  y: number;
};

export const MODEL_ZOOM_WHEEL_FACTOR = 1.06;

export function resolveWheelZoomFactor(deltaY: number): number | null {
  if (!Number.isFinite(deltaY) || deltaY === 0) {
    return null;
  }
  return deltaY < 0
    ? MODEL_ZOOM_WHEEL_FACTOR
    : 1 / MODEL_ZOOM_WHEEL_FACTOR;
}

export function resolvePivotPreservingAnchor(
  anchor: ZoomScreenPoint,
  pivot: ZoomScreenPoint,
  previousScale: number,
  nextScale: number
): ZoomScreenPoint {
  if (
    !Number.isFinite(anchor.x) ||
    !Number.isFinite(anchor.y) ||
    !Number.isFinite(pivot.x) ||
    !Number.isFinite(pivot.y) ||
    !Number.isFinite(previousScale) ||
    !Number.isFinite(nextScale) ||
    previousScale <= 0 ||
    nextScale <= 0
  ) {
    return { ...anchor };
  }

  const scaleRatio = nextScale / previousScale;
  return {
    x: pivot.x - (pivot.x - anchor.x) * scaleRatio,
    y: pivot.y - (pivot.y - anchor.y) * scaleRatio
  };
}
