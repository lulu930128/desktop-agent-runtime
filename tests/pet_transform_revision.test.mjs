import assert from "node:assert/strict";
import test from "node:test";

import { resolveAuthoritativePetTransform } from "../pet-electron/renderer/src/interaction/pet-transform-revision.ts";

test("renderer rejects out-of-order authoritative transforms", () => {
  let current = {
    revision: 10,
    anchor: { x: 1000, y: 1000 },
    zoomScale: 1
  };

  for (const incoming of [
    { revision: 12, anchor: { x: 1200, y: 1200 }, zoomScale: 1.2 },
    { revision: 11, anchor: { x: 1100, y: 1100 }, zoomScale: 1.1 }
  ]) {
    current = resolveAuthoritativePetTransform(current, incoming).state;
  }

  assert.equal(current.revision, 12);
  assert.deepEqual(current.anchor, { x: 1200, y: 1200 });
  assert.equal(current.zoomScale, 1.2);
});

test("duplicate revisions do not reapply transform state", () => {
  const current = {
    revision: 4,
    anchor: { x: 800, y: 900 },
    zoomScale: 1.5
  };
  const result = resolveAuthoritativePetTransform(current, {
    revision: 4,
    anchor: { x: 0, y: 0 },
    zoomScale: 0.2
  });

  assert.equal(result.accepted, false);
  assert.deepEqual(result.state, current);
});
