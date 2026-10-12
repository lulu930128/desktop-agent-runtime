const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../pet-electron/node_modules/typescript');

const source = fs.readFileSync(path.join(__dirname, '../pet-electron/src/main.js'), 'utf8');
const tree = ts.createSourceFile('main.js', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
function findAll(node, predicate, result = []) {
  if (predicate(node)) result.push(node);
  ts.forEachChild(node, child => { findAll(child, predicate, result); });
  return result;
}
function calls(node, name) {
  return findAll(node, n => ts.isCallExpression(n) && n.expression.getText(tree) === name);
}
const owner = tree.statements.find(s => ts.isVariableStatement(s)
  && s.declarationList.declarations.some(d => d.name.getText(tree) === 'qtDesktopOwner'));
const ipc = findAll(tree, n => ts.isFunctionDeclaration(n) && n.name?.text === 'registerIpc')[0];
const ready = findAll(tree, n => ts.isCallExpression(n)
  && n.expression.getText(tree) === 'app.whenReady().then')[0].arguments[0].body;

for (const value of ['qt', 'electron', undefined]) {
  test(`desktop owner ${value}: execute production startup gates with synthetic effects`, () => {
    assert.equal(owner, undefined, 'Electron no longer has a standalone desktop-owner branch');
    // Execute enclosing production statements, not a copied ownership predicate.
    const statements = [
      ...ipc.body.statements.filter(s => calls(s, 'startScheduleNotifications').length),
      ...ready.statements.filter(s => ['createTray', 'createWindow', 'registerModelProtocol']
        .some(name => calls(s, name).length)),
    ];
    assert.equal(calls(tree, 'createTray').length, 0, 'Qt is the only tray owner');
    assert.equal(calls(tree, 'startScheduleNotifications').length, 0, 'Qt is the only delivery consumer');
    const effects = [];
    const context = {
      process: {env: {KURO_DESKTOP_OWNER: value}},
      scheduleClient: {}, Notification: {}, revealBriefingWindow() {},
      startScheduleNotifications: () => { effects.push('schedule'); return () => {}; },
      createTray: () => effects.push('tray'),
      createWindow: () => effects.push('pet'),
      registerModelProtocol: () => effects.push('model'),
      protocol: {}, net: {}, path, repoRoot: 'synthetic',
    };
    vm.runInNewContext(statements.map(s => s.getText(tree)).join('\n'), context);
    assert.deepEqual(effects, ['model', 'pet']);
  });
}
