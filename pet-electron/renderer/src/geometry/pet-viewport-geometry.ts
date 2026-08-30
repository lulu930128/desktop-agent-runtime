export type ScreenPoint = {
  x: number;
  y: number;
};

export type CanvasViewportBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type CanvasClientRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

export type LocalBounds = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

function isFinitePoint(point: ScreenPoint): boolean {
  return Number.isFinite(point?.x) && Number.isFinite(point?.y);
}

function isValidViewportBounds(bounds: CanvasViewportBounds): boolean {
  return (
    isFinitePoint(bounds) &&
    Number.isFinite(bounds?.width) &&
    Number.isFinite(bounds?.height) &&
    bounds.width > 0 &&
    bounds.height > 0
  );
}

export function resolveActualCanvasViewportBounds(
  windowScreenPoint: ScreenPoint,
  canvasRect: CanvasClientRect
): CanvasViewportBounds | null {
  if (
    !isFinitePoint(windowScreenPoint) ||
    !Number.isFinite(canvasRect?.left) ||
    !Number.isFinite(canvasRect?.top) ||
    !Number.isFinite(canvasRect?.width) ||
    !Number.isFinite(canvasRect?.height) ||
    canvasRect.width <= 0 ||
    canvasRect.height <= 0
  ) {
    return null;
  }

  return {
    x: windowScreenPoint.x + canvasRect.left,
    y: windowScreenPoint.y + canvasRect.top,
    width: canvasRect.width,
    height: canvasRect.height
  };
}

export function getActualCanvasViewportBounds(
  canvas: HTMLCanvasElement
): CanvasViewportBounds | null {
  return resolveActualCanvasViewportBounds(
    { x: window.screenX, y: window.screenY },
    canvas.getBoundingClientRect()
  );
}

export function screenPointToViewportPoint(
  screenPoint: ScreenPoint,
  viewportBounds: CanvasViewportBounds
): ScreenPoint | null {
  if (!isFinitePoint(screenPoint) || !isValidViewportBounds(viewportBounds)) {
    return null;
  }

  return {
    x: screenPoint.x - viewportBounds.x,
    y: screenPoint.y - viewportBounds.y
  };
}

export function viewportPointToScreenPoint(
  viewportPoint: ScreenPoint,
  viewportBounds: CanvasViewportBounds
): ScreenPoint | null {
  if (!isFinitePoint(viewportPoint) || !isValidViewportBounds(viewportBounds)) {
    return null;
  }

  return {
    x: viewportBounds.x + viewportPoint.x,
    y: viewportBounds.y + viewportPoint.y
  };
}

export function containsScreenPoint(
  viewportBounds: CanvasViewportBounds,
  screenPoint: ScreenPoint
): boolean {
  const viewportPoint = screenPointToViewportPoint(screenPoint, viewportBounds);
  return Boolean(
    viewportPoint &&
      viewportPoint.x >= 0 &&
      viewportPoint.x < viewportBounds.width &&
      viewportPoint.y >= 0 &&
      viewportPoint.y < viewportBounds.height
  );
}

export function screenBoundsFromViewport(
  localBounds: LocalBounds,
  viewportBounds: CanvasViewportBounds
): LocalBounds | null {
  if (
    !Number.isFinite(localBounds?.left) ||
    !Number.isFinite(localBounds?.top) ||
    !Number.isFinite(localBounds?.right) ||
    !Number.isFinite(localBounds?.bottom) ||
    localBounds.right < localBounds.left ||
    localBounds.bottom < localBounds.top ||
    !isValidViewportBounds(viewportBounds)
  ) {
    return null;
  }

  return {
    left: viewportBounds.x + localBounds.left,
    top: viewportBounds.y + localBounds.top,
    right: viewportBounds.x + localBounds.right,
    bottom: viewportBounds.y + localBounds.bottom
  };
}
