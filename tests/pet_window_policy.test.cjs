const assert = require("node:assert/strict");
const test = require("node:test");

const {
  PET_ALWAYS_ON_TOP_LEVEL,
  resolvePetWindowPolicy
} = require("../pet-electron/src/main-process/pet-window-policy");

test("pet mode is non-focusable and stays in the screen-saver topmost band", () => {
  const policy = resolvePetWindowPolicy({ mode: "pet" });

  assert.equal(policy.mode, "pet-topmost");
  assert.equal(policy.focusable, false);
  assert.equal(policy.alwaysOnTop, true);
  assert.equal(policy.alwaysOnTopLevel, PET_ALWAYS_ON_TOP_LEVEL);
  assert.equal(policy.visibleOnAllWorkspaces, true);
  assert.equal(policy.visibleOnFullScreen, true);
  assert.equal(policy.moveTopOnShow, true);
});

test("window mode remains focusable without forcing topmost z-order", () => {
  const policy = resolvePetWindowPolicy({ mode: "window" });

  assert.equal(policy.mode, "window-normal");
  assert.equal(policy.focusable, true);
  assert.equal(policy.alwaysOnTop, false);
  assert.equal(policy.visibleOnAllWorkspaces, false);
  assert.equal(policy.moveTopOnShow, false);
});
