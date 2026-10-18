// Bounded pet-local probes. Launcher lifecycle is reported by Qt itself.
function withTimeout(promise, timeoutMs, fallback) {
  return new Promise(resolve => {
    const timer = setTimeout(() => resolve(fallback), timeoutMs);
    Promise.resolve(promise).then(
      value => { clearTimeout(timer); resolve(value); },
      () => { clearTimeout(timer); resolve(fallback); }
    );
  });
}

function validRect(bounds) {
  return Boolean(bounds && [bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isFinite)
    && bounds.width > 0 && bounds.height > 0);
}

function modelRect(bounds) {
  if (!bounds || ![bounds.left, bounds.top, bounds.right, bounds.bottom].every(Number.isFinite)) return null;
  const rect = { x: bounds.left, y: bounds.top, width: bounds.right - bounds.left, height: bounds.bottom - bounds.top };
  return validRect(rect) ? rect : null;
}

function usableIntersection(model, ...frames) {
  if (!validRect(model) || !frames.every(validRect)) return false;
  const rects = [model, ...frames];
  const width = Math.min(...rects.map(r => r.x + r.width)) - Math.max(...rects.map(r => r.x));
  const height = Math.min(...rects.map(r => r.y + r.height)) - Math.max(...rects.map(r => r.y));
  return width >= Math.min(64, model.width) && height >= Math.min(64, model.height);
}

// Pure observation: no geometry recovery, renderer command or state persistence.
function petCapability(inspector, presentation, ageMs, displays, nativeContentBounds, nativeVisible = false) {
  const ready = inspector?.ready === true;
  const model = modelRect(inspector?.modelScreenBounds);
  const areas = (Array.isArray(displays) ? displays : []).map(d => d?.bounds || d?.workArea).filter(validRect);
  const nativeKnown = validRect(nativeContentBounds);
  const geometryKnown = Boolean(model && nativeKnown && areas.length);
  const visibleOnDisplay = Boolean(model && areas.some(area => usableIntersection(model, area)));
  const visibleWithinNativeContent = Boolean(model && nativeKnown && usableIntersection(model, nativeContentBounds));
  const visible = ready && nativeVisible === true && geometryKnown
    && areas.some(area => usableIntersection(model, nativeContentBounds, area));
  const contained = model && nativeKnown && model.x >= nativeContentBounds.x && model.y >= nativeContentBounds.y
    && model.x + model.width <= nativeContentBounds.x + nativeContentBounds.width
    && model.y + model.height <= nativeContentBounds.y + nativeContentBounds.height;
  return {
    state: visible ? 'ready' : ready ? (!geometryKnown ? 'unknown' : nativeVisible !== true ? 'hidden' : 'offscreen') : !presentation ? 'missing'
      : ageMs < 20000 ? 'loading' : 'failed',
    modelReady: ready, visible: Boolean(visible), responsive: Boolean(inspector),
    visibleOnDisplay, visibleWithinNativeContent,
    nativeVisible: nativeVisible === true,
    hostClip: !model || !nativeKnown ? 'unknown' : contained ? 'none' : visibleWithinNativeContent ? 'partial' : 'full'
  };
}
module.exports = { withTimeout, petCapability };
