const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../pet-electron/node_modules/typescript');
const backendRoot = path.resolve(__dirname, '../pet-electron/renderer/src/backend');

function fixture(realAudio = false) {
  const audios = [];
  const state = {};
  class Audio {
    constructor(src) { this.src = src; this.currentTime = 0; this.events = {}; audios.push(this); }
    addEventListener(name, cb) { this.events[name] = cb; }
    play() { return Promise.resolve(); }
    pause() {}
  }
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
      module, exports: module.exports, URL, Audio, WebSocket: Socket, console: { info() {}, warn() {} },
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
    { setMouthOpen() {}, setSpeaking() {}, setLipSyncValue() {} }, patch => Object.assign(state, patch));
  if (!realAudio) client.stopAudioPlayback = () => { client.currentAudio = null; client.audioQueue = []; };
  client.connect();
  const socket = sockets[0];
  socket.events.open();
  return { client, socket, timers, audios, state };
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
  assert.deepEqual(socket.sent.at(-1), { type: 'frontend-playback-complete', request_id: 'turn-1', status: 'completed' });
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

test('interrupt reports interruption rather than successful playback', () => {
  const { client, socket, timers } = fixture();
  client.handleMessage({ type: 'backend-synth-complete', request_id: 'old' });
  client.handleMessage({ type: 'control', text: 'interrupt' });
  timers.shift()();
  assert.equal(socket.sent.length, 2);
  assert.equal(socket.sent.at(-1).status, 'interrupted');
  assert.equal(client.playbackRequestId, undefined);
});


test('audio error is failed even when synthesis finishes normally', () => {
  const {client, socket, timers, audios} = fixture(true);
  client.stopSpeechLipSync = () => {};
  client.handleMessage({type: 'audio', audio: 'fixture', request_id: 't'});
  client.handleMessage({type: 'backend-synth-complete', request_id: 't'});
  audios[0].events.error();
  timers.at(-1)();
  assert.equal(socket.sent.at(-1).status, 'failed');
});

test('lip sync exception does not stop audio; late callback cannot clear new playback', () => {
  const {client, socket, timers, audios} = fixture(true);
  client.stopSpeechLipSync = () => {};
  client.beginSpeechLipSync = () => { throw Error('optional animation failed'); };
  client.handleMessage({type: 'audio', audio: 'fixture', request_id: 'old'});
  const old = audios[0];
  client.handleMessage({type: 'control', text: 'conversation-chain-start', request_id: 'new'});
  client.handleMessage({type: 'audio', audio: 'fixture', request_id: 'new'});
  old.events.ended();
  assert.equal(client.currentAudio, audios[1]);
  client.handleMessage({type: 'backend-synth-complete', request_id: 'new'});
  audios[1].events.ended();
  timers.at(-1)();
  assert.equal(socket.sent.at(-1).status, 'completed');
  assert.equal(socket.sent.at(-1).request_id, 'new');
});

test('standalone speech status reaches the presentation state', () => {
  const {client, state} = fixture();
  client.handleMessage({type: 'speech-status', status: 'unavailable', request_id: 't'});
  assert.equal(state.speechStatus, 'unavailable');
});

test('Pet keeps repeated Display deltas and acknowledges only ended segments', () => {
  const {client, state, socket, timers, audios} = fixture(true);
  client.stopSpeechLipSync = () => {};
  for (const text of ["説明", "説明", "\n  x = 1"]) {
    client.handleMessage({type: "audio", request_id: "scope", display_contract: "kuro.speech-lanes.v1",
      display_append: true, display_text: {text}});
  }
  assert.equal(state.latestAssistantText, "説明説明\n  x = 1");
  for (const id of [1,2,3]) client.handleMessage({type:"audio",request_id:"scope",audio:"fixture",segment_id:id});
  client.handleMessage({type:"backend-synth-complete",request_id:"scope"});
  audios[0].events.ended(); audios[1].events.error(); audios[2].events.ended();
  timers.at(-1)();
  assert.deepEqual(socket.sent.at(-1).ended_segments, [1,3]);
  assert.equal(socket.sent.at(-1).status, "failed");
});
