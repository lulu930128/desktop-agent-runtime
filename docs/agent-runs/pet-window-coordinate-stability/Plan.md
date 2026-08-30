# Plan

## Milestones

1. 固定幾何與狀態 contract
   - Scope: main-process geometry helper、state、task docs。
   - Acceptance: display 空洞被排除，anchor、model screen bounds 與 dynamic host envelope 可用純函式測試。
   - Validation: `node --test --test-isolation=none .\tests\pet_layout.test.cjs`

2. 收斂 Pet host 與 pointer ownership
   - Scope: Electron `main.js`、preload、renderer command contract。
   - Acceptance: Pet 使用 renderer 回報的 model-bounds-follow host；main process 發送全域游標；anchor／zoom 更新與 native host resize 不形成 model scale feedback loop。
   - Validation: `node --check .\pet-electron\src\main.js` 與 targeted Node tests。

3. 修正 Live2D look 與 hit test
   - Scope: pointer controls、renderer、hit tester、interaction profile。
   - Acceptance: look 以臉部 screen point 計算且只用一套 Cubism look path；缺少 model3 HitAreas 時使用可見 drawable 三角 mesh，不使用 drawable AABB 或人工橢圓 fallback。
   - Validation: `npm run check:renderer` 與 `npm run build:renderer`。

4. 收斂 transform ownership 與 revision
   - Scope: main-owned `PetTransformState`、intent-only renderer request、revisioned transform／host／envelope IPC。
   - Acceptance: host command 無法改 anchor／zoom；過期或缺少 revision 的訊息 fail closed；20 次放大／縮小不累積可見漂移。
   - Validation: transform、revision、command geometry targeted Node tests。

5. 分離 stable placement 與 dynamic visual bounds
   - Scope: Live2D renderer placement matrix、drawable bounds sampling、inspector evidence。
   - Acceptance: motion／expression／outfit 只改 host envelope，不重定義腳底或水平中心。
   - Validation: model screen geometry regression、renderer typecheck／build。

6. 切換 Pet Geometry Core v2 actual viewport
   - Scope: renderer viewport pure helper、五條 screen-space conversion、expected／actual inspector、native bounds diagnostics。
   - Acceptance: cached expected host 不再參與 rendering geometry；host move／resize regression 維持 global stable anchor；pointer 與 model envelope 共用 actual canvas viewport。
   - Validation: viewport geometry tests、legacy scan、renderer typecheck／build。

7. Scoped live acceptance
   - Scope: 只重啟 Pet shell，查 control endpoint 與實際桌面互動。
   - Acceptance: exact Pet PID 採用 compact host，anchor 一致，多螢幕拖曳、點擊穿透與可見位置正常。
   - Validation: `/status`、`/live2d-inspector`、截圖／實際互動與短時間資源取樣。

8. Interaction Freeze A/B proof
   - Scope: Main-process experiment flag、drag／zoom burst state、host relocation suppression、telemetry；renderer 只補 drag-start signal。
   - Acceptance: Freeze OFF／ON 共用同一 renderer build；Freeze ON 時 drag／180 ms wheel burst 仍更新 transform 與 envelope，但不呼叫 native `setBounds()`，且 `/status` 可辨識 suppressed／applied counts。
   - Validation: host envelope policy regression、Electron syntax、renderer typecheck／build、Freeze ON live status 與使用者拖曳／縮放實測。

9. Fixed shell 與 compact surface 純核心
   - Scope: `pet-fixed-shell.js`、render-surface geometry、targeted tests。
   - Acceptance: shell 使用 physical display bounds union；initial／dynamic surface 不等於 shell，anchor 可穿出實體螢幕且不被 clamp。
   - Validation: fixed-shell／render-surface geometry tests。

10. Atomic renderer surface cutover
    - Scope: compact surface DOM、frame-start pending apply、transform／envelope／topology callbacks、inspector telemetry。
    - Acceptance: WebGL 初始化即使用 compact canvas；surface 位移與 resize 在 render frame 開頭套用，不先搬舊 framebuffer 再下一幀 correction。
    - Validation: renderer typecheck／build 與 viewport／transform regression。

11. Fixed native shell guard 與 click-through fail-safe
    - Scope: Main fixed shell owner、單一 native bounds wrapper、hover lease／watchdog、status telemetry。
    - Acceptance: normal Pet lifecycle native bounds writes為 0；renderer failure／unresponsive／stale lease 強制恢復 passthrough。
    - Validation: Electron syntax、legacy scan、mouse policy regression。

