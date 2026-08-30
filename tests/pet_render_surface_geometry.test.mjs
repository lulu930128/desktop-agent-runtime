import assert from "node:assert/strict";
import test from "node:test";

import {
  createInitialPetRenderSurface,
  resolvePetRenderSurfaceAction,
  resolvePetRenderSurfaceEnvelope,
  surfaceContainsModelBounds,
  translatePetRenderSurfaceToAnchor
} from "../pet-electron/renderer/src/geometry/pet-render-surface-geometry.ts";

const shell = { x: -1920, y: 0, width: 4480, height: 1440 };

test("initial compact surface is positioned inside shell coordinates without filling it", () => {
  const state = createInitialPetRenderSurface(shell, { x: 1800, y: 1416 }, 12);

  assert.ok(state);
  assert.deepEqual(state.screenBounds, { x: 1420, y: 160, width: 760, height: 1280 });
  assert.deepEqual(state.localBounds, { x: 3340, y: 160, width: 760, height: 1280 });
  assert.ok(state.localBounds.width < shell.width);
});

test("anchor movement translates only the compact surface and preserves its size", () => {
  const initial = createInitialPetRenderSurface(shell, { x: 1800, y: 1416 }, 12);
  const moved = translatePetRenderSurfaceToAnchor(initial, shell, { x: 2800, y: 900 }, 13);

  assert.ok(moved);
  assert.deepEqual(moved.screenBounds, { x: 2420, y: -356, width: 760, height: 1280 });
  assert.deepEqual(moved.anchorScreenPoint, { x: 2800, y: 900 });
  assert.equal(moved.transformRevision, 13);
});

test("dynamic model bounds resize the surface without clamping offscreen placement", () => {
  const state = resolvePetRenderSurfaceEnvelope(
    { left: -700, top: -1600, right: 3300, bottom: 2400 },
    shell,
    { x: 1800, y: 2400 },
    14
  );

  assert.ok(state);
  assert.deepEqual(state.screenBounds, { x: -796, y: -1696, width: 4192, height: 4192 });
  assert.deepEqual(state.localBounds, { x: 1124, y: -1696, width: 4192, height: 4192 });
  assert.equal(
    surfaceContainsModelBounds(state.screenBounds, {
      left: -700,
      top: -1600,
      right: 3300,
      bottom: 2400
    }),
    true
  );
});

test("surface envelope grows immediately, shrinks lazily, and ignores pose jitter", () => {
  const current = { x: 100, y: 100, width: 800, height: 1200 };
  assert.equal(
    resolvePetRenderSurfaceAction(current, { x: 60, y: 100, width: 880, height: 1200 }),
    "apply"
  );
  assert.equal(
    resolvePetRenderSurfaceAction(current, { x: 180, y: 180, width: 640, height: 1000 }),
    "shrink"
  );
  assert.equal(
    resolvePetRenderSurfaceAction(current, { x: 116, y: 100, width: 800, height: 1200 }),
    "keep"
  );
});
