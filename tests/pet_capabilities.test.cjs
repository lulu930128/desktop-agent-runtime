const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { resolveAsset, normalizePresentation } = require('../pet-electron/src/main-process/local-model');
const { repairPlacement, modelIsVisible } = require('../pet-electron/src/main-process/pet-visibility');
const displays = [{ workArea: { x: -1920, y: 0, width: 1920, height: 1080 } }, { workArea: { x: 0, y: 0, width: 2560, height: 1440 } }];
test('offscreen saved anchor recovers; valid negative coordinates remain unchanged', () => {
  assert.deepEqual(repairPlacement({ x: -300, y: 900 }, displays), { x: -300, y: 900 });
  assert.deepEqual(repairPlacement({ x: 2142, y: 2515 }, displays), { x: 2142, y: 1416 });
});
test('actual model bounds recover into one display, independently of its transparent host', () => {
  const bounds = { left: 1742, top: 1600, right: 2542, bottom: 2515 };
  assert.equal(modelIsVisible(bounds, displays), false);
  const anchor = repairPlacement({ x: 2142, y: 2515 }, displays, bounds);
  const delta = anchor.y - 2515;
  assert.equal(modelIsVisible({ ...bounds, top: bounds.top + delta, bottom: bounds.bottom + delta }, displays), true);
});
test('usable clipped, oversized and cross-display models retain the user anchor', () => {
  const anchor = { x: 1400, y: 1800 };
  for (const bounds of [
    { left: 1000, top: 900, right: 1800, bottom: 1800 },
    { left: -200, top: -900, right: 3000, bottom: 1800 },
    { left: -400, top: 700, right: 400, bottom: 1500 }
  ]) {
    assert.equal(modelIsVisible(bounds, displays), true);
    assert.deepEqual(repairPlacement(anchor, displays, bounds), anchor);
  }
});
test('a tiny ungrabbable sliver still qualifies for explicit recovery', () => {
  const bounds = { left: 2550, top: 900, right: 3000, bottom: 1400 };
  const anchor = { x: 2800, y: 1400 };
  assert.equal(modelIsVisible(bounds, displays), false);
  assert.notDeepEqual(repairPlacement(anchor, displays, bounds), anchor);
});
test('local asset gateway rejects traversal, absolute paths, unknown models and private extensions', () => {
  const root = fs.mkdtempSync(path.join(__dirname, '../launcher_logs/model-fixture-'));
  try {
    fs.mkdirSync(path.join(root, 'live2d-models'));
    fs.writeFileSync(path.join(root, 'secret.json'), '{}');
    fs.writeFileSync(path.join(root, 'live2d-models', 'private.txt'), 'fixture');
    fs.writeFileSync(path.join(root, 'model_dict.json'), '[]');
    for (const file of ['../secret.json', path.join(root, 'secret.json'), 'private.txt']) assert.throws(() => resolveAsset(path.join(root, 'live2d-models'), file));
    assert.throws(() => normalizePresentation(root, { modelPath: 'unknown.model3.json', scaleWidth: 1 }));
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
