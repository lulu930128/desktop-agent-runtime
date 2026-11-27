const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync, execFileSync} = require('node:child_process');
const ts = require('../pet-electron/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const frontend = path.join(root, 'devtools/original-git-web-host-20261010/frontend/src');
const source = require(path.join(frontend, '../work-panel-history.cjs')).historySource();
function pinnedSource() {
  const release = fs.readFileSync(path.join(root, 'kuro_launcher/qt_web_release.py'), 'utf8');
  const fingerprint = release.match(/fingerprint='([a-f0-9]+)'/)[1];
  const record = JSON.parse(fs.readFileSync(path.join(root, 'assets/qt-owner', fingerprint, 'owner-build.json'), 'utf8'));
  const original = execFileSync('git', ['show', record.lineage.originalCommit + ':pet-electron/renderer/src/work-panel/main.ts'], {cwd: root});
  assert.equal(crypto.createHash('sha256').update(original).digest('hex'), record.lineage.sources['src/work-panel/main.ts']);
  return original.toString('utf8');
}
function panelClass(input = source) {
  function load(name) {
    const code = ts.transpileModule(fs.readFileSync(path.join(frontend, name + '.ts'), 'utf8'),
      {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText;
    const m = {exports: {}};
    new Function('require', 'module', 'exports', code)(r => load(path.join(path.dirname(name), r)), m, m.exports);
    return m.exports;
  }
  const code = ts.transpileModule(input.replace('new KuroWorkPanel();', 'module.exports = KuroWorkPanel;'),
    {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}}).outputText;
  const m = {exports: {}};
  const bridge = {};
  new Function('require', 'module', 'exports', 'window', 'document', code)(
    r => r.endsWith('.css') || r === './schedule' ? {} : load('work-panel/model'), m, m.exports,
    {kuroWorkPanel: bridge}, {querySelector: () => ({})});
  return {Panel: m.exports, bridge};
}
function harness(input) {
  const {Panel, bridge} = panelClass(input);
  const panel = Object.create(Panel.prototype);
  Object.assign(panel, {history: {ok: true, messages: []}, chat: {}, runtime: {}, mode: 'chat',
    renderChrome() {}, updateChatHeader() {}, renderChatTranscript() {}, updateComposerState() {},
    updateSensorControls() {}, renderHistoryDrawer() {}, scheduleHistoryRefresh() {}});
  return {panel, bridge};
}
function frames() {
  const result = spawnSync(path.join(root, 'envs/kuro-llm310/python.exe'), ['-B', 'tests/test_qt_display_stream.py', '--export'],
    {cwd: root, encoding: 'utf8', env: {...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8',
      PYTHONPATH: [root, path.join(root, 'tests')].join(path.delimiter)}});
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test('current signed lineage identifies the original merge method being reproduced', () => {
  assert.ok(pinnedSource().includes('private mergedChatMessages()'));
});

test('real adapter live to asynchronous history refresh retains one complete AI row', async () => {
  const data = frames();
  const {panel, bridge} = harness();
  panel.chat = data[0].chat;
  let rows = panel.mergedChatMessages();
  const complete = data[2].history.messages.at(-1).content;
  assert.equal(rows.at(-1).content, complete.trim());
  panel.onChatState(data[1].chat);
  let resolve;
  bridge.getHistories = () => new Promise(done => {resolve = done;});
  const refresh = panel.refreshHistory();
  assert.equal(panel.mergedChatMessages().filter(r => ['ai', 'assistant'].includes(r.role)).length, 1);
  resolve(data[2].history);
  await refresh;
  panel.onChatState(data[2].chat);
  rows = panel.mergedChatMessages();
  assert.equal(rows.length, 2);
  assert.equal(rows.at(-1).content, complete);
  panel.onChatState(data[3].chat);
  panel.history = data[3].history;
  assert.deepEqual(panel.mergedChatMessages(), []);
});

test('identical user and AI in separate active turns are distinct before history returns', async () => {
  const {panel, bridge} = harness();
  const first = [{role: 'human', content: 'もう一度'}, {role: 'ai', content: '同じ回答。\n- 一覧'}];
  panel.chat = {aiState: 'idle', currentHistoryUid: 'h', latestUserText: 'もう一度', latestAssistantText: first[1].content};
  panel.history = {ok: true, current_history_uid: 'h', messages: first};
  panel.onChatState({aiState: 'thinking', latestAssistantText: ''});
  panel.onChatState({aiState: 'thinking', latestAssistantText: first[1].content});
  assert.equal(panel.mergedChatMessages().length, 4);
  panel.onChatState({aiState: 'idle'});
  assert.equal(panel.mergedChatMessages().length, 4);
  bridge.getHistories = async () => ({ok: true, current_history_uid: 'h', messages: [...first, ...first]});
  await panel.refreshHistory();
  assert.deepEqual(panel.mergedChatMessages(), [...first, ...first]);
});

test('stale async history cannot replace a later history selection or reconnect', async () => {
  const {panel, bridge} = harness();
  panel.chat = {aiState: 'idle', currentHistoryUid: 'old', wsConnected: true};
  let resolve;
  bridge.getHistories = () => new Promise(done => {resolve = done;});
  const read = panel.refreshHistory();
  panel.onChatState({currentHistoryUid: 'new', latestUserText: '', latestAssistantText: ''});
  panel.history = {ok: true, current_history_uid: 'new', messages: [{role: 'ai', content: '新對話'}]};
  resolve({ok: true, current_history_uid: 'old', messages: [{role: 'ai', content: '舊對話'}]});
  await read;
  assert.equal(panel.mergedChatMessages()[0].content, '新對話');
});

test('adapter-only fixes the pinned renderer duplication without changing its signed source', async () => {
  const data = frames();
  const {panel, bridge} = harness(pinnedSource());
  panel.chat = data[1].chat;
  const live = panel.mergedChatMessages();
  bridge.getHistories = async () => data[2].history;
  await panel.refreshHistory();
  const persisted = panel.mergedChatMessages();
  assert.equal(live.length, 2);
  assert.equal(persisted.length, 2);
  assert.equal(live.at(-1).content, persisted.at(-1).content.trim());
});

test('newer history read wins and an old failed read cannot erase it', async () => {
  const {panel, bridge} = harness();
  const pending = [];
  bridge.getHistories = () => new Promise((resolve, reject) => pending.push({resolve, reject}));
  const old = panel.refreshHistory();
  const fresh = panel.refreshHistory();
  pending[1].resolve({ok: true, messages: [{role: 'ai', content: '新快照'}]});
  await fresh;
  pending[0].reject(new Error('old failure'));
  await old;
  assert.equal(panel.history.messages[0].content, '新快照');
  assert.equal(panel.history.ok, true);
});

test('same-history reconnect identity fences pending reads and clears old live text', async () => {
  const {panel, bridge} = harness();
  panel.chat = {aiState: 'idle', currentHistoryUid: 'h', wsConnected: true, identity: {context: 'old'}};
  let resolve;
  bridge.getHistories = () => new Promise(done => {resolve = done;});
  const read = panel.refreshHistory();
  panel.onChatState({identity: {context: 'new'}, latestUserText: '', latestAssistantText: ''});
  resolve({ok: true, messages: [{role: 'ai', content: '舊連線'}]});
  await read;
  assert.deepEqual(panel.mergedChatMessages(), []);
});

test('back-to-back repeated turns survive before any completed history read', () => {
  const {panel} = harness();
  panel.chat = {aiState: 'idle', currentHistoryUid: 'h'};
  for (let i = 1; i <= 3; i++) {
    panel.onChatState({aiState: 'idle', latestUserText: '同一句'});
    panel.onChatState({aiState: 'thinking', latestAssistantText: ''});
    panel.onChatState({aiState: 'thinking', latestAssistantText: '同一回答\n'});
    panel.onChatState({aiState: 'idle'});
    assert.equal(panel.mergedChatMessages().length, 2 * i);
  }
});

test('rolling history and a same-turn partial snapshot retain exactly one live AI', () => {
  const {panel} = harness();
  const old = Array.from({length: 120}, (_, i) => ({role: i % 2 ? 'ai' : 'human', content: String(i), timestamp: String(i)}));
  panel.history = {ok: true, messages: old};
  panel.chat = {aiState: 'idle', latestUserText: '新問題'};
  panel.onChatState({aiState: 'thinking', latestAssistantText: ''});
  panel.onChatState({latestAssistantText: '完整\n回答'});
  panel.history = {ok: true, messages: [...old.slice(2), {role: 'human', content: '新問題'}, {role: 'ai', content: '完整'}]};
  const rows = panel.mergedChatMessages();
  assert.equal(rows.length, 120);
  assert.equal(rows.at(-1).content, '完整\n回答');
  assert.equal(rows.filter(r => r.role === 'ai' && r.content.startsWith('完整')).length, 1);
});

test('direct history payload B clears completed live turn A and fences its pending refresh', async () => {
  const {panel, bridge} = harness();
  panel.chat = {aiState: 'idle', currentHistoryUid: 'A'};
  panel.onChatState({aiState: 'thinking', latestUserText: 'A 問題', latestAssistantText: ''});
  panel.onChatState({latestAssistantText: 'A 回答\n- 細節'});
  panel.onChatState({aiState: 'idle'});
  assert.equal(panel.mergedChatMessages().length, 2);
  let resolve;
  bridge.getHistories = () => new Promise(done => {resolve = done;});
  const oldRead = panel.refreshHistory();
  const b = [{role: 'human', content: 'B 問題'}, {role: 'ai', content: 'B 回答'}];
  panel.applyHistoryPayload({ok: true, current_history_uid: 'B', messages: b});
  assert.deepEqual(panel.mergedChatMessages(), b);
  resolve({ok: true, current_history_uid: 'A', messages: [{role: 'ai', content: 'A 延遲快照'}]});
  await oldRead;
  assert.equal(panel.chat.currentHistoryUid, 'B');
  assert.deepEqual(panel.mergedChatMessages(), b);
});
