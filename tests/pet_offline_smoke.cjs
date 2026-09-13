// Runs the production main/preload/renderer with isolated state and no providers.
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { app, BrowserWindow } = require('electron');
const root = path.resolve(__dirname, '..');
const evidence = path.join(root, 'launcher_logs', 'work-panel-validation');
fs.mkdirSync(evidence, { recursive: true });
const profile = fs.mkdtempSync(path.join(evidence, 'pet-offline-'));
app.setPath('userData', profile);
process.env.KURO_MAIL_BRIEFING_AUTO = '0';
process.env.KURO_PET_CONTROL_PORT = '0';
process.env.KURO_BACKEND_BASE_URL = 'http://127.0.0.1:1';
process.env.KURO_BACKEND_WS_URL = 'ws://127.0.0.1:1/client-ws';
delete process.env.KURO_CORE_TOKEN;
delete process.env.KURO_LAUNCHER_CONTROL_TOKEN;
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'Open-LLM-VTuber/model_dict.json'), 'utf8'));
const model = catalog.find(m => m.name === 'mao_pro');
process.env.KURO_PRESENTATION = JSON.stringify({ modelPath: model.url.replace('/live2d-models/', ''), confUid: 'fixture', confName: 'fixture', scaleWidth: Math.max(.8, model.kScale * 2) });
fs.writeFileSync(path.join(profile, 'pet-shell-state.json'), JSON.stringify({ petAnchor: { x: 2142, y: 2515 }, petZoomScale: 1.53 }));
require('../pet-electron/src/main.js');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let status;
async function run() {
  for (let i = 0; i < 120; i++) {
    const pet = BrowserWindow.getAllWindows().find(w => w.webContents.getURL().includes('/index.html'));
    if (pet) {
      status = await pet.webContents.executeJavaScript('window.__kuroLive2DInspector?.getSnapshot()');
      if (status?.ready && status.modelScreenBounds) {
        const { modelIsVisible } = require('../pet-electron/src/main-process/pet-visibility');
        if (modelIsVisible(status.modelScreenBounds, require('electron').screen.getAllDisplays())) {
          const backend = await pet.webContents.executeJavaScript('window.__kuroPetRendererState.wsConnected');
          assert.equal(backend, false);
          assert.ok(status.modelUrl.startsWith('kuro-model://local/'));
          await delay(300);
          fs.writeFileSync(path.join(evidence, 'pet-offline.png'), (await pet.webContents.capturePage()).toPNG());
          fs.writeFileSync(path.join(evidence, 'pet-offline-result.json'), JSON.stringify({ ok: true, checkedAt: new Date().toISOString(), profile,
            checks: ['production main/preload/renderer', 'local model loads without LLM', 'real model bounds visible after saved offscreen position', 'backend remains offline'],
            modelUrl: status.modelUrl, bounds: status.modelScreenBounds, anchor: status.anchorScreenPoint }, null, 2));
          app.exit(0);
          return;
        }
      }
    }
    await delay(250);
  }
  throw new Error('Offline model not ready/visible: ' + JSON.stringify(status));
}
app.whenReady().then(() => delay(500)).then(run).catch(error => {
  fs.writeFileSync(path.join(evidence, 'pet-offline-result.json'), JSON.stringify({ ok: false, error: String(error.stack), profile }, null, 2));
  app.exit(1);
});
