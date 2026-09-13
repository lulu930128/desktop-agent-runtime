const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeSnapshot } = require('../pet-electron/src/main-process/briefing-store');

test('Mail snapshot replacement cannot revive legacy Calendar in Today or sections', () => {
  const legacy = {sections:[{key:'calendar',title:'Legacy',modules:[]}],today:{items:[
    {id:'old',source:'calendar',text:'Legacy event'},
    {id:'study',source:'study',text:'Study retained'}
  ]}};
  const snapshot = normalizeSnapshot({mail:{messages:[]}},legacy);
  assert.equal(snapshot.sections.some(s=>s.key==='calendar'),false);
  assert.equal(snapshot.today.items.some(i=>i.source==='calendar'),false);
  assert.equal(snapshot.today.items.some(i=>i.id==='study'),true);
});
