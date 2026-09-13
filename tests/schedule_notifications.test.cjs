const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { startScheduleNotifications } = require('../pet-electron/src/main-process/schedule-notifications');

for (const allowed of [true, false]) {
  test(`desktop delivery rechecks authorization (${allowed})`, async () => {
    const calls = [];
    let shown = 0;
    class Notice extends EventEmitter {
      static isSupported() { return true; }
      show() { shown++; this.emit('show'); }
      close() { this.emit('close'); }
    }
    const client = { async call(_, payload) {
      calls.push(payload);
      if (payload.action === 'claim') return {ok:true, delivery:{id:'owned',leaseToken:'fenced'}};
      if (payload.action === 'authorize') return {ok:allowed,title:'Test'};
      return {ok:true};
    }};
    const stop = startScheduleNotifications({client,Notification:Notice,reveal(){},intervalMs:60000});
    await new Promise(resolve => setImmediate(resolve));
    stop();
    assert.equal(shown, Number(allowed));
    assert.deepEqual(calls.map(c=>c.action), allowed ? ['claim','authorize','ack'] : ['claim','authorize']);
    if (allowed) assert.deepEqual(calls[2],{action:'ack',id:'owned',leaseToken:'fenced',result:'delivered'});
  });
}
