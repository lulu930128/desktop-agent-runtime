# W9 Pet native frame checkpoint

## 範圍與限制

- Repo：`C:\project\desktop-agent-runtime`；基線 `main / 74b372f9c48a16c7deb129faf835970b6b1c2a05`。
- 目標：既有單一 Electron owner 在 startup/topology read back native content；必要時最多一次 anchor display fallback；Renderer 與 read-only capability 使用實際 frame。
- 不變更 mouse/window policy、CSS/canvas、使用者 anchor/zoom、private state、模型、W7/W8 既有 21 個 dirty paths。
- 不啟動或重啟任何正式服務，不做 live POST、commit/push/tag，不寫 repo 外檔案。再次寫入拒絕即停止，不換方式繞過。

## 計畫與完成條件

1. 已記錄 source/WIP SHA，檢查 owner、產品品質與現有測試；續接前核對 27 個 dirty paths、原四個 W9 source SHA 與未套用 Geometry gate。
2. 已接入 bounded native reconciliation、actual-frame bootstrap/host-set、unknown-frame Renderer recovery、保守 capability；本輪補齊 Geometry gate。
3. 已執行實際 source targeted regression、syntax、renderer typecheck 與隔離 build；W7/W8 21/21 SHA 不變，未重跑 W7/W8。
4. 已保存本輪驗證與恢復界線；獨立 Reviewer 與使用者正常 cold start native gate 待驗。

## 狀態

- 狀態：SOURCE_VALIDATED；獨立 Reviewer 待複查，Native Q3/Q4 未驗證，產品驗收仍為 partial。
- 本輪只修改 `pet-command-geometry.ts` 的 native bounds/revision gate、更新兩個既有測試檔、新增 `tests/pet_native_frame.test.cjs` 及本 checkpoint/Validation.json。
- 上輪 `main.js`、`pet-fixed-shell.js`、`pet-status.js`、`pet-render-surface-controller.ts` 的修改保留且 SHA 不變；`renderer/src/main.ts` 無需修改，實際 callback 已由 regression 驗證接通。
- `pet-host-set` 僅接受有限數值 x/y、正的有限 width/height，以及與 Renderer 相同的非負 safe-integer revision；unknown/malformed/stale/future payload 不呼叫 setter、不回報 hostAccepted。
- 先前記憶體候選 20/20、既有 31/31 與唯讀探針 9/9 均不繼承為本輪證據。本輪重新執行並通過 56 個正式 source tests。
- Windows/Electron 為何 clamp union 的底層原因仍未確認。
- Capability 模型資訊仍來自既有 5 秒 inspector probe，最多採用 6 秒內且 revision 相符的快照；status 讀取當下 native frame/hidden 狀態，不進行 relocation/save，也不代表逐影格或實體桌面可見性驗收。

## 權限恢復與 Observation

- 前輪 `pet-command-geometry.ts` 寫入失敗後已停止寫入，保留部分 source。
- 使用者提供新證據：管理員已備份 SDDL 並修復 ACL；正式 workspace_write job `abbc9f4f-d889-4b60-8f6c-938082e66455` 驗證 restricted ACL、相鄰臨時檔及目標 Open Existing Write handle，內容 SHA 保持一致。本輪未自行重做 ACL/write permission 探測，也未改權限。
- Creation/LastWrite/LastAccess 合併比較有差異，確切欄位未知，僅列 Observation；使用者另提供 geometry LastModified 仍為原 2026-08-30。本輪不把時間戳差異視為 permission denial。
- 本輪正常 source 寫入成功，未遇新 Permission denied。

## 本輪驗證

Repo root 執行（10 個受影響測試檔，56 passed / 0 failed / 0 skipped，exit 0）：

```powershell
node --test tests/g6_pet_shell.test.cjs tests/pet_native_frame.test.cjs tests/pet_fixed_shell.test.cjs tests/pet_host_envelope.test.cjs tests/pet_render_surface_geometry.test.mjs tests/pet_command_geometry.test.mjs tests/pet_transform_state.test.cjs tests/pet_window_policy.test.cjs tests/pet_mouse_policy.test.cjs tests/pet_transform_revision.test.mjs
```

