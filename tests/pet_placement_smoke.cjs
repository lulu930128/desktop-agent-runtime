// Production main/preload/renderer regression, isolated from all user services.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { app, BrowserWindow, screen } = require('electron');
const { modelIsVisible } = require('../pet-electron/src/main-process/pet-visibility');
const root = path.resolve(__dirname, '..');
const evidence = path.join(root, 'launcher_logs/work-panel-validation');
const profile = fs.mkdtempSync(path.join(evidence, 'pet-placement-'));
app.setPath('userData', profile);
Object.assign(process.env, {
  KURO_MAIL_BRIEFING_AUTO: '0', KURO_PET_CONTROL_PORT: '0',
  KURO_BACKEND_BASE_URL: 'http://127.0.0.1:1', KURO_BACKEND_WS_URL: 'ws://127.0.0.1:1/client-ws'
});
delete process.env.KURO_CORE_TOKEN;
delete process.env.KURO_LAUNCHER_CONTROL_TOKEN;
const model = JSON.parse(fs.readFileSync(path.join(root, 'Open-LLM-VTuber/model_dict.json'), 'utf8')).find(m => m.name === 'mao_pro');
process.env.KURO_PRESENTATION = JSON.stringify({ modelPath: model.url.replace('/live2d-models/', ''), confUid: 'fixture', confName: 'fixture', scaleWidth: Math.max(.8, model.kScale * 2) });
const stateFile = path.join(profile, 'pet-shell-state.json');
fs.writeFileSync(stateFile, JSON.stringify({ petAnchor: { x: 2142, y: 8515 }, petZoomScale: 1.53 }));
let readStatus;
const control = require('../pet-electron/src/main-process/control-server');
const startControl = control.startControlServer;
control.startControlServer = options => { readStatus = options.getShellStatus; return startControl(options); };
require('../pet-electron/src/main.js');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const checks = [];
let pet;
async function until(predicate, label) {
  for (let i = 0; i < 120; i++) {
    if (await predicate()) return;
    await delay(100);
  }
  throw new Error(`Timed out: ${label}`);
}
async function dragTo(anchor) {
  await pet.webContents.executeJavaScript(`(() => {
    const api = window.kuroPetElectron;
    api.updateComponentHover('live2d-model', true);
    api.startWindowDrag(100, 100);
    api.requestPetTransform({ kind: 'anchor', requestedAnchor: ${JSON.stringify(anchor)} });
  })()`);
  await until(() => readStatus().petAnchor.x === anchor.x && readStatus().petAnchor.y === anchor.y, 'drag accepted');
  await pet.webContents.executeJavaScript('window.kuroPetElectron.endWindowDrag()');
  await delay(2200); // Includes two real renderer envelope heartbeats after release.
  assert.deepEqual(readStatus().petAnchor, anchor, 'drag release must not snap the anchor back');
  assert.deepEqual(JSON.parse(fs.readFileSync(stateFile, 'utf8')).petAnchor, anchor, 'chosen position persisted');
}
async function run() {
  await until(() => {
    pet = BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('/index.html'));
    return pet && readStatus && modelIsVisible(readStatus().petModelScreenBounds, screen.getAllDisplays());
  }, 'offscreen startup recovery');
  checks.push('offscreen saved position recovers using real model bounds');
  const start = readStatus().petAnchor;
  await dragTo({ x: start.x - 180, y: start.y + 240 });
  checks.push('oversized model stays at a partially offscreen position after drag release');
  const other = screen.getAllDisplays().at(-1).workArea;
  await dragTo({ x: other.x + other.width / 2, y: other.y + other.height + 100 });
  checks.push('drag across actual displays preserves the selected position');
  const beforeZoom = readStatus();
  const pivot = { x: beforeZoom.petAnchor.x, y: beforeZoom.petAnchor.y - 400 };
  await pet.webContents.executeJavaScript(`window.kuroPetElectron.requestPetTransform({kind: 'zoom', scaleFactor: 1.1, pivotScreenPoint: ${JSON.stringify(pivot)}})`);
  await until(() => readStatus().petTransformRevision > beforeZoom.petTransformRevision, 'zoom accepted');
  const zoomed = readStatus();
  await delay(2200);
  assert.deepEqual(readStatus().petAnchor, zoomed.petAnchor, 'zoom release must not snap the anchor back');
  assert.equal(readStatus().petTransformRevision, zoomed.petTransformRevision, 'animation must not advance the user transform');
  checks.push('zoom and animation do not relocate or repeatedly revise the anchor');
  await dragTo({ x: 20000, y: 20000 });
  screen.emit('display-metrics-changed', {}, screen.getPrimaryDisplay(), ['workArea']);
  await until(() => modelIsVisible(readStatus().petModelScreenBounds, screen.getAllDisplays()), 'topology recovery');
  const recovered = readStatus();
  await delay(2200);
  assert.deepEqual(readStatus().petAnchor, recovered.petAnchor);
  assert.equal(readStatus().petTransformRevision, recovered.petTransformRevision);
  checks.push('display topology event recovers lost model once without a correction loop');
  assert.equal(readStatus().forceIgnoreMouse, false, 'new profile defaults to mouse passthrough off');
  checks.push('mouse passthrough defaults off in the real startup path');
  fs.writeFileSync(path.join(evidence, 'pet-placement-result.json'), JSON.stringify({ ok: true, checkedAt: new Date().toISOString(), checks, profile }, null, 2));
  app.exit(0);
}
const timeout = setTimeout(() => { console.error('Placement smoke timed out'); app.exit(1); }, 50000);
app.whenReady().then(run).catch(error => {
  fs.writeFileSync(path.join(evidence, 'pet-placement-result.json'), JSON.stringify({ ok: false, error: String(error.stack), checks, profile, anchor: readStatus?.().petAnchor }, null, 2));
  app.exit(1);
}).finally(() => clearTimeout(timeout));
