// SYNTHETIC DOM contract, not a Windows rendering acceptance.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname,'geometry.js'),'utf8');
const source = fs.readFileSync(path.join(__dirname,'frontend/src/work-panel/main.ts'),'utf8');
const rect={x:0,y:0,width:100,height:20,bottom:20};
function measure(missing, historyOpen=false, drawerRect=rect, animations=[]) {
  const node={tagName:'P',textContent:'SYNTHETIC',parentElement:{className:'today-frame'},getBoundingClientRect:()=>rect,
    classList:{contains:name=>historyOpen && name==='has-history'}};
  const document={documentElement:{scrollWidth:1280,scrollHeight:720},body:{innerText:'SYNTHETIC'},fonts:{status:'loaded',check:()=>true},
    querySelector:s=>s==='.history-drawer'?{...node,getBoundingClientRect:()=>drawerRect}:node,
    querySelectorAll:s=>s===missing?[]:[node],getAnimations:()=>animations.map(playState=>({playState,effect:{target:node}})),
    createRange:()=>({selectNodeContents(){},getClientRects:()=>[rect]})};
  return JSON.parse(vm.runInNewContext(script,{document,getComputedStyle:()=>({getPropertyValue:()=>'',fontFamily:'synthetic',lineHeight:'20px'}),innerWidth:1280,innerHeight:720,devicePixelRatio:1,screen:{},navigator:{language:'zh-TW'}}));
}
test('real source Today selectors are measured and required nonempty',()=>{
  for(const token of ['today-frame','section-kicker','today-question','today-summary','today-primary','block-heading','priority-list','empty-state']) assert.ok(source.includes(token),token);
  const result=measure();
  assert.equal(result.deepCoverage.today,true);
  for(const [selector,count] of Object.entries(result.deepCoverage.required)) {
    assert.ok(count>=1,selector);assert.ok(result.deepGeometry[selector].length>=1,selector);
  }
});
test('History evidence requires opened state as well as drawer geometry',()=>{
  assert.equal(measure().history.opened,false);
  assert.equal(measure(undefined,true).history.opened,true);
});
test('opened class with offscreen drawer cannot pass visible History evidence',()=>{
  const result=measure(undefined,true,{x:1500,y:0,width:320,height:500});
  assert.equal(result.history.opened,false);
  assert.equal(result.history.visibleIntersection.width,0);
  assert.equal(result.geometry['.history-drawer'].x,1500,'raw rect is never moved');
});
test('drawer outside stage is rejected even inside viewport; running animation remains unsettled',()=>{
  assert.equal(measure(undefined,true,{x:200,y:0,width:320,height:500}).history.opened,false);
  assert.equal(measure(undefined,true,rect,['running']).history.animationsSettled,false);
  assert.equal(measure(undefined,true,rect,['finished']).history.animationsSettled,true);
});
test('missing header and kicker stay missing, never synthesized',()=>{
  for(const selector of ['.today-frame > header','.today-frame > header > .section-kicker','.today-primary > section > .block-heading']) {
    const result=measure(selector);assert.equal(result.deepCoverage.required[selector],0);assert.deepEqual(result.deepGeometry[selector],[]);
  }
});
