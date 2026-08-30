const DEFAULT_HOST_ENVELOPE_OPTIONS = Object.freeze({
  horizontalPadding: 96,
  verticalPadding: 96,
  minWidth: 280,
  minHeight: 420,
  // Keep most of the 96 DIP safety padding available while allowing normal
  // Live2D vertex motion to move inside the transparent host without causing
  // a native BrowserWindow resize on every frame.
  expandTolerance: 24,
  shrinkMargin: 48
});

function finiteNumber(value, fallback = 0) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function normalizeScreenBounds(bounds) {
  if (!bounds || typeof bounds !== "object") {
    return null;
  }

  const left = finiteNumber(bounds.left, Number.NaN);
  const top = finiteNumber(bounds.top, Number.NaN);
  const right = finiteNumber(bounds.right, Number.NaN);
  const bottom = finiteNumber(bounds.bottom, Number.NaN);
  if (
    !Number.isFinite(left) ||
    !Number.isFinite(top) ||
    !Number.isFinite(right) ||
    !Number.isFinite(bottom) ||
    right <= left ||
    bottom <= top
  ) {
    return null;
  }

  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top
  };
}

function normalizeHostBounds(bounds) {
  if (!bounds || typeof bounds !== "object") {
    return null;
  }

  const x = finiteNumber(bounds.x, Number.NaN);
  const y = finiteNumber(bounds.y, Number.NaN);
  const width = finiteNumber(bounds.width, Number.NaN);
  const height = finiteNumber(bounds.height, Number.NaN);
  if (
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return null;
  }

  return {
    x: Math.round(x),
    y: Math.round(y),
    width: Math.max(1, Math.round(width)),
    height: Math.max(1, Math.round(height))
  };
}

function resolvePetHostBounds(modelBounds, options = {}) {
  const normalizedModelBounds = normalizeScreenBounds(modelBounds);
  if (!normalizedModelBounds) {
    return null;
  }

  const config = { ...DEFAULT_HOST_ENVELOPE_OPTIONS, ...(options || {}) };
  const horizontalPadding = Math.max(0, finiteNumber(config.horizontalPadding));
  const verticalPadding = Math.max(0, finiteNumber(config.verticalPadding));
  const minWidth = Math.max(1, finiteNumber(config.minWidth, 1));
  const minHeight = Math.max(1, finiteNumber(config.minHeight, 1));
  const paddedLeft = normalizedModelBounds.left - horizontalPadding;
  const paddedTop = normalizedModelBounds.top - verticalPadding;
  const paddedRight = normalizedModelBounds.right + horizontalPadding;
  const paddedBottom = normalizedModelBounds.bottom + verticalPadding;
  const paddedWidth = paddedRight - paddedLeft;
  const paddedHeight = paddedBottom - paddedTop;
  const width = Math.max(minWidth, paddedWidth);
  const height = Math.max(minHeight, paddedHeight);
  const centerX = (paddedLeft + paddedRight) / 2;
  const centerY = (paddedTop + paddedBottom) / 2;
  const left = Math.floor(centerX - width / 2);
  const top = Math.floor(centerY - height / 2);
  const right = Math.ceil(centerX + width / 2);
  const bottom = Math.ceil(centerY + height / 2);

  return {
    x: left,
    y: top,
    width: right - left,
    height: bottom - top
  };
}

function hostContainsBounds(hostBounds, innerBounds, tolerance = 0) {
  const host = normalizeHostBounds(hostBounds);
  const inner = normalizeHostBounds(innerBounds);
  if (!host || !inner) {
    return false;
  }

  const allowed = Math.max(0, finiteNumber(tolerance));
  return (
    inner.x >= host.x - allowed &&
    inner.y >= host.y - allowed &&
    inner.x + inner.width <= host.x + host.width + allowed &&
    inner.y + inner.height <= host.y + host.height + allowed
  );
}

function resolveHostResizeAction(currentBounds, desiredBounds, options = {}) {
  const current = normalizeHostBounds(currentBounds);
  const desired = normalizeHostBounds(desiredBounds);
  if (!desired) {
    return "ignore";
  }
  if (!current) {
    return "apply";
  }

  const config = { ...DEFAULT_HOST_ENVELOPE_OPTIONS, ...(options || {}) };
  if (!hostContainsBounds(current, desired, config.expandTolerance)) {
    return "apply";
  }

  const shrinkMargin = Math.max(0, finiteNumber(config.shrinkMargin));
  if (
    current.width - desired.width >= shrinkMargin * 2 ||
    current.height - desired.height >= shrinkMargin * 2
  ) {
    return "shrink";
  }

  return "keep";
}

function shouldFreezePetHostRelocation(options = {}) {
  return Boolean(
    options.enabled === true &&
      options.mode === "pet" &&
      (options.dragActive === true || options.zoomActive === true)
  );
}

module.exports = {
  DEFAULT_HOST_ENVELOPE_OPTIONS,
  hostContainsBounds,
  normalizeHostBounds,
  normalizeScreenBounds,
  resolveHostResizeAction,
  resolvePetHostBounds,
  shouldFreezePetHostRelocation
};
