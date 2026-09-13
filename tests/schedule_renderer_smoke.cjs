// Run with pet-electron/node_modules/electron/dist/electron.exe.
// Isolated DB/profile; real SchedulePanel, preload, IPC, HTTP and Core process.
const {app,BrowserWindow,ipcMain}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const http=require('node:http');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
const ts=require('../pet-electron/node_modules/typescript');
const {createCoreClient,registerCoreIpc}=require('../pet-electron/src/main-process/core-client');
const root=path.resolve(__dirname,'..');
const scratch=fs.mkdtempSync(path.join(os.tmpdir(),'kuro-schedule-ui-'));
app.setPath('userData',path.join(scratch,'profile'));
let child,window,port,client,notificationUnavailable=false,statusDay=null;
const token=crypto.randomBytes(32).toString('hex'),instance=crypto.randomUUID();
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(check,label){for(let i=0;i<100;i++){if(await check())return;await wait(100);}throw Error(`Timed out: ${label}`);}
async function startCore(){
  child=spawn(path.join(root,'envs/kuro-llm310/python.exe'),[path.join(root,'kuro_core_service.py'),'--db',path.join(scratch,'work.sqlite3'),'--port',String(port),'--instance',instance,'--timezone','Asia/Taipei'],{cwd:root,env:{...process.env,KURO_CORE_TOKEN:token},windowsHide:true,stdio:'ignore'});
  await until(async()=>Boolean((await client.call('status')).ok),'Core readiness');
}
async function stopCore(){
  const current=child;
  await new Promise(resolve=>{const req=http.request(`http://127.0.0.1:${port}/shutdown`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json','Content-Length':2}},res=>{res.resume();res.on('end',resolve);});req.on('error',resolve);req.end('{}');});
  await until(()=>current.exitCode!==null,'Core stop');child=null;
}
async function run(code){return window.webContents.executeJavaScript(code,true);}
async function capture(file){await run('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');await wait(150);fs.writeFileSync(file,(await window.webContents.capturePage()).toPNG());}
async function click(label){await run(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent===${JSON.stringify(label)}).click()`);}
async function modal(){await until(()=>run(`Boolean(document.querySelector('dialog[open]'))`),'dialog');}
async function saved(){await until(()=>run(`!document.querySelector('dialog[open]')`),'saved');}
async function field(label,value){await run(`(()=>{const n=Array.from(document.querySelectorAll('dialog label')).find(n=>n.firstElementChild.textContent===${JSON.stringify(label)}).querySelector('input,select,textarea');if(n.type==='checkbox')n.checked=${JSON.stringify(value)};else n.value=${JSON.stringify(value)};n.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
async function main(){
  const probe=require('node:net').createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));port=probe.address().port;await new Promise(r=>probe.close(r));
  client=createCoreClient({url:`http://127.0.0.1:${port}`,token,instance});await startCore();
  registerCoreIpc(ipcMain,{async call(action,payload){if(action==='notifications'&&notificationUnavailable)return {ok:false,error:'core_unavailable'};const result=await client.call(action,payload);return action==='status'&&statusDay?{...result,today:statusDay}:result;}},()=>window);
  const source=fs.readFileSync(path.join(root,'pet-electron/renderer/src/work-panel/schedule.ts'),'utf8').replace('export class SchedulePanel','class SchedulePanel');
  const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText.replace(/export \{\};?/g,'');
  fs.writeFileSync(path.join(scratch,'panel.js'),compiled+'\nwindow.panel=new SchedulePanel(window.kuroWorkPanel);document.body.append(panel.root);');
  fs.copyFileSync(path.join(root,'pet-electron/renderer/src/work-panel/styles.css'),path.join(scratch,'style.css'));
  fs.writeFileSync(path.join(scratch,'index.html'),'<meta charset="utf-8"><link rel="stylesheet" href="style.css"><style>body{overflow:auto;padding:16px;height:auto}</style><script defer src="panel.js"></script>');
  window=new BrowserWindow({width:590,height:740,show:false,webPreferences:{preload:path.join(root,'pet-electron/src/briefing-preload.js'),contextIsolation:true,sandbox:true,backgroundThrottling:false}});
  await window.loadFile(path.join(scratch,'index.html'));
  await until(()=>run(`document.body.innerText.includes('這段時間沒有安排')`),'empty state');
  const health=await client.call('status');
  notificationUnavailable=true;await run('panel.refresh(false)');assert.equal(await run(`document.body.innerText.includes('提醒狀態暫時無法確認')`),true);notificationUnavailable=false;
  statusDay=new Date(Date.parse(health.today+'T12:00Z')+86400000).toISOString().slice(0,10);await run('panel.refresh(false)');assert.equal(await run(`document.querySelector('[aria-label="查看日期"]').value`),statusDay);statusDay=null;await run('panel.refresh(false)');
  await click('新增安排');await modal();
  await field('名稱','窄視窗跨日學習安排'.repeat(8));await field('類型','study');await field('全天',true);
  const yesterday=new Date(health.today+'T12:00Z');yesterday.setUTCDate(yesterday.getUTCDate()-1);
  const tomorrow=new Date(health.today+'T12:00Z');tomorrow.setUTCDate(tomorrow.getUTCDate()+1);
  await field('開始／截止',yesterday.toISOString().slice(0,10));await field('結束（全天的結束日不含）',tomorrow.toISOString().slice(0,10));
  await run(`document.querySelector('form').requestSubmit();document.querySelector('form').requestSubmit()`);await saved();
  let view=await client.call('view');assert.equal(view.items.length,1);assert.equal(view.items[0].timeState,'ongoing');assert.equal(view.items[0].item.trackCompletion,true);
  assert.equal(await run(`document.documentElement.scrollWidth<=window.innerWidth`),true);
  const evidence=path.join(root,'launcher_logs','schedule-validation');fs.mkdirSync(evidence,{recursive:true});
  await capture(path.join(evidence,'narrow-schedule.png'));
  await click('編輯');await modal();await field('名稱','保留衝突草稿');
  const item=view.items[0];await client.call('mutate',{action:'update',id:item.scheduleId,expectedRevision:item.revision,scope:'all',item:{...item.item,title:'另一個視窗修改'},confirmed:true,idempotencyKey:crypto.randomUUID()});
  await click('儲存變更');await until(()=>run(`document.querySelector('[role=alert]').textContent.includes('草稿已保留')`),'conflict');
  assert.equal(await run(`document.querySelector('dialog input').value`),'保留衝突草稿');
  await run(`document.querySelector('[role=alert]').scrollIntoView()`);await capture(path.join(evidence,'conflict-draft.png'));
  await click('重新讀取版本（保留草稿）');await wait(150);await click('儲存變更');await saved();
  await click('完成');await until(async()=> (await client.call('view')).items[0].state==='completed','completion');
  await run(`document.querySelector('.schedule-group:last-of-type').open=true`);
  await click('恢復未完成');await until(async()=> (await client.call('view')).items[0].state==='pending','reopen');
  await stopCore();await run('panel.refresh(false)');assert.equal(await run(`document.body.innerText.includes('不能確認是否有安排')`),true);
  await capture(path.join(evidence,'offline.png'));
  await startCore();await run('panel.refresh()');view=await client.call('view');assert.equal(view.items[0].item.title,'保留衝突草稿');
  await click('取消');await modal();await click('確認取消');await saved();assert.equal((await client.call('view')).items.length,0);
  await stopCore();const result={ok:true,checkedAt:new Date().toISOString(),checks:['empty','notification read failure','today rollover','narrow long title','cross-day ongoing','double submit','conflict draft','explicit reload','complete/reopen','offline','restart persistence','cancel'],evidence};
  fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}
app.whenReady().then(main).then(()=>app.exit(0)).catch(error=>{console.error(error);child?.kill();app.exit(1);});