12. Feature-flagged live acceptance
    - Scope: 只 reload／restart Pet shell，保留 v6＋Freeze rollback。
    - Acceptance: fixed shell runtime identity、compact canvas、drag／zoom無 correction、透明區可點、跨螢幕／mixed DPI／極端 zoom與 CPU／GPU可接受。
    - Validation: `/status`、`/live2d-inspector`、實際桌面互動與資源取樣。

## Stop-and-fix rules

- targeted tests、syntax、typecheck 或 build 任一失敗時，先修正再進 runtime 驗收。
- 若 compact host 造成模型裁切或不能跨螢幕，先修正 geometry／projection，不回退成全桌面互動視窗。
- 若無法證明 runtime 採用新版 source，不宣稱使用者可見修正完成。
- fixed shell 與 compact surface 必須同一個 feature-flagged cutover；不得先啟動 giant shell 再補 compact canvas。
- Q3／Q4 驗收完成前不得移除 `model-bounds-follow-v6` 或 Interaction Freeze rollback。

## Decisions

- 2026-08-25：不再讓跨雙螢幕透明 BrowserWindow 同時承擔視覺與互動；改採 compact-follow host。
- 2026-08-25：使用腳底中央作為全域 anchor，並由 main process 唯一持有與校正。
- 2026-08-25：全域 cursor tracking 由 Electron main process 提供，解除 renderer 必須覆蓋整個桌面的假設。
- 2026-08-25：依使用者澄清，全域 cursor feed 僅做 transparent-window hit preflight；Live2D look 只在按住／拖曳角色期間啟用。
- 2026-08-25：依使用者要求解除腳底 anchor 的 work-area 底部下限；先在 tray 與工作面板加入「重置桌寵位置」以避免角色無法找回。
- 2026-08-25：無官方 HitAreas 的模型改以可見 drawable 三角 mesh 命中，讓腳、袖子與頭髮依實際模型幾何可選取。
- 2026-08-25：縮放不再只改 model matrix；main process 以 0.25 倍級距擴張單螢幕 host envelope，renderer 以 1280 CSS px 基準抵銷 host 尺寸對模型實際大小的影響，保留腳底 screen anchor。
- 2026-08-30：縮放 contract 升級為 `compact-follow-v2`；每次滾輪以 screen-space 游標為 pivot 換算新 anchor，zoom／anchor 以單一 IPC 送往 main process，host 上限小於 display 全尺寸。
- 2026-08-30：實機影片證明 placement clamp 會破壞 pivot invariance；contract 升級為 `compact-follow-v3`，anchor 改為不限制的 screen-space 座標，display resolver 只負責選擇 host 尺寸，找回角色由既有 reset action 負責。
- 2026-08-30：工程規格與 source audit 證明固定 zoom envelope 仍會在極端倍率造成 BrowserWindow 內部裁切；contract 升級為 `model-bounds-follow-v4`。renderer 擁有 Cubism 可見邊界到 screen DIP 的投影，main process 擁有 native bounds、96 DIP padding、即時擴張與延遲縮小。
- 2026-08-30：快速滾輪仍存在 renderer／main 雙寫與 host resize 交錯；contract 升級為 `model-bounds-follow-v5`。renderer 只送含事件 `screenX/screenY` pivot 的操作意圖，main process 計算並提交唯一 transform revision。
- 2026-08-30：host 訊息只可更新 viewport；placement 固定使用模型初始穩定可見邊界，dynamic drawable bounds 只服務透明 host envelope。
- 2026-08-30：source 與 live diagnostics 證明 v5 的 `hostBounds` 仍是 async expected mirror，卻同時驅動五條 renderer screen-space geometry；v6 改用 `window.screenX/screenY + canvas rect` 的 per-frame／per-event actual canvas viewport，expected host 僅保留 telemetry。
- 2026-08-30：`ActualViewport` 精確命名為 `actualCanvasViewportBounds`；Main 同時輸出 native window／content bounds 作診斷，但不得透過另一條 IPC mirror 成為 renderer geometry source。
- 2026-08-30：不直接重構 fixed host；先用 process-scoped `KURO_PET_INTERACTION_FREEZE_HOST=1` 做單一變因 A/B。預設 OFF，Mode A 不主動套用 interaction pending host，正式產品設定與 host padding／pivot／DPI contract 均不變。
- 2026-08-30：Freeze A/B 與使用者畫面確認 dynamic native relocation 是主要 correction 來源；正式 cutover 改為 `fixed-desktop-shell-v1`＋derived compact surface。
- 2026-08-30：fixed shell 預設啟用，但保留 `KURO_PET_FIXED_DESKTOP_SHELL=0` 回到 v6；legacy cleanup 延後到 live Q3／Q4 驗收後。
- 2026-08-30：surface DOM 變更只在 render frame 開頭 flush；dynamic envelope 在當幀只排入 pending，避免移動已畫好的舊 framebuffer。
