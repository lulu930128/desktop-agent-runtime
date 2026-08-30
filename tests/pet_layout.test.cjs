const assert = require("node:assert/strict");
const test = require("node:test");

const {
  resolvePetLayout,
  resolvePetDisplayContext,
  resolveZoomAwarePetHostSize
} = require("../pet-electron/src/main-process/pet-layout");

const alignedDisplays = [
  { id: 1, workArea: { x: 0, y: 0, width: 2560, height: 1440 } },
  { id: 2, workArea: { x: 2560, y: 0, width: 2560, height: 1440 } }
];

test("pet host follows the anchor instead of spanning the virtual desktop", () => {
  const layout = resolvePetLayout({ x: 1800, y: 1416 }, alignedDisplays);

  assert.deepEqual(layout.anchor, { x: 1800, y: 1416 });
  assert.deepEqual(layout.hostBounds, { x: 1420, y: 160, width: 760, height: 1280 });
  assert.deepEqual(layout.localAnchor, { x: 380, y: 1256 });
});

test("an anchor in a staggered-display gap remains a valid offscreen placement", () => {
  const staggeredDisplays = [
    { id: 1, workArea: { x: 0, y: 0, width: 2560, height: 1440 } },
    { id: 2, workArea: { x: 2560, y: 86, width: 2560, height: 1440 } }
  ];
  const layout = resolvePetLayout({ x: 3000, y: 20 }, staggeredDisplays);

  assert.equal(layout.displayId, 2);
  assert.deepEqual(layout.anchor, { x: 3000, y: 20 });
  assert.equal(layout.hostBounds.y, -1236);
});

test("an internal monitor seam remains traversable", () => {
  const left = resolvePetLayout({ x: 2559, y: 1200 }, alignedDisplays);
  const right = resolvePetLayout({ x: 2560, y: 1200 }, alignedDisplays);

  assert.equal(left.anchor.x, 2559);
  assert.equal(right.anchor.x, 2560);
  assert.equal(left.hostBounds.width, 760);
  assert.equal(right.hostBounds.width, 760);
});

test("outer edges do not clamp an intentionally offscreen anchor", () => {
  const left = resolvePetLayout({ x: -500, y: 4000 }, alignedDisplays);
  const right = resolvePetLayout({ x: 9000, y: 4000 }, alignedDisplays);

  assert.deepEqual(left.anchor, { x: -500, y: 4000 });
  assert.deepEqual(right.anchor, { x: 9000, y: 4000 });
  assert.equal(left.hostBounds.x, -880);
  assert.equal(right.hostBounds.x, 8620);
});

test("the pet can move below a display without a layout-imposed lower bound", () => {
  const layout = resolvePetLayout({ x: 1800, y: 2400 }, alignedDisplays);

  assert.deepEqual(layout.anchor, { x: 1800, y: 2400 });
  assert.deepEqual(layout.hostBounds, { x: 1420, y: 1144, width: 760, height: 1280 });
  assert.deepEqual(layout.localAnchor, { x: 380, y: 1256 });
});

test("small displays receive a bounded adaptive host", () => {
  const layout = resolvePetLayout(
    { x: 400, y: 560 },
    [{ id: 9, workArea: { x: 0, y: 0, width: 800, height: 600 } }]
  );

  assert.deepEqual(layout.hostBounds, { x: 20, y: -16, width: 760, height: 600 });
  assert.deepEqual(layout.localAnchor, { x: 380, y: 576 });
});

test("zoom uses a stepped host envelope instead of resizing on every wheel frame", () => {
  assert.deepEqual(resolveZoomAwarePetHostSize(0.8), {
    hostWidth: 760,
    hostHeight: 1280
  });
  assert.deepEqual(resolveZoomAwarePetHostSize(1.06), {
    hostWidth: 950,
    hostHeight: 1600
  });
  assert.deepEqual(resolveZoomAwarePetHostSize(1.24), {
    hostWidth: 950,
    hostHeight: 1600
  });
  assert.deepEqual(resolveZoomAwarePetHostSize(1.26), {
    hostWidth: 1140,
    hostHeight: 1920
  });
});

test("a zoom-aware host grows to the display edge without moving the feet anchor", () => {
  const anchor = { x: 1800, y: 1416 };
  const normal = resolvePetLayout(anchor, alignedDisplays);
  const zoomed = resolvePetLayout(
    anchor,
    alignedDisplays,
    resolveZoomAwarePetHostSize(1.06)
  );

  assert.deepEqual(normal.anchor, anchor);
  assert.deepEqual(zoomed.anchor, anchor);
  assert.deepEqual(zoomed.hostBounds, {
    x: 1325,
    y: 58,
    width: 950,
    height: 1382
  });
  assert.deepEqual(zoomed.localAnchor, { x: 475, y: 1358 });
});

test("extreme zoom remains compact instead of becoming a fullscreen host", () => {
  const layout = resolvePetLayout(
    { x: 1800, y: 1416 },
    alignedDisplays,
    resolveZoomAwarePetHostSize(8)
  );

  assert.equal(layout.displayId, 1);
  assert.equal(layout.hostBounds.width, 1843);
  assert.equal(layout.hostBounds.height, 1382);
  assert.ok(layout.hostBounds.width < alignedDisplays[0].workArea.width);
  assert.ok(layout.hostBounds.height < alignedDisplays[0].workArea.height);
  assert.notEqual(layout.hostBounds.width, 5120);
});

test("compact host limits do not clamp an intentionally offscreen anchor", () => {
  const layout = resolvePetLayout(
    { x: 1800, y: 2400 },
    alignedDisplays,
    resolveZoomAwarePetHostSize(8)
  );

  assert.deepEqual(layout.anchor, { x: 1800, y: 2400 });
  assert.equal(layout.hostBounds.y, 1042);
  assert.deepEqual(layout.localAnchor, { x: 921, y: 1358 });
});

test("display scaleFactor is metadata and never rescales DIP placement", () => {
  const mixedDpiDisplays = [
    {
      id: 1,
      scaleFactor: 1,
      workArea: { x: 0, y: 0, width: 2560, height: 1440 }
    },
    {
      id: 2,
      scaleFactor: 1.25,
      workArea: { x: 2560, y: 0, width: 2048, height: 1152 }
    }
  ];
  const left = resolvePetDisplayContext({ x: 2559, y: 900 }, mixedDpiDisplays);
  const right = resolvePetDisplayContext({ x: 2560, y: 900 }, mixedDpiDisplays);
  const rightLayout = resolvePetLayout({ x: 2560, y: 900 }, mixedDpiDisplays);

  assert.equal(left.scaleFactor, 1);
  assert.equal(right.scaleFactor, 1.25);
  assert.deepEqual(rightLayout.anchor, { x: 2560, y: 900 });
});
