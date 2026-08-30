const assert = require("node:assert/strict");
const test = require("node:test");

const {
  canMutateFixedPetShell,
  resolveFixedDesktopShellBounds
} = require("../pet-electron/src/main-process/pet-fixed-shell");

test("fixed shell uses the union of physical display bounds", () => {
  const bounds = resolveFixedDesktopShellBounds([
    { id: 1, bounds: { x: -1920, y: 120, width: 1920, height: 1080 } },
    { id: 2, bounds: { x: 0, y: 0, width: 2560, height: 1440 } }
  ]);

  assert.deepEqual(bounds, { x: -1920, y: 0, width: 4480, height: 1440 });
});

test("fixed shell includes taskbar space instead of shrinking to workArea", () => {
  const bounds = resolveFixedDesktopShellBounds([
    {
      id: 1,
      bounds: { x: 0, y: 0, width: 2560, height: 1440 },
      workArea: { x: 0, y: 0, width: 2560, height: 1400 }
    }
  ]);

  assert.equal(bounds.height, 1440);
});

test("normal model interaction cannot mutate a fixed native shell", () => {
  assert.equal(canMutateFixedPetShell("startup"), true);
  assert.equal(canMutateFixedPetShell("display-topology"), true);
  assert.equal(canMutateFixedPetShell("mode-switch"), true);
  assert.equal(canMutateFixedPetShell("recovery"), true);
  assert.equal(canMutateFixedPetShell("model-envelope"), false);
  assert.equal(canMutateFixedPetShell("drag"), false);
  assert.equal(canMutateFixedPetShell("zoom"), false);
});
