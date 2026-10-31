const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../pet-electron/node_modules/typescript');
const root = path.resolve(__dirname, '../devtools/original-git-web-host-20261010/frontend/src');
function load(name, injected = {}) {
  const source = fs.readFileSync(path.join(root, name + '.ts'), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText;
  const m = {exports: {}};
  new Function('require', 'module', 'exports', ...Object.keys(injected), code)(r => load(path.join(path.dirname(name), r)), m, m.exports, ...Object.values(injected));
  return m.exports;
}
function harness() {
  const sent = []; let response, event;
  const {OwnerTransport, makeOwnerBridge} = load('owner-bridge');
  const t = new OwnerTransport({submit: raw => sent.push(JSON.parse(raw)), response: {connect: cb => response = cb}, event: {connect: cb => event = cb}}, 100);
  t.identity = {client: 'c', actor: 'kuro_01', context: 'x', history: '', revision: 1};
  const bridge = makeOwnerBridge(t);
  const states = [];
  t.on('onHistoryReadState', state => states.push(state));
  const reply = (result, req = sent.at(-1), identity = req.expected) => response(JSON.stringify({contract: 'kuro.qt.work.v1', id: req.id, expected: req.expected, identity, result}));
  const chat = value => event(JSON.stringify({contract: 'kuro.qt.work.v1', name: 'onChatState', identity: t.identity, value}));
  return {t, bridge, sent, reply, chat, states};
}
const rows = Array.from({length: 22}, (_, i) => ({uid: `anonymous-${i}`, title: 'SYNTHETIC'}));
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

test('failed list rejects so immutable renderer cannot fall back to an ok empty transcript', async () => {
  const h = harness();
  const pending = h.bridge.getHistories();
  h.reply({ok: false, error: 'history_owner_rejected'});
  await assert.rejects(pending, /history_owner_rejected/);
  assert.deepEqual(h.sent.map(r => r.method), ['getHistories']);
  assert.equal(h.states.at(-1).state, 'failed');
});

test('startup not ready waits for ready then returns the real list with empty selected UID', async () => {
  const h = harness();
  const pending = h.bridge.getHistories();
  h.reply({ok: false, error: 'conversation_not_ready'});
  await flush();
  assert.equal(h.sent.length, 1);
  assert.equal(h.states.at(-1).state, 'loading');
  h.chat({wsConnected: true, historyReady: true});
  await flush();
  assert.equal(h.sent.length, 2);
  h.reply({ok: true, histories: rows, current_history_uid: '', historyUid: ''});
  assert.equal((await pending).histories.length, 22);
  assert.equal(h.t.identity.history, '');
  assert.equal(h.states.at(-1).state, 'ready');
});

test('repeated open reads coalesce while pending and next open performs a fresh owner read', async () => {
  const h = harness();
  const first = h.bridge.getHistories();
  const second = h.bridge.getHistories();
  assert.equal(h.sent.length, 1);
  h.reply({ok: true, histories: rows});
  assert.equal((await first).histories.length, 22);
  assert.equal((await second).histories.length, 22);
  const reopened = h.bridge.getHistories();
  assert.equal(h.sent.length, 2);
  h.reply({ok: true, histories: []});
  assert.deepEqual((await reopened).histories, []);
  assert.equal(h.states.at(-1).state, 'ready');
});

test('old identity response cannot clear a newer list; only a serialized fresh read may complete', async () => {
  const h = harness();
  const pending = h.bridge.getHistories();
  const old = h.sent[0];
  h.t.notify('onChatState', {wsConnected: true, historyReady: false});
  h.t.identity = {...h.t.identity, context: 'new-context', revision: 2};
  h.t.notify('onIdentityChange', h.t.identity);
  h.chat({wsConnected: true, historyReady: true});
  h.reply({ok: true, histories: []}, old, old.expected);
  await flush();
  assert.equal(h.sent.length, 2);
  assert.equal(h.sent[1].expected.context, 'new-context');
  h.reply({ok: true, histories: rows});
  assert.equal((await pending).histories.length, 22);
  assert.equal(h.t.identity.context, 'new-context');
});

test('malformed success is a failure, and owner readiness wait is bounded', async () => {
  const h = harness();
  const malformed = h.bridge.getHistories();
  h.reply({ok: true, messages: []});
  await assert.rejects(malformed, /history_list_invalid/);
  const {createHistoryListReader} = load('owner-bridge');
  const read = createHistoryListReader(h.t, 5);
  const pending = read();
  h.reply({ok: false, error: 'conversation_not_ready'});
  await assert.rejects(pending, /history_ready_timeout/);
});

// Load the unchanged renderer itself: this observes its real failure/fallback branch.
test('immutable renderer displays a list failure instead of a definitive zero count', async () => {
  const h = harness();
  let fallbackCalls = 0;
  h.bridge.getChatHistory = async () => { fallbackCalls++; return {ok: true, histories: [], messages: []}; };
  const source = fs.readFileSync(path.join(root, 'work-panel/main.ts'), 'utf8').replace('new KuroWorkPanel();', 'module.exports = KuroWorkPanel;');
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText;
  const m = {exports: {}};
  const window = {kuroWorkPanel: h.bridge};
  let drawer;
  const appRoot = {querySelector: () => drawer};
  const document = {querySelector: () => appRoot};
  new Function('require','module','exports','window','document',code)(r => r.endsWith('.css') ? {} : r === './schedule' ? {} : load('work-panel/model'),m,m.exports,window,document);
  const panel = Object.create(m.exports.prototype);
  const pending = panel.refreshHistory();
  h.reply({ok: false, error: 'history_owner_rejected'});
  await pending;
  assert.equal(fallbackCalls, 0);
  assert.equal(panel.history.ok, false);
  class Element {
    children = []; className = ''; textContent = '';
    appendChild(e) { this.children.push(e); return e; }
    append(...es) { this.children.push(...es); }
    replaceChildren() { this.children = []; }
    setAttribute() {} addEventListener() {}
  }
  drawer = new Element();
  document.createElement = () => new Element();
  panel.historyQuery = ''; panel.chat = {};
  panel.renderHistoryDrawer();
  const copy = el => el.textContent + el.children.map(copy).join('');
  assert.match(copy(drawer), /對話服務尚未連線/);
  assert.doesNotMatch(copy(drawer), /目前沒有對話紀錄/);
  const recovered = panel.refreshHistory();
  h.reply({ok: true, histories: rows});
  await recovered;
  panel.renderHistoryDrawer();
  const list = drawer.children.at(-1);
  assert.equal(list.children.length, 22);
  assert.ok(list.children.every(row => row.className.startsWith('history-row')));
  panel.historyQuery = 'no match'; panel.renderHistoryDrawer();
  assert.match(copy(drawer), /找不到符合的對話/);
  panel.historyQuery = '';
  const empty = panel.refreshHistory();
  h.reply({ok: true, histories: []});
  await empty; panel.renderHistoryDrawer();
  assert.match(copy(drawer), /目前沒有對話紀錄/);
});

test('presentation distinguishes loading, failure and ready empty; ready/reconnect reuses drawer read handler', async () => {
  const h = harness();
  const elements = new Map();
  let open = true, closeClicks = 0, readClicks = 0;
  class Element {
    dataset = {}; hidden = false; textContent = ''; attrs = {};
    setAttribute(k,v) { this.attrs[k] = v; }
    appendChild(node) {
      const name = node.dataset.ownerHistoryStatus ? '[data-owner-history-status]' : '[data-owner-history-progress]';
      elements.set(name, node); node.remove = () => elements.delete(name);
    }
    querySelector(selector) { return elements.get(selector); }
  }
  const drawer = new Element(), list = new Element(), header = new Element();
  elements.set('[data-history-drawer]', drawer); elements.set('.history-list', list); elements.set('.chat-header', header);
  elements.set('[data-stage]', {classList: {contains: () => open}});
  elements.set('[data-history-drawer] .history-drawer-header .icon-button', {click: () => {closeClicks++; open = false;}});
  elements.set('[data-history-toggle]', {click: () => {readClicks++;}});
  const document = {querySelector: selector => elements.get(selector), createElement: () => new Element(), addEventListener() {}};
  const project = load('owner-presentation', {document, Element}).installHistoryListGuards(h.t);
  const pending = h.bridge.getHistories();
  project();
  assert.equal(list.hidden, true);
  assert.match(elements.get('[data-owner-history-status]').textContent, /正在等待/);
  assert.match(elements.get('[data-owner-history-progress]').textContent, /正在讀取/);
  h.reply({ok: false, error: 'history_owner_rejected'});
  await assert.rejects(pending);
  await flush(); project();
  assert.match(elements.get('[data-owner-history-status]').textContent, /讀取失敗/);
  assert.equal(list.hidden, true);
  h.chat({wsConnected: true, historyReady: false});
  h.chat({wsConnected: true, historyReady: true});
  await flush();
  assert.equal(closeClicks, 1); assert.equal(readClicks, 1);
  open = true;
  const reopened = h.bridge.getHistories();
  h.reply({ok: true, histories: []});
  await reopened; await flush(); project();
  assert.equal(list.hidden, false);
  assert.equal(elements.has('[data-owner-history-status]'), false);
  h.chat({wsConnected: false, historyReady: false});
  h.chat({wsConnected: true, historyReady: true});
  await flush();
  assert.equal(closeClicks, 2); assert.equal(readClicks, 2);
  // A closed drawer is left closed; its normal next open performs the read.
  h.chat({wsConnected: false, historyReady: false});
  h.chat({wsConnected: true, historyReady: true});
  await flush();
  assert.equal(readClicks, 2);
});
