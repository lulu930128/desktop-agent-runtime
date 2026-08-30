const assert = require("node:assert/strict");
const test = require("node:test");

const {
  hostContainsBounds,
  resolveHostResizeAction,
  resolvePetHostBounds,
  shouldFreezePetHostRelocation
} = require("../pet-electron/src/main-process/pet-host-envelope");

test("model bounds plus padding determine the native host", () => {
  const host = resolvePetHostBounds({
    left: 2250,
    top: 320,
    right: 2900,
    bottom: 1380
  });

  assert.deepEqual(host, { x: 2154, y: 224, width: 842, height: 1252 });
  assert.equal(
    hostContainsBounds(host, { x: 2154, y: 224, width: 842, height: 1252 }),
    true
  );
});

test("a cross-monitor model receives only its local envelope", () => {
  const host = resolvePetHostBounds({
    left: 2250,
    top: 300,
    right: 2900,
    bottom: 1300
  });

  assert.ok(host.x > 0);
  assert.ok(host.x + host.width < 5120);
  assert.ok(host.x < 2560);
  assert.ok(host.x + host.width > 2560);
});

test("extreme model zoom can produce a host larger than one display", () => {
  const host = resolvePetHostBounds({
    left: -700,
    top: -1600,
    right: 3300,
    bottom: 2400
  });

  assert.ok(host.width > 2560);
  assert.ok(host.height > 1440);
  assert.deepEqual(host, { x: -796, y: -1696, width: 4192, height: 4192 });
});

test("host grows immediately and shrinks lazily", () => {
  const current = { x: 100, y: 100, width: 800, height: 1200 };

  assert.equal(
    resolveHostResizeAction(current, { x: 60, y: 100, width: 880, height: 1200 }),
    "apply"
  );
  assert.equal(
    resolveHostResizeAction(current, { x: 180, y: 180, width: 640, height: 1000 }),
    "shrink"
  );
  assert.equal(
    resolveHostResizeAction(current, { x: 110, y: 110, width: 780, height: 1180 }),
    "keep"
  );
  assert.equal(
    resolveHostResizeAction(current, { x: 116, y: 100, width: 800, height: 1200 }),
    "keep",
    "normal drawable motion stays inside the safety-padding hysteresis"
  );
});

test("small models retain a bounded recovery viewport", () => {
  const host = resolvePetHostBounds({
    left: 500,
    top: 500,
    right: 560,
    bottom: 620
  });

  assert.deepEqual(host, { x: 390, y: 350, width: 280, height: 420 });
});

test("interaction freeze suppresses relocation only for enabled pet drag or zoom", () => {
  assert.equal(
    shouldFreezePetHostRelocation({
      enabled: true,
      mode: "pet",
      dragActive: true,
      zoomActive: false
    }),
    true
  );
  assert.equal(
    shouldFreezePetHostRelocation({
      enabled: true,
      mode: "pet",
      dragActive: false,
      zoomActive: true
    }),
    true
  );
  assert.equal(
    shouldFreezePetHostRelocation({
      enabled: false,
      mode: "pet",
      dragActive: true,
      zoomActive: true
    }),
    false
  );
  assert.equal(
    shouldFreezePetHostRelocation({
      enabled: true,
      mode: "window",
      dragActive: true,
      zoomActive: true
    }),
    false
  );
  assert.equal(
    shouldFreezePetHostRelocation({
      enabled: true,
      mode: "pet",
      dragActive: false,
      zoomActive: false
    }),
    false
  );
});
