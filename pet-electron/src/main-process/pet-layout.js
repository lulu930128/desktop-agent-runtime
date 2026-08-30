const DEFAULT_LAYOUT_OPTIONS = Object.freeze({
  hostWidth: 760,
  hostHeight: 1280,
  bottomInset: 24,
  maxHostWidthRatio: 0.72,
  maxHostHeightRatio: 0.96
});

const PET_HOST_ZOOM_STEP = 0.25;

function finiteNumber(value, fallback = 0) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function normalizeRect(rect, fallbackId, scaleFactor = 1) {
  const x = Math.round(finiteNumber(rect?.x));
  const y = Math.round(finiteNumber(rect?.y));
  const width = Math.max(1, Math.round(finiteNumber(rect?.width, 1)));
  const height = Math.max(1, Math.round(finiteNumber(rect?.height, 1)));
  return {
    id: rect?.id ?? fallbackId,
    x,
    y,
    width,
    height,
    right: x + width,
    bottom: y + height,
    scaleFactor: Math.max(0.1, finiteNumber(scaleFactor, 1))
  };
}

function normalizeWorkAreas(displays) {
  const areas = Array.isArray(displays)
    ? displays.map((display, index) =>
        normalizeRect(
          display?.workArea || display?.bounds || display,
          display?.id ?? index,
          display?.scaleFactor
        )
      )
    : [];

  return areas.length ? areas : [normalizeRect({ x: 0, y: 0, width: 1280, height: 720 }, 0)];
}

function resolvePetDisplayContext(point, displays) {
  const areas = normalizeWorkAreas(displays);
  const fallbackArea = areas[0];
  const requestedPoint = {
    x: finiteNumber(point?.x, fallbackArea.x + fallbackArea.width / 2),
    y: finiteNumber(point?.y, fallbackArea.y + fallbackArea.height / 2)
  };
  const area = pickWorkArea(areas, requestedPoint);
  return {
    displayId: area.id,
    scaleFactor: area.scaleFactor,
    workArea: {
      x: area.x,
      y: area.y,
      width: area.width,
      height: area.height
    }
  };
}

function containsPoint(area, point) {
  return (
    point.x >= area.x &&
    point.x < area.right &&
    point.y >= area.y &&
    point.y < area.bottom
  );
}

function squaredDistanceToRect(area, point) {
  const nearestX = Math.min(Math.max(point.x, area.x), area.right - 1);
  const nearestY = Math.min(Math.max(point.y, area.y), area.bottom - 1);
  const dx = point.x - nearestX;
  const dy = point.y - nearestY;
  return dx * dx + dy * dy;
}

function pickWorkArea(areas, point) {
  const containing = areas.find((area) => containsPoint(area, point));
  if (containing) {
    return containing;
  }

  return areas.reduce((nearest, area) =>
    squaredDistanceToRect(area, point) < squaredDistanceToRect(nearest, point)
      ? area
      : nearest
  );
}

function resolveZoomAwarePetHostSize(zoomScale, options = {}) {
  const baseWidth = Math.max(
    1,
    Math.round(finiteNumber(options.baseWidth, DEFAULT_LAYOUT_OPTIONS.hostWidth))
  );
  const baseHeight = Math.max(
    1,
    Math.round(finiteNumber(options.baseHeight, DEFAULT_LAYOUT_OPTIONS.hostHeight))
  );
  const step = Math.max(
    0.01,
    finiteNumber(options.zoomStep, PET_HOST_ZOOM_STEP)
  );
  const normalizedZoom = Math.max(1, finiteNumber(zoomScale, 1));
  const envelopeScale =
    normalizedZoom <= 1 ? 1 : Math.ceil(normalizedZoom / step) * step;

  return {
    hostWidth: Math.round(baseWidth * envelopeScale),
    hostHeight: Math.round(baseHeight * envelopeScale)
  };
}

function resolvePetLayout(point, displays, options = {}) {
  const config = { ...DEFAULT_LAYOUT_OPTIONS, ...(options || {}) };
  const areas = normalizeWorkAreas(displays);
  const fallbackArea = areas[0];
  const requestedPoint = {
    x: finiteNumber(point?.x, fallbackArea.x + fallbackArea.width / 2),
    y: finiteNumber(point?.y, fallbackArea.bottom - config.bottomInset)
  };
  const area = pickWorkArea(areas, requestedPoint);
  const minimumHostWidth = Math.min(area.width, DEFAULT_LAYOUT_OPTIONS.hostWidth);
  const minimumHostHeight = Math.min(area.height, DEFAULT_LAYOUT_OPTIONS.hostHeight);
  const maxHostWidth = Math.min(
    area.width,
    Math.max(
      minimumHostWidth,
      Math.floor(area.width * Math.min(1, Math.max(0.1, config.maxHostWidthRatio)))
    )
  );
  const maxHostHeight = Math.min(
    area.height,
    Math.max(
      minimumHostHeight,
      Math.floor(area.height * Math.min(1, Math.max(0.1, config.maxHostHeightRatio)))
    )
  );
  const hostWidth = Math.min(maxHostWidth, Math.max(1, Math.round(config.hostWidth)));
  const hostHeight = Math.min(maxHostHeight, Math.max(1, Math.round(config.hostHeight)));
  const bottomInset = Math.min(
    hostHeight - 1,
    Math.max(0, Math.round(config.bottomInset))
  );
  const anchor = {
    x: requestedPoint.x,
    y: requestedPoint.y
  };
  const unclampedHostX = Math.round(anchor.x - hostWidth / 2);
  const unclampedHostY = Math.round(anchor.y - (hostHeight - bottomInset));
  const hostBounds = {
    x: unclampedHostX,
    y: unclampedHostY,
    width: hostWidth,
    height: hostHeight
  };

  return {
    anchor,
    hostBounds,
    displayId: area.id,
    scaleFactor: area.scaleFactor,
    workArea: {
      x: area.x,
      y: area.y,
      width: area.width,
      height: area.height
    },
    localAnchor: {
      x: anchor.x - hostBounds.x,
      y: anchor.y - hostBounds.y
    }
  };
}

module.exports = {
  DEFAULT_LAYOUT_OPTIONS,
  PET_HOST_ZOOM_STEP,
  containsPoint,
  normalizeWorkAreas,
  resolvePetDisplayContext,
  resolveZoomAwarePetHostSize,
  resolvePetLayout
};
