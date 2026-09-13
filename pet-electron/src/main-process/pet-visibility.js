function areaFor(anchor, displays) {
  const areas = displays.map(display => display.workArea || display.bounds);
  return areas.reduce((best, area) => {
    const distance = r => Math.hypot(anchor.x - Math.max(r.x, Math.min(anchor.x, r.x + r.width)), anchor.y - Math.max(r.y, Math.min(anchor.y, r.y + r.height)));
    return !best || distance(area) < distance(best) ? area : best;
  }, null);
}
function repairPlacement(anchor, displays, bounds = null) {
  const area = areaFor(anchor, displays);
  if (!area) return anchor;
  if (!bounds) {
    if (displays.some(d => { const a = d.workArea || d.bounds; return anchor.x >= a.x && anchor.x < a.x + a.width && anchor.y >= a.y && anchor.y < a.y + a.height; })) return anchor;
    return { x: Math.max(area.x + 80, Math.min(anchor.x, area.x + area.width - 80)), y: Math.max(area.y + 80, Math.min(anchor.y, area.y + area.height - 24)) };
  }
  // A partly clipped or oversized model can still be deliberately positioned
  // and dragged. Recovery is only for models with no usable visible area.
  if (modelIsVisible(bounds, displays)) return anchor;
  const width = bounds.right - bounds.left, height = bounds.bottom - bounds.top;
  const left = width <= area.width ? Math.max(area.x, Math.min(bounds.left, area.x + area.width - width)) : area.x + (area.width - width) / 2;
  const top = height <= area.height ? Math.max(area.y, Math.min(bounds.top, area.y + area.height - height)) : area.y;
  return { x: anchor.x + left - bounds.left, y: anchor.y + top - bounds.top };
}
function modelIsVisible(bounds, displays) {
  if (!bounds) return false;
  return displays.some(d => {
    const a = d.workArea || d.bounds;
    const width = Math.max(0, Math.min(bounds.right, a.x + a.width) - Math.max(bounds.left, a.x));
    const height = Math.max(0, Math.min(bounds.bottom, a.y + a.height) - Math.max(bounds.top, a.y));
    return width >= Math.min(bounds.right - bounds.left, 64) && height >= Math.min(bounds.bottom - bounds.top, 64);
  });
}
module.exports = { repairPlacement, modelIsVisible };
