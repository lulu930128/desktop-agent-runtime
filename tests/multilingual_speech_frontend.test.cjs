const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../pet-electron/node_modules/typescript');
const file = path.resolve(__dirname, '../devtools/original-git-web-host-20261010/frontend/src/owner-presentation.ts');
const source = fs.readFileSync(file, 'utf8');
const output = ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText;
const mod = {exports:{}};
new Function('require','module','exports',output)(()=>{throw Error('unexpected runtime import');},mod,mod.exports);
const {validChatSpeechSettings, saveChatSpeechSettings} = mod.exports;
const snapshot = (settings={locale:'ja-JP',policy:'summary',route:'dual_lane'},persisted=false) => ({ok:true,
  contract:'kuro.chat-speech-settings.v1',revision:(persisted?'b':'a').repeat(64),settings,persisted,
  locales:{'ja-JP':'default','zh-Hant':'unverified','en-US':'unverified'}, consumer:'conversation-runtime',effective:'next_turn'});

test('all three policies and reserved locales have explicit capability truth', () => {
  for(const policy of ['brief','summary','detailed']) for(const locale of ['ja-JP','zh-Hant','en-US'])
    assert.equal(validChatSpeechSettings(snapshot({locale,policy,route:'dual_lane'})),true);
  assert.equal(validChatSpeechSettings(snapshot({locale:'fr-FR',policy:'summary',route:'dual_lane'})),false);
  assert.equal(validChatSpeechSettings({...snapshot(),locales:{'ja-JP':'default','en-US':'supported'}}),false);
});

test('write includes expected revision and authoritative readback before success', async () => {
  const first=snapshot(), desired={locale:'en-US',policy:'detailed',route:'dual_lane'}, written=snapshot(desired,true), calls=[];
  const transport={call:async(method,payload)=>{calls.push([method,payload]);return method==='getChatSpeechSettings'?written:written;}};
  assert.deepEqual(await saveChatSpeechSettings(transport,first,desired),written);
  assert.deepEqual(calls,[['updateChatSpeechSettings',{settings:desired,expectedRevision:first.revision}],['getChatSpeechSettings',undefined]]);
});

test('unknown write/readback never retries or reports success', async () => {
  const desired={locale:'ja-JP',policy:'brief',route:'dual_lane'};
  for(const mode of ['failed','unpersisted','mismatch']) {
    const calls=[];
    const result=await saveChatSpeechSettings({call:async(method)=>{
      calls.push(method);
      if(mode==='failed')return {ok:false,unknownResult:true};
      if(mode==='unpersisted')return snapshot(desired,false);
      return method==='updateChatSpeechSettings'?snapshot(desired,true):snapshot();
    }},snapshot(),desired);
    assert.equal(result.ok,false);assert.equal(result.unknownResult,true);
    assert.equal(calls.filter(v=>v==='updateChatSpeechSettings').length,1);
  }
});

test('formal Settings projection adds speech controls, preserves Core owner and immutable main', () => {
  assert.match(source,/const projectChatSpeechSettings = installChatSpeechSettings\(transport\)/);
  assert.match(source,/projectChatSpeechSettings\(\)/);
  assert.match(source,/select\("朗讀策略", "chatSpeechPolicy"/);
  assert.match(source,/select\("朗讀語言", "chatSpeechLocale"/);
  assert.match(source,/語音未驗證前暫不送合成/);
  assert.match(source,/getAssistantSettings/);
  assert.match(source,/getChatSpeechSettings/);
  assert.doesNotMatch(source,/localStorage.*chatSpeech|輸入語言選擇/);
});
