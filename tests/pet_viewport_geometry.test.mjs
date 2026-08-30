import assert from "node:assert/strict";
import test from "node:test";

import {
  containsScreenPoint,
  resolveActualCanvasViewportBounds,
  screenBoundsFromViewport,
  screenPointToViewportPoint,
  viewportPointToScreenPoint
} from "../pet-electron/renderer/src/geometry/pet-viewport-geometry.ts";
import {
  resolveModelScreenBounds,
  resolveStablePlacementTranslation
} from "../pet-electron/renderer/src/live2d/model-screen-geometry.ts";

function resolveStableAnchorFromViewport(anchor, viewport) {
  const stableBounds = { left: -0.4, right: 0.4, top: -0.75, bottom: 0.75 };
  const localAnchor = screenPointToViewportPoint(anchor, viewport);
  const deviceAnchor = {
    x: (localAnchor.x / viewport.width) * 2 - 1,
    y: 1 - (localAnchor.y / viewport.height) * 2
  };
  const projection = viewport.width < viewport.height
    ? { scaleX: 1, scaleY: viewport.width / viewport.height, translateX: 0, translateY: 0 }
    : { scaleX: viewport.height / viewport.width, scaleY: 1, translateX: 0, translateY: 0 };
  const anchorViewPoint = {
    x: deviceAnchor.x / projection.scaleX,
    y: deviceAnchor.y / projection.scaleY
  };
  const placement = resolveStablePlacementTranslation(
    stableBounds,
    anchorViewPoint,
    1.3,
    1.3
  );
  const screenBounds = resolveModelScreenBounds(
    stableBounds,
    {
      scaleX: 1.3,
      scaleY: 1.3,
      translateX: placement.x,
      translateY: placement.y
    },
    projection,
    viewport
  );

  return {
    x: (screenBounds.left + screenBounds.right) / 2,
    y: screenBounds.bottom
  };
}

test("actual canvas viewport includes the renderer window origin and canvas offset", () => {
  assert.deepEqual(
    resolveActualCanvasViewportBounds(
      { x: 1000, y: 200 },
      { left: 12, top: 8, width: 800, height: 1200 }
    ),
    { x: 1012, y: 208, width: 800, height: 1200 }
  );
});

test("screen and viewport points round-trip in logical DIP", () => {
  const viewport = { x: 1000, y: 200, width: 800, height: 1200 };
  const screenPoint = { x: 1200, y: 500 };
  const viewportPoint = screenPointToViewportPoint(screenPoint, viewport);

  assert.deepEqual(viewportPoint, { x: 200, y: 300 });
  assert.deepEqual(viewportPointToScreenPoint(viewportPoint, viewport), screenPoint);
});

test("stale expected host coordinates cannot affect actual viewport conversion", () => {
  const expectedHost = { x: 1000, y: 200, width: 800, height: 1200 };
  const actualViewport = { x: 1025, y: 200, width: 800, height: 1200 };
  const anchor = { x: 1300, y: 900 };

  assert.equal(expectedHost.x, 1000);
  assert.deepEqual(screenPointToViewportPoint(anchor, actualViewport), {
    x: 275,
    y: 700
  });
});

test("native host movement cannot change a canonical global anchor", () => {
  const anchor = { x: 1800, y: 1200 };
  const before = { x: 1400, y: 100, width: 760, height: 1280 };
  const after = { x: 1450, y: 100, width: 760, height: 1280 };
  const beforeLocal = screenPointToViewportPoint(anchor, before);
  const afterLocal = screenPointToViewportPoint(anchor, after);

  assert.notDeepEqual(afterLocal, beforeLocal);
  assert.deepEqual(viewportPointToScreenPoint(beforeLocal, before), anchor);
  assert.deepEqual(viewportPointToScreenPoint(afterLocal, after), anchor);
});

test("host movement and resize preserve the model stable anchor on screen", () => {
  const anchor = { x: 1800, y: 1200 };
  const before = { x: 1400, y: 100, width: 760, height: 1280 };
  const moved = { x: 1450, y: 140, width: 760, height: 1280 };
  const resized = { x: 1350, y: 40, width: 1000, height: 1500 };

  for (const viewport of [before, moved, resized]) {
    const stableAnchor = resolveStableAnchorFromViewport(anchor, viewport);
    assert.ok(Math.abs(stableAnchor.x - anchor.x) < 0.01);
    assert.ok(Math.abs(stableAnchor.y - anchor.y) < 0.01);
  }
});

test("screen hit testing and projected bounds use the actual viewport", () => {
  const viewport = { x: -500, y: 100, width: 600, height: 900 };

  assert.equal(containsScreenPoint(viewport, { x: -500, y: 100 }), true);
  assert.equal(containsScreenPoint(viewport, { x: 100, y: 100 }), false);
  assert.deepEqual(
    screenBoundsFromViewport(
      { left: 40, top: 60, right: 240, bottom: 560 },
      viewport
    ),
    { left: -460, top: 160, right: -260, bottom: 660 }
  );
});

test("invalid or empty viewport observations fail closed", () => {
  assert.equal(
    resolveActualCanvasViewportBounds(
      { x: Number.NaN, y: 0 },
      { left: 0, top: 0, width: 800, height: 1200 }
    ),
    null
  );
  assert.equal(
    resolveActualCanvasViewportBounds(
      { x: 0, y: 0 },
      { left: 0, top: 0, width: 0, height: 1200 }
    ),
    null
  );
});