- G6 以真實 native/display/model fixtures 覆蓋 ready、unknown、hidden、offscreen、partial overlap、負座標、minimum visible area、三者交集及 inspector failure。舊缺幾何仍 ready 的 fixture 已移除；missing/loading/failed、policy、single-owner 與 bounded status coverage 保留。
- 新 regression 直接載入正式 helpers、AST 擷取 main functions，以及在記憶體編譯實際 Controller/router；覆蓋 union accepted、bounded fallback、persistent clamp、write count、bootstrap、drag/zoom freeze、null-frame recovery、revision fence 與正式 main callback。
- G6 的 HTTP 測試只使用 test-owned loopback port 0 與 synthetic handlers；未呼叫正式服務。
- `node --check`：`pet-electron/src/main.js`、`pet-electron/src/main-process/pet-fixed-shell.js`、`pet-electron/src/main-process/pet-status.js`、`tests/g6_pet_shell.test.cjs`、`tests/pet_native_frame.test.cjs`，五個各 exit 0。
- 在 `pet-electron` 執行 `node node_modules/typescript/bin/tsc --project tsconfig.renderer.json --noEmit`：exit 0。
- `git diff --check`：exit 0；僅有既存 LF/CRLF 提示。
- `Validation.json` 保存續接前 SHA、交付 source/tests SHA、驗證結果；W7/W8 21/21 與原 `Preflight.json` 相符。
- 一個新增負座標 fixture 最初錯估垂直錯位螢幕的最近距離，7 passed / 1 failed；已修正 fixture 並增加反向案例，最終 56/56 通過，沒有為此改 production 邏輯。

隔離 build 在 `pet-electron` 執行下列命令；實際 config 在記憶體編譯，輸出到全新 repo-local `.tmp`，不寫正式 renderer-dist，不複製或改動 public assets，不讀 `.env`：

```powershell
@'
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { build, defineConfig } from 'vite';
const outDir=path.resolve('../.tmp/w9-pet-native-frame-resume-20261018');
if(fs.existsSync(outDir)) throw new Error('Isolated output already exists; refusing overwrite');
const configPath=path.resolve('vite.renderer.config.ts');
const exports={};
const code=ts.transpileModule(fs.readFileSync(configPath,'utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}
}).outputText;
vm.runInNewContext(code,{exports,__dirname:path.dirname(configPath),require:name=>{
 if(name==='vite')return {defineConfig};
 if(name==='path')return path;
 throw new Error('Unexpected config dependency');
}},{filename:configPath});
const config=exports.default;
await build({...config,configFile:false,envFile:false,
 build:{...config.build,outDir,emptyOutDir:false,copyPublicDir:false}});
'@ | node --input-type=module
```

- 結果：Vite 8.0.13、86 modules transformed、exit 0；這是 bundle compilation 驗證，不是可發布的完整 runtime assets 套件。
- 初次以 Vite `configLoader: runner` 載入既有 `__dirname` config 時 exit 1 / `ERR_AMBIGUOUS_MODULE_SYNTAX`，屬 loader 相容性而非權限拒絕；保留原 config，改為以上記憶體載入方式後通過。
- 已知提示：Node `MODULE_TYPELESS_PACKAGE_JSON`；Cubism classic script 無法當 module bundle。未做無關 package/config 改動。
- Reviewer 重跑 build 時應另選全新的隔離輸出目錄，不能覆寫本次或 production output。

## 恢復界線

- `Preflight.json` 保存本輪前的 21 個 WIP 路徑及授權 source SHA。
- 只恢復 W9 scoped diff；禁止 reset/clean/stash/checkout，禁止回復整個 worktree。
- 先確認 current source 與交付 SHA 一致，再由 reviewer 檢查 W9 reverse patch；若已有後續變更，逐 hunk 合併，不能直接覆寫。
- W7/W8 source pin 與 Web bundle 是不同範圍，不修改、不重建；舊 gate 若因 Pet source drift 失配，不重簽舊證據。

## 待使用者正常 cold start 驗收

- 使用既有 Launcher 入口自行啟動；核對唯一 Pet owner、載入 source/build 身分。
- 核對 native content readback、Renderer shell、model bounds 與 displays 的共同交集，不能以 `modelReady` 代替可見。
- 雙螢幕、負座標、125%/150% DPI、large zoom partial overlap、拖曳/zoom 期間 topology 變更與 lease 結束後更新。
- union clamp 時最多一次 per-display fallback；持續 clamp 顯示 degraded/unknown，不循環 resize、不重設 anchor/zoom。
- GET status 不移動視窗、不寫使用者 state；hidden/unknown/失敗 inspector 不得 ready。
- Native Q3/Q4 留待實際 Windows 使用者工作階段驗收，本輪 source tests/build 不替代它。
