const FIXED_PET_SHELL_MUTATION_REASONS = new Set([
  "startup",
  "display-topology",
  "mode-switch",
  "recovery"
]);

function finiteNumber(value, fallback = 0) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : fallback;
}

function normalizeDisplayBounds(display, fallbackId = 0) {
  const source = display?.bounds || display?.workArea || display;
  const x = Math.round(finiteNumber(source?.x));
  const y = Math.round(finiteNumber(source?.y));
  const width = Math.max(1, Math.round(finiteNumber(source?.width, 1)));
  const height = Math.max(1, Math.round(finiteNumber(source?.height, 1)));
  return {
    id: display?.id ?? fallbackId,
    x,
    y,
    width,
    height,
    right: x + width,
    bottom: y + height
  };
}

function resolveFixedDesktopShellBounds(displays) {
  const normalized = Array.isArray(displays)
    ? displays.map((display, index) => normalizeDisplayBounds(display, index))
    : [];
  const areas = normalized.length
    ? normalized
    : [normalizeDisplayBounds({ x: 0, y: 0, width: 1280, height: 720 })];
  const left = Math.min(...areas.map((area) => area.x));
  const top = Math.min(...areas.map((area) => area.y));
  const right = Math.max(...areas.map((area) => area.right));
  const bottom = Math.max(...areas.map((area) => area.bottom));

  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top)
  };
}

function canMutateFixedPetShell(reason) {
  return FIXED_PET_SHELL_MUTATION_REASONS.has(String(reason || ""));
}

// Native readback is evidence, so malformed values must not become defaults.
function readNativeContentBounds(window) {
  try {
    if (!window || window.isDestroyed()) return null;
    const bounds = window.getContentBounds();
    if (!bounds || ![bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isFinite)
      || bounds.width <= 0 || bounds.height <= 0) return null;
    return { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
  } catch {
    return null;
  }
}

function containsFrame(outer, inner) {
  return Boolean(outer && inner && outer.x <= inner.x && outer.y <= inner.y
    && outer.x + outer.width >= inner.x + inner.width
    && outer.y + outer.height >= inner.y + inner.height);
}

function selectAnchorDisplayBounds(displays, anchor) {
  if (!anchor || ![anchor.x, anchor.y].every(Number.isFinite)) return null;
  const areas = (Array.isArray(displays) ? displays : [])
    .map(display => display?.bounds)
    .filter(bounds => bounds && [bounds.x, bounds.y, bounds.width, bounds.height].every(Number.isFinite)
      && bounds.width > 0 && bounds.height > 0);
  const distance = area => Math.hypot(
    anchor.x - Math.max(area.x, Math.min(anchor.x, area.x + area.width)),
    anchor.y - Math.max(area.y, Math.min(anchor.y, area.y + area.height))
  );
  const nearest = areas.reduce((best, area) => !best || distance(area) < distance(best) ? area : best, null);
  return nearest ? { x: nearest.x, y: nearest.y, width: nearest.width, height: nearest.height } : null;
}

// One union attempt and at most one display fallback on the existing owner.
// All coordinates are Electron DIPs; display scale metadata is not a multiplier.
function reconcileFixedPetShell({ window, displays, anchor, reason, applyBounds }) {
  let actualBounds = readNativeContentBounds(window);
  if (reason !== "startup" && reason !== "display-topology") {
    return { state: "denied", actualBounds, fallbackAttempted: false };
  }
  const displayBounds = selectAnchorDisplayBounds(displays, anchor);
  if (!displayBounds) return { state: "unknown", actualBounds, fallbackAttempted: false };
  const unionBounds = resolveFixedDesktopShellBounds(displays);
  let fallbackAttempted = false;
  try {
    applyBounds(unionBounds, reason);
    actualBounds = readNativeContentBounds(window);
    if (containsFrame(actualBounds, unionBounds)) {
      return { state: "union", actualBounds, fallbackAttempted };
    }
    if (!containsFrame(actualBounds, displayBounds)) {
      fallbackAttempted = true;
      applyBounds(displayBounds, reason);
      actualBounds = readNativeContentBounds(window);
    }
  } catch {
    return { state: "degraded", actualBounds: readNativeContentBounds(window), fallbackAttempted };
  }
  return {
    state: !actualBounds ? "unknown" : containsFrame(actualBounds, displayBounds) ? "per-display" : "degraded",
    actualBounds,
    fallbackAttempted
  };
}

module.exports = {
  FIXED_PET_SHELL_MUTATION_REASONS,
  canMutateFixedPetShell,
  readNativeContentBounds,
  reconcileFixedPetShell,
  selectAnchorDisplayBounds,
  normalizeDisplayBounds,
  resolveFixedDesktopShellBounds
};
