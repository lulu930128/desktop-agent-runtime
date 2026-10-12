const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../pet-electron/node_modules/typescript');
const backendRoot = path.resolve(__dirname, '../pet-electron/renderer/src/backend');

function fixture() {
  const timers = [];
  const sockets = [];
  class Socket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 1; this.events = {}; this.sent = []; sockets.push(this); }
    addEventListener(kind, callback) { this.events[kind] = callback; }
    send(raw) { this.sent.push(JSON.parse(raw)); }
    close() { this.readyState = 3; }
  }
  const cache = new Map();
  function load(filename) {
    filename = path.resolve(filename);
    if (cache.has(filename)) return cache.get(filename);
    const js = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
    }).outputText;
    const module = { exports: {} };
    cache.set(filename, module.exports);
    vm.runInNewContext(js, {
      module, exports: module.exports, URL, WebSocket: Socket, console: { info() {}, warn() {} },
      btoa: value => Buffer.from(value, 'binary').toString('base64'),
      window: { setTimeout(callback) { timers.push(callback); return timers.length; }, clearTimeout() {} },
      performance: { now: () => 0 },
      require(relative) {
        if (relative.includes('pet-live2d-renderer')) return {};
        return load(path.resolve(path.dirname(filename), relative + '.ts'));
      },
    }, { filename });
    return module.exports;
  }
  const { BackendClient } = load(path.join(backendRoot, 'backend-client.ts'));
  const client = new BackendClient({ wsUrl: 'ws://localhost:23456/client-ws?fixture=1', baseUrl: 'http://localhost:23456' },
    { setMouthOpen() {}, setSpeaking() {} }, () => {});
  client.stopAudioPlayback = () => { client.currentAudio = null; client.audioQueue = []; };
  client.connect();
  const socket = sockets[0];
  socket.events.open();
  return { client, socket, timers };
}

test('canonical Pet URL and init never create history', () => {
  const { socket } = fixture();
  const url = new URL(socket.url);
  assert.equal(url.searchParams.get('client_role'), 'pet-presentation');
  assert.equal(url.searchParams.get('fixture'), '1');
  assert.deepEqual(socket.sent, [{ type: 'request-init-config' }]);
});

test('Pet captures audio for Qt but never sends a conversation trigger', async () => {
  const { client, socket } = fixture();
  client.micSamples = [0, 1, -1];
  client.stopMicrophoneNodes = () => {};
  client.captureEnabledImages = async () => [];
  const result = await client.controlMicrophone('submit');
  assert.equal(result.ok, true);
  assert.equal(result.capture.format, 'pcm16le');
  assert.equal(Buffer.from(result.capture.data, 'base64').readInt16LE(2), 32767);
  assert.deepEqual(socket.sent, [{ type: 'request-init-config' }]);
  assert.equal(typeof client.sendText, 'undefined');
  assert.equal(typeof client.sendInterrupt, 'undefined');
});

test('local playback stop never controls the Qt conversation', () => {
  const { client, socket } = fixture();
  client.stopPlayback();
  assert.deepEqual(socket.sent, [{ type: 'request-init-config' }]);
});

test('reconfiguration cannot promote Pet to a controllable frontend', () => {
  const { client } = fixture();
  const config = client.applyConfig('http://localhost:12345', 'ws://localhost:12345/client-ws?client_role=frontend', false);
  assert.equal(new URL(config.wsUrl).searchParams.get('client_role'), 'pet-presentation');
});

test('Pet acknowledges only after actual playback queue drains', () => {
  const { client, socket, timers } = fixture();
  client.currentAudio = {};
  client.handleMessage({ type: 'backend-synth-complete', request_id: 'turn-1' });
  assert.equal(timers.length, 0);
  client.currentAudio = null;
  client.audioQueue = ['fixture'];
  client.maybeNotifyPlaybackComplete();
  assert.equal(timers.length, 0);
  client.audioQueue = [];
  client.maybeNotifyPlaybackComplete();
  timers.shift()();
  assert.deepEqual(socket.sent.at(-1), { type: 'frontend-playback-complete', request_id: 'turn-1' });
});

test('stale playback timer cannot acknowledge a later turn', () => {
  const { client, socket, timers } = fixture();
  client.handleMessage({ type: 'backend-synth-complete', request_id: 'old' });
  const stale = timers.shift();
  client.resetPlaybackTurn();
  client.handleMessage({ type: 'backend-synth-complete', request_id: 'new' });
  stale();
  assert.equal(socket.sent.length, 1);
  timers.shift()();
  assert.equal(socket.sent.at(-1).request_id, 'new');
});

test('interrupt resets pending playback without inventing completion', () => {
  const { client, socket, timers } = fixture();
  client.handleMessage({ type: 'backend-synth-complete', request_id: 'old' });
  client.handleMessage({ type: 'control', text: 'interrupt' });
  timers.shift()();
  assert.equal(socket.sent.length, 1);
  assert.equal(client.playbackRequestId, undefined);
});
