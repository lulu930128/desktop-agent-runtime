const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname,'typography.js'),'utf8');

test('read-only diagnostic preserves text and reports spacing without claiming glyph font identity', () => {
  const child = Object.freeze({nodeType:3, textContent:'10月11日 星期日'});
  const node = Object.freeze({textContent:child.textContent, childNodes:Object.freeze([child])});
  const document = {
    querySelector:s => s.includes('kicker') ? node : null,
    createElement:tag => { assert.equal(tag, 'canvas'); return {getContext:() => ({measureText:text => ({width:text.length})})}; },
    createRange:() => ({setStart(){}, setEnd(){}, getClientRects:() => [{x:0,y:3,width:7,height:11}]})
  };
  const result = JSON.parse(vm.runInNewContext(script, {document, getComputedStyle:() => ({fontFamily:'monospace',fontSize:'10px',fontStyle:'normal',fontWeight:'400',lineHeight:'normal'})}));
  assert.equal(node.textContent, '10月11日 星期日');
  assert.ok(result.kicker.codepoints.includes('U+0020'));
  assert.equal(result.kicker.glyphRects.length, Array.from(child.textContent).length);
  assert.ok(result.kicker.metrics.some(m => m.text === '10月11日星期日'));
  assert.ok(result.kicker.metrics.some(m => m.text === '10月11日 星期日'));
  assert.ok(result.intl.parts.length > 0);
  assert.equal(result.actualGlyphFonts, 'UNVERIFIED');
  assert.equal(result.icuVersion, 'UNVERIFIED');
});

test('absent Today nodes stay absent', () => {
  const result = JSON.parse(vm.runInNewContext(script, {document:{querySelector:()=>null}}));
  assert.equal(result.kicker, null);
  assert.equal(result.nativeDate, null);
});
