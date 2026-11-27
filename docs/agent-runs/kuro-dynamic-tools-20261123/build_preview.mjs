// Generate the portable read-only preview from the real Qt Tools component and local receipts.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from '../../../pet-electron/node_modules/vite/dist/node/index.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const ui = path.join(root, 'devtools/original-git-web-host-20261010/frontend');
const read = file => fs.readFileSync(file, 'utf8');
const inventory = JSON.parse(read(path.join(here, 'inventory.json')));
const events = JSON.parse(read(path.join(here, 'workflows.json'))).events;
const groups = {'project-workspace':'Project Workspace','japanese-study':'日文學習','english-study':'英文學習',
  'listening-audio':'聽力練習','omi-search':'OMI 市場資料'};
const tools = inventory.tools.map(row => ({...row, label:row.label || row.name.split('::')[1],
  serviceLabel:groups[row.service], mode:'owner', enabled:true}));
const snapshot = {ok:true,preview:true,contract:'kuro.tool-policy-settings.v1',digest:inventory.policy_digest,
  confirmation_available:false,runtime_adoption:'UNVERIFIED',catalog:{toolNames:tools.map(r=>r.name),groups},
  services:inventory.services,tools,events};
const entry = 'virtual:kuro-tools-preview';
const bundle = await build({root:ui, configFile:false, publicDir:false,logLevel:'warn',
  plugins:[{name:'tools-preview',resolveId(id){if(id.endsWith(entry))return '\0'+entry;},
    load(id){if(id==='\0'+entry)return `import {installToolSettings} from ${JSON.stringify(path.join(ui,'src/owner-presentation.ts').replaceAll('\\','/'))};
      const snapshot=JSON.parse(document.getElementById('receipt').textContent);
      installToolSettings({call:async method=>method==='getTools'?snapshot:{ok:false},on(){}})();`;}}],
  build:{write:false,minify:false,lib:{entry,formats:['iife'],name:'KuroTools'}}});
const js = (Array.isArray(bundle) ? bundle[0] : bundle).output.find(item=>item.type==='chunk').code;
const css = ['src/work-panel/styles.css','src/owner-presentation.css'].map(f=>read(path.join(ui,f))).join('\n');
fs.writeFileSync(path.join(here,'preview.html'), `<!DOCTYPE html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Kuro 工具與權限 · 隔離預覽</title>
<style>${css}
html,body{overflow:auto;height:auto;min-height:100%}main{width:min(900px,94%);margin:40px auto}
main header{display:flex;gap:20px;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);margin-bottom:20px}
[hidden]{display:none!important}main header a{color:var(--moon)}.settings-content{overflow:visible}h1{font-size:22px}</style>
<main><header><h1>Kuro 工具頁預覽</h1><a href="task.patch">檢視程式差異</a></header>
<div hidden class="settings-nav-item is-active"><strong>工具與權限</strong></div><div class="settings-content"></div></main>
<script id="receipt" type="application/json">${JSON.stringify(snapshot).replaceAll('<','\\u003c')}</script>
<script>${js.replaceAll('</script','<\\/script')}</script></html>`);
