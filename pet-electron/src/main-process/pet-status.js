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

function petCapability(inspector, presentation, ageMs, displays, modelIsVisible) {
  const ready = inspector?.ready === true;
  const visible = ready && modelIsVisible(inspector.modelScreenBounds, displays);
  return {
    state: visible ? 'ready' : ready ? 'offscreen' : !presentation ? 'missing'
      : ageMs < 20000 ? 'loading' : 'failed',
    modelReady: ready, visible: Boolean(visible), responsive: Boolean(inspector)
  };
}
module.exports = { withTimeout, petCapability };
