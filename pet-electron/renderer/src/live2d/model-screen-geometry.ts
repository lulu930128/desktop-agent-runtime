export type ModelDrawableBounds = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type AffineAxisTransform = {
  scaleX: number;
  scaleY: number;
  translateX: number;
  translateY: number;
};

export type ModelScreenBounds = {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
};

export type ScreenViewport = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PlacementTranslation = {
  x: number;
  y: number;
};

export const REFERENCE_MODEL_VIEWPORT_HALF_DIP = 640;

function finitePositive(value: number): number | null {
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function resolveViewportPixelsPerViewUnit(
  viewportWidth: number,
  viewportHeight: number
): number | null {
  const width = finitePositive(viewportWidth);
  const height = finitePositive(viewportHeight);
  return width && height ? Math.min(width, height) / 2 : null;
}

export function resolveViewportInvariantTargetHeight(
  baseTargetHeight: number,
  zoomScale: number,
  viewportWidth: number,
  viewportHeight: number
): number | null {
  const pixelsPerViewUnit = resolveViewportPixelsPerViewUnit(
    viewportWidth,
    viewportHeight
  );
  if (
    !pixelsPerViewUnit ||
    !Number.isFinite(baseTargetHeight) ||
    baseTargetHeight <= 0 ||
    !Number.isFinite(zoomScale) ||
    zoomScale <= 0
  ) {
    return null;
  }

  const desiredModelCanvasHeightDip =
    baseTargetHeight * zoomScale * REFERENCE_MODEL_VIEWPORT_HALF_DIP;
  return desiredModelCanvasHeightDip / pixelsPerViewUnit;
}

export function resolveStablePlacementTranslation(
  stableBounds: ModelDrawableBounds,
  anchorViewPoint: { x: number; y: number },
  scaleX: number,
  scaleY: number
): PlacementTranslation | null {
  if (
    !stableBounds ||
    !Number.isFinite(stableBounds.left) ||
    !Number.isFinite(stableBounds.right) ||
    !Number.isFinite(stableBounds.top) ||
    !Number.isFinite(stableBounds.bottom) ||
    stableBounds.right <= stableBounds.left ||
    stableBounds.bottom <= stableBounds.top ||
    !Number.isFinite(anchorViewPoint?.x) ||
    !Number.isFinite(anchorViewPoint?.y) ||
    !Number.isFinite(scaleX) ||
    !Number.isFinite(scaleY)
  ) {
    return null;
  }

  const centerX = (stableBounds.left + stableBounds.right) / 2;
  return {
    x: anchorViewPoint.x - centerX * scaleX,
    y: anchorViewPoint.y - stableBounds.top * scaleY
  };
}

export function resolveModelScreenBounds(
  modelBounds: ModelDrawableBounds,
  modelTransform: AffineAxisTransform,
  projectionTransform: AffineAxisTransform,
  viewport: ScreenViewport
): ModelScreenBounds | null {
  if (
    !modelBounds ||
    !modelTransform ||
    !projectionTransform ||
    !viewport ||
    !finitePositive(viewport.width) ||
    !finitePositive(viewport.height)
  ) {
    return null;
  }

  const xs = [modelBounds.left, modelBounds.right];
  const ys = [modelBounds.top, modelBounds.bottom];
  if (
    [...xs, ...ys].some((value) => !Number.isFinite(value)) ||
    modelBounds.right <= modelBounds.left ||
    modelBounds.bottom <= modelBounds.top
  ) {
    return null;
  }

  const screenXs = xs.map((modelX) => {
    const viewX = modelTransform.scaleX * modelX + modelTransform.translateX;
    const deviceX = projectionTransform.scaleX * viewX + projectionTransform.translateX;
    return viewport.x + ((deviceX + 1) / 2) * viewport.width;
  });
  const screenYs = ys.map((modelY) => {
    const viewY = modelTransform.scaleY * modelY + modelTransform.translateY;
    const deviceY = projectionTransform.scaleY * viewY + projectionTransform.translateY;
    return viewport.y + ((1 - deviceY) / 2) * viewport.height;
  });
  const left = Math.min(...screenXs);
  const right = Math.max(...screenXs);
  const top = Math.min(...screenYs);
  const bottom = Math.max(...screenYs);

  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top
  };
}
