import assert from "node:assert/strict";
import test from "node:test";

import { applyPetGeometryCommand } from "../pet-electron/renderer/src/commands/pet-command-geometry.ts";

function createFakeRenderer() {
  return {
    revision: 12,
    anchor: { x: 1000, y: 1000 },
    zoomScale: 1.2,
    expectedHostBounds: { x: 0, y: 0, width: 800, height: 1200 },
    applyAuthoritativeTransform(transform) {
      if (transform.revision <= this.revision) return false;
      this.revision = transform.revision;
      this.anchor = { ...transform.anchor };
      this.zoomScale = transform.zoomScale;
      return true;
    },
    getTransformRevision() {
      return this.revision;
    },
    getZoomScale() {
      return this.zoomScale;
    },
    setExpectedHostBounds(bounds) {
      this.expectedHostBounds = { ...bounds };
    }
  };
}

test("host updates cannot mutate canonical anchor or zoom", () => {
  const renderer = createFakeRenderer();
  const before = {
    anchor: { ...renderer.anchor },
    zoomScale: renderer.zoomScale
  };

  applyPetGeometryCommand(renderer, {
    type: "pet-host-set",
    transformRevision: 12,
    petHostBounds: { x: 100, y: 100, width: 900, height: 1300 },
    petAnchor: { x: 0, y: 0 },
    zoomScale: 8
  });

  assert.deepEqual(renderer.anchor, before.anchor);
  assert.equal(renderer.zoomScale, before.zoomScale);
  assert.deepEqual(renderer.expectedHostBounds, {
    x: 100,
    y: 100,
    width: 900,
    height: 1300
  });
});

test("stale host revisions cannot replace newer expected-host telemetry", () => {
  const renderer = createFakeRenderer();
  const before = { ...renderer.expectedHostBounds };

  applyPetGeometryCommand(renderer, {
    type: "pet-host-set",
    transformRevision: 11,
    petHostBounds: { x: -500, y: -500, width: 200, height: 200 }
  });

  assert.deepEqual(renderer.expectedHostBounds, before);
});

test("host updates without a valid transform revision fail closed", () => {
  const renderer = createFakeRenderer();
  const before = { ...renderer.expectedHostBounds };

  applyPetGeometryCommand(renderer, {
    type: "pet-host-set",
    petHostBounds: { x: -500, y: -500, width: 200, height: 200 }
  });

  assert.deepEqual(renderer.expectedHostBounds, before);
});

test("host updates for a future transform wait for that transform revision", () => {
  const renderer = createFakeRenderer();
  const before = { ...renderer.expectedHostBounds };

  applyPetGeometryCommand(renderer, {
    type: "pet-host-set",
    transformRevision: 13,
    petHostBounds: { x: 100, y: 100, width: 900, height: 1300 }
  });

  assert.deepEqual(renderer.expectedHostBounds, before);
});
