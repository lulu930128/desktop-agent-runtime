const assert = require("node:assert/strict");
const test = require("node:test");

const {
  resolvePetMousePolicy
} = require("../pet-electron/src/main-process/pet-mouse-policy");

function resolve(overrides = {}) {
  return resolvePetMousePolicy({
    mode: "pet",
    petGameMode: false,
    forceIgnoreMouse: false,
    interactiveHover: false,
    ...overrides
  });
}

test("window mode remains interactive", () => {
  const policy = resolve({ mode: "window", forceIgnoreMouse: true });
  assert.equal(policy.ignoreMouseEvents, false);
  assert.equal(policy.mode, "window-interactive");
});

test("enabled mouse passthrough ignores the entire pet host", () => {
  const policy = resolve({ forceIgnoreMouse: true, interactiveHover: true });
  assert.equal(policy.ignoreMouseEvents, true);
  assert.equal(policy.mode, "full-passthrough");
});

test("disabled mouse passthrough keeps transparent pixels click-through", () => {
  const policy = resolve({ forceIgnoreMouse: false, interactiveHover: false });
  assert.equal(policy.ignoreMouseEvents, true);
  assert.equal(policy.mode, "transparent-passthrough");
});

test("disabled mouse passthrough makes only the hovered model interactive", () => {
  const policy = resolve({ forceIgnoreMouse: false, interactiveHover: true });
  assert.equal(policy.ignoreMouseEvents, false);
  assert.equal(policy.mode, "model-interactive");
});

test("game mode always passes mouse input through", () => {
  const policy = resolve({ petGameMode: true, interactiveHover: true });
  assert.equal(policy.ignoreMouseEvents, true);
  assert.equal(policy.mode, "game-passthrough");
});
