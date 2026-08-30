import assert from "node:assert/strict";
import test from "node:test";

import {
  resolvePivotPreservingAnchor,
  resolveWheelZoomFactor
} from "../pet-electron/renderer/src/interaction/pet-zoom-geometry.ts";
import petLayout from "../pet-electron/src/main-process/pet-layout.js";

const { resolvePetLayout, resolveZoomAwarePetHostSize } = petLayout;

test("wheel input becomes a transform request factor without local state", () => {
  assert.equal(resolveWheelZoomFactor(-120), 1.06);
  assert.equal(resolveWheelZoomFactor(120), 1 / 1.06);
  assert.equal(resolveWheelZoomFactor(0), null);
});

test("zooming keeps the screen-space point under the wheel fixed", () => {
  const anchor = { x: 1800, y: 1416 };
  const pivot = { x: 1700, y: 900 };
  const previousScale = 1;
  const nextScale = 1.06;
  const nextAnchor = resolvePivotPreservingAnchor(
    anchor,
    pivot,
    previousScale,
    nextScale
  );
  const modelOffset = {
    x: (pivot.x - anchor.x) / previousScale,
    y: (pivot.y - anchor.y) / previousScale
  };

  assert.equal(nextAnchor.x + modelOffset.x * nextScale, pivot.x);
  assert.equal(nextAnchor.y + modelOffset.y * nextScale, pivot.y);
});

test("inverse zoom returns the original anchor without cumulative drift", () => {
  const anchor = { x: 1800, y: 1416 };
  const pivot = { x: 1700, y: 900 };
  const zoomedAnchor = resolvePivotPreservingAnchor(anchor, pivot, 1, 1.06);
  const restoredAnchor = resolvePivotPreservingAnchor(zoomedAnchor, pivot, 1.06, 1);

  assert.ok(Math.abs(restoredAnchor.x - anchor.x) < 1e-9);
  assert.ok(Math.abs(restoredAnchor.y - anchor.y) < 1e-9);
});

test("invalid zoom geometry leaves the accepted anchor unchanged", () => {
  const anchor = { x: 1800, y: 1416 };

  assert.deepEqual(
    resolvePivotPreservingAnchor(anchor, { x: Number.NaN, y: 900 }, 1, 1.06),
    anchor
  );
  assert.deepEqual(
    resolvePivotPreservingAnchor(anchor, { x: 1700, y: 900 }, 0, 1.06),
    anchor
  );
});

test("main-process layout accepts an offscreen pivot anchor without breaking reversibility", () => {
  const displays = [
    { id: 1, workArea: { x: 0, y: 0, width: 2560, height: 1440 } }
  ];
  const initialAnchor = { x: 2217, y: 1416 };
  const pivot = { x: 1850, y: 900 };
  let anchor = initialAnchor;
  let zoomScale = 1.2906773363770545;

  for (let index = 0; index < 12; index += 1) {
    const nextScale = zoomScale * 1.06;
    const proposedAnchor = resolvePivotPreservingAnchor(
      anchor,
      pivot,
      zoomScale,
      nextScale
    );
    const acceptedLayout = resolvePetLayout(
      proposedAnchor,
      displays,
      resolveZoomAwarePetHostSize(nextScale)
    );
    assert.deepEqual(acceptedLayout.anchor, proposedAnchor);
    assert.ok(acceptedLayout.hostBounds.width < displays[0].workArea.width);
    assert.ok(acceptedLayout.hostBounds.height < displays[0].workArea.height);
    anchor = acceptedLayout.anchor;
    zoomScale = nextScale;
  }

  assert.ok(anchor.x > displays[0].workArea.width);

  for (let index = 0; index < 12; index += 1) {
    const nextScale = zoomScale / 1.06;
    anchor = resolvePetLayout(
      resolvePivotPreservingAnchor(anchor, pivot, zoomScale, nextScale),
      displays,
      resolveZoomAwarePetHostSize(nextScale)
    ).anchor;
    zoomScale = nextScale;
  }

  assert.ok(Math.abs(anchor.x - initialAnchor.x) < 1e-9);
  assert.ok(Math.abs(anchor.y - initialAnchor.y) < 1e-9);
});
