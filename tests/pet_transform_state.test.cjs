const assert = require("node:assert/strict");
const test = require("node:test");

const {
  advancePetTransformState,
  applyPetTransformRequest,
  createPetTransformState,
  isCurrentTransformRevision
} = require("../pet-electron/src/main-process/pet-transform-state");
const { mergeState } = require("../pet-electron/src/state");

test("main-owned transform increments one monotonic revision per change", () => {
  const initial = createPetTransformState({
    revision: 10,
    anchor: { x: 1000, y: 1200 },
    zoomScale: 1
  });
  const changed = advancePetTransformState(initial, {
    anchor: { x: 1010, y: 1190 }
  });
  const unchanged = advancePetTransformState(changed.state, {
    anchor: { x: 1010, y: 1190 }
  });

  assert.equal(changed.changed, true);
  assert.equal(changed.state.revision, 11);
  assert.equal(unchanged.changed, false);
  assert.equal(unchanged.state.revision, 11);
});

test("rapid authoritative zoom in and out remains pivot reversible", () => {
  const initial = createPetTransformState({
    revision: 1,
    anchor: { x: 1800, y: 1416 },
    zoomScale: 1
  });
  const pivotScreenPoint = { x: 1700, y: 900 };
  let current = initial;

  for (let index = 0; index < 20; index += 1) {
    current = applyPetTransformRequest(current, {
      kind: "zoom",
      scaleFactor: 1.06,
      pivotScreenPoint
    }).state;
  }
  for (let index = 0; index < 20; index += 1) {
    current = applyPetTransformRequest(current, {
      kind: "zoom",
      scaleFactor: 1 / 1.06,
      pivotScreenPoint
    }).state;
  }

  assert.ok(Math.abs(current.anchor.x - initial.anchor.x) < 0.01);
  assert.ok(Math.abs(current.anchor.y - initial.anchor.y) < 0.01);
  assert.ok(Math.abs(current.zoomScale - initial.zoomScale) < 1e-12);
  assert.equal(current.revision, 41);
});

test("envelopes accept only the exact current transform revision", () => {
  const current = createPetTransformState({
    revision: 20,
    anchor: { x: 1000, y: 1000 },
    zoomScale: 1.4
  });

  assert.equal(isCurrentTransformRevision(current, 19), false);
  assert.equal(isCurrentTransformRevision(current, 20), true);
  assert.equal(isCurrentTransformRevision(current, 21), false);
});

test("invalid transform requests cannot mutate canonical state", () => {
  const current = createPetTransformState({
    revision: 7,
    anchor: { x: 1000, y: 1000 },
    zoomScale: 1
  });
  const result = applyPetTransformRequest(current, {
    kind: "zoom",
    scaleFactor: Number.NaN,
    pivotScreenPoint: { x: 900, y: 800 }
  });

  assert.equal(result.accepted, false);
  assert.deepEqual(result.state, current);
});

test("persisted pet anchors preserve sub-DIP transform precision", () => {
  const merged = mergeState({
    petAnchor: { x: 1000.125, y: 1200.875 },
    petZoomScale: 1.06
  });

  assert.deepEqual(merged.petAnchor, { x: 1000.125, y: 1200.875 });
});
