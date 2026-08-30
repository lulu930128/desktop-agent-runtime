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

module.exports = {
  FIXED_PET_SHELL_MUTATION_REASONS,
  canMutateFixedPetShell,
  normalizeDisplayBounds,
  resolveFixedDesktopShellBounds
};
