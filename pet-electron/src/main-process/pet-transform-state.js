const DEFAULT_TRANSFORM_OPTIONS = Object.freeze({
  minZoomScale: 0.2,
  maxZoomScale: 8
});

function finiteNumber(value, fallback = Number.NaN) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function normalizeAnchor(anchor, fallback = { x: 0, y: 0 }) {
  const fallbackX = finiteNumber(fallback?.x, 0);
  const fallbackY = finiteNumber(fallback?.y, 0);
  return {
    x: finiteNumber(anchor?.x, fallbackX),
    y: finiteNumber(anchor?.y, fallbackY)
  };
}

function normalizeZoomScale(value, options = {}) {
  const config = { ...DEFAULT_TRANSFORM_OPTIONS, ...(options || {}) };
  const minZoomScale = Math.max(0.001, finiteNumber(config.minZoomScale, 0.2));
  const maxZoomScale = Math.max(
    minZoomScale,
    finiteNumber(config.maxZoomScale, 8)
  );
  const zoomScale = finiteNumber(value, 1);
  return Math.max(minZoomScale, Math.min(maxZoomScale, zoomScale));
}

function normalizeRevision(value, fallback = 1) {
  const revision = Number(value);
  return Number.isSafeInteger(revision) && revision >= 1 ? revision : fallback;
}

function createPetTransformState(input = {}, options = {}) {
  return {
    revision: normalizeRevision(input.revision, 1),
    anchor: normalizeAnchor(input.anchor),
    zoomScale: normalizeZoomScale(input.zoomScale, options)
  };
}

function resolvePivotPreservingAnchor(anchor, pivot, previousScale, nextScale) {
  const normalizedAnchor = normalizeAnchor(anchor);
  const pivotX = finiteNumber(pivot?.x);
  const pivotY = finiteNumber(pivot?.y);
  const previous = finiteNumber(previousScale);
  const next = finiteNumber(nextScale);
  if (
    !Number.isFinite(pivotX) ||
    !Number.isFinite(pivotY) ||
    !Number.isFinite(previous) ||
    !Number.isFinite(next) ||
    previous <= 0 ||
    next <= 0
  ) {
    return normalizedAnchor;
  }

  const scaleRatio = next / previous;
  return {
    x: pivotX - (pivotX - normalizedAnchor.x) * scaleRatio,
    y: pivotY - (pivotY - normalizedAnchor.y) * scaleRatio
  };
}

function advancePetTransformState(currentState, nextValues = {}, options = {}) {
  const current = createPetTransformState(currentState, options);
  const nextAnchor = normalizeAnchor(nextValues.anchor, current.anchor);
  const nextZoomScale = normalizeZoomScale(
    nextValues.zoomScale ?? current.zoomScale,
    options
  );
  const changed =
    nextAnchor.x !== current.anchor.x ||
    nextAnchor.y !== current.anchor.y ||
    nextZoomScale !== current.zoomScale;
  if (!changed) {
    return { changed: false, state: current };
  }
  if (current.revision >= Number.MAX_SAFE_INTEGER) {
    throw new Error("Pet transform revision exhausted");
  }

  return {
    changed: true,
    state: {
      revision: current.revision + 1,
      anchor: nextAnchor,
      zoomScale: nextZoomScale
    }
  };
}

function applyPetTransformRequest(currentState, request = {}, options = {}) {
  const current = createPetTransformState(currentState, options);
  const kind = String(request?.kind || "").trim().toLowerCase();

  if (kind === "zoom") {
    const scaleFactor = finiteNumber(request.scaleFactor);
    if (!Number.isFinite(scaleFactor) || scaleFactor <= 0) {
      return { accepted: false, changed: false, state: current };
    }
    const nextZoomScale = normalizeZoomScale(
      current.zoomScale * scaleFactor,
      options
    );
    const pivotX = finiteNumber(request.pivotScreenPoint?.x);
    const pivotY = finiteNumber(request.pivotScreenPoint?.y);
    if (!Number.isFinite(pivotX) || !Number.isFinite(pivotY)) {
      return { accepted: false, changed: false, state: current };
    }
    const pivot = { x: pivotX, y: pivotY };
    const nextAnchor = resolvePivotPreservingAnchor(
      current.anchor,
      pivot,
      current.zoomScale,
      nextZoomScale
    );
    const result = advancePetTransformState(
      current,
      { anchor: nextAnchor, zoomScale: nextZoomScale },
      options
    );
    return { accepted: true, ...result };
  }

  if (kind === "anchor") {
    const requestedX = finiteNumber(request.requestedAnchor?.x);
    const requestedY = finiteNumber(request.requestedAnchor?.y);
    if (!Number.isFinite(requestedX) || !Number.isFinite(requestedY)) {
      return { accepted: false, changed: false, state: current };
    }
    const result = advancePetTransformState(
      current,
      { anchor: { x: requestedX, y: requestedY } },
      options
    );
    return { accepted: true, ...result };
  }

  return { accepted: false, changed: false, state: current };
}

function isCurrentTransformRevision(currentState, revision) {
  const currentRevision = normalizeRevision(currentState?.revision, 1);
  return Number.isSafeInteger(Number(revision)) && Number(revision) === currentRevision;
}

module.exports = {
  DEFAULT_TRANSFORM_OPTIONS,
  advancePetTransformState,
  applyPetTransformRequest,
  createPetTransformState,
  isCurrentTransformRevision,
  normalizeAnchor,
  normalizeRevision,
  normalizeZoomScale,
  resolvePivotPreservingAnchor
};
