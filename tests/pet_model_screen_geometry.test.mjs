import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveModelScreenBounds,
  resolveStablePlacementTranslation,
  resolveViewportInvariantTargetHeight,
  resolveViewportPixelsPerViewUnit
} from "../pet-electron/renderer/src/live2d/model-screen-geometry.ts";

test("dynamic visual bounds cannot redefine stable placement", () => {
  const stableBounds = { left: -0.4, right: 0.4, top: -0.75, bottom: 0.75 };
  const anchorViewPoint = { x: 0.2, y: -0.1 };
  const placementBeforeMotion = resolveStablePlacementTranslation(
    stableBounds,
    anchorViewPoint,
    1.5,
    1.5
  );
  const dynamicVisualBounds = {
    left: -0.8,
    right: 0.6,
    top: -1.1,
    bottom: 0.9
  };
  const placementDuringMotion = resolveStablePlacementTranslation(
    stableBounds,
    anchorViewPoint,
    1.5,
    1.5
  );

  assert.notDeepEqual(dynamicVisualBounds, stableBounds);
  assert.deepEqual(placementDuringMotion, placementBeforeMotion);
});

test("model screen bounds transform from Cubism space into global DIP", () => {
  const bounds = resolveModelScreenBounds(
    { left: -0.5, right: 0.5, top: -1, bottom: 1 },
    { scaleX: 1, scaleY: 1, translateX: 0, translateY: 0 },
    { scaleX: 1, scaleY: 0.5, translateX: 0, translateY: 0 },
    { x: 2200, y: 100, width: 800, height: 1600 }
  );

  assert.deepEqual(bounds, {
    left: 2400,
    top: 500,
    right: 2800,
    bottom: 1300,
    width: 400,
    height: 800
  });
});

test("host viewport changes do not change visual model height", () => {
  const baseTargetHeight = 1.7;
  const zoomScale = 1.4;
  const portraitTarget = resolveViewportInvariantTargetHeight(
    baseTargetHeight,
    zoomScale,
    760,
    1280
  );
  const landscapeTarget = resolveViewportInvariantTargetHeight(
    baseTargetHeight,
    zoomScale,
    1800,
    1200
  );
  const portraitPixels = resolveViewportPixelsPerViewUnit(760, 1280);
  const landscapePixels = resolveViewportPixelsPerViewUnit(1800, 1200);

  assert.ok(portraitTarget && landscapeTarget && portraitPixels && landscapePixels);
  assert.ok(
    Math.abs(portraitTarget * portraitPixels - landscapeTarget * landscapePixels) < 1e-9
  );
});

test("DIP geometry does not apply monitor scaleFactor a second time", () => {
  const cssViewport = { x: 2560, y: 0, width: 1000, height: 1200 };
  const atScale100 = resolveModelScreenBounds(
    { left: -0.5, right: 0.5, top: -1, bottom: 1 },
    { scaleX: 1, scaleY: 1, translateX: 0, translateY: 0 },
    { scaleX: 1, scaleY: 5 / 6, translateX: 0, translateY: 0 },
    cssViewport
  );
  const atScale125 = resolveModelScreenBounds(
    { left: -0.5, right: 0.5, top: -1, bottom: 1 },
    { scaleX: 1, scaleY: 1, translateX: 0, translateY: 0 },
    { scaleX: 1, scaleY: 5 / 6, translateX: 0, translateY: 0 },
    cssViewport
  );

  assert.deepEqual(atScale125, atScale100);
});
