// Window evidence only. Launcher owns process activation and recovery.
function withTimeout(promise, milliseconds, fallback) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(fallback), milliseconds);
    Promise.resolve(promise).then(
      (value) => { clearTimeout(timer); resolve(value); },
      () => { clearTimeout(timer); resolve(fallback); }
    );
  });
}

function readWindowState(window, screen) {
  const exists = Boolean(window && !window.isDestroyed());
  const bounds = exists ? window.getBounds() : null;
  // Require a usable title-bar area on one real display, not the virtual union.
  const display = bounds && screen.getAllDisplays().find(({ workArea: area }) => {
    const width = Math.min(bounds.x + bounds.width, area.x + area.width) - Math.max(bounds.x, area.x);
    return width >= Math.min(220, bounds.width) && bounds.y >= area.y && bounds.y + 32 <= area.y + area.height;
  });
  const contents = exists && window.webContents;
  return {
    contractVersion: 1,
    exists,
    visible: exists && window.isVisible(),
    minimized: exists && window.isMinimized(),
    focused: exists && window.isFocused(),
    bounds,
    displayId: display ? display.id : null,
    displayMatch: Boolean(display),
    loading: Boolean(contents && !contents.isDestroyed() && contents.isLoadingMainFrame()),
    rendererReady: false,
    responsive: false
  };
}

async function probeWindow(window, screen, timeoutMs = 300) {
  const state = readWindowState(window, screen);
  if (!state.exists || state.loading || window.webContents.isDestroyed()) return state;
  const probe = await withTimeout(
    Promise.resolve().then(() => window.webContents.executeJavaScript("window.__kuroWorkPanelReady === true", false))
      .then((ready) => ({ rendererReady: ready === true, responsive: true })),
    timeoutMs,
    { rendererReady: false, responsive: false }
  );
  const current = readWindowState(window, screen);
  return current.exists && !current.loading ? { ...current, ...probe } : current;
}

function revealWindow(window, { app, screen, clampBounds, platform = process.platform }) {
  if (!window || window.isDestroyed()) return readWindowState(window, screen);
  if (window.isMinimized()) window.restore();
  const before = window.getBounds();
  const bounds = clampBounds(before);
  const boundsClamped = ["x", "y", "width", "height"].some((key) => before[key] !== bounds[key]);
  if (boundsClamped) window.setBounds(bounds, false);
  window.show();
  window.moveTop();
  if (platform === "win32") app.focus({ steal: true });
  window.focus();
  return { ...readWindowState(window, screen), boundsClamped };
}

module.exports = { withTimeout, readWindowState, probeWindow, revealWindow };
