# Progress

## Status

- Current phase: fixed-desktop-shell-v1 source／build validation complete; scoped runtime adoption pending
- Last updated: 2026-08-30 Asia/Taipei

## Completed

- 完成照片、source、產品文件與 live `/status`／`/live2d-inspector` 唯讀盤點。
- 確認舊 host 使用虛擬桌面外接矩形，且不同高度顯示器會產生不存在的可用區域。
- 確認小黑 model3 沒有 `HitAreas`，renderer 會回退到所有 drawable 外接矩形。
- 確認舊 look path 以整個雙螢幕 canvas 正規化，且同時套用兩套 look controller。
- 新增以實際 display work-area 集合為準的 geometry resolver；staggered display gap 不再是合法 anchor。
- Pet host 改為 `compact-follow-v1`：基準為 `760 x 1280`，放大時以 0.25 倍級距擴張、並限制在角色所在 display 的尺寸內；main process 回傳 accepted anchor／host bounds。
- 拖曳改用 `PointerEvent.screenX/screenY`，加入 pointer capture、cancel、lost-capture 與 blur 復原。
- main process 以 Electron `screen.getCursorScreenPoint()` 提供全域游標座標；臉部追蹤改以模型臉部原點正規化，且只保留 Cubism `setDragging` 單一路徑。
- 沒有官方 `HitAreas` 時改用可見 drawable 的 triangle mesh；腳、袖子、頭髮等部位依模型幾何命中，不再使用所有 drawable AABB 或頭／身人工橢圓。
- 恢復 adaptive render cadence，移除強制 uncapped renderer 與 background flags。
- 依使用者澄清將 look tracking 改為 press/drag-only；全域 cursor feed 只做命中預判，平常不再觸發臉部追蹤或 active render cadence。
- 依使用者要求解除垂直 bottom clamp；角色可以向下移出 work area，並在 tray／工作面板加入「重置桌寵位置」救援入口。
- 拖曳 anchor IPC 以 animation frame 合併；state persistence 延後 `240 ms`，結束拖曳與退出時強制 flush，避免每個 pointer event 同步寫檔。
- zoom 與 host geometry 改為單一 `pet-zoom-layout-set` payload；BrowserWindow 尺寸變動、腳底 anchor 與 model zoom 在 renderer 同一回合套用，避免各自更新造成中心跳動。
- renderer 以 `1280 CSS px` 基準抵銷 host envelope 尺寸，BrowserWindow 擴大只增加可繪製範圍，不會再次放大角色或移動腳底。

## Validation evidence

- `node --test --test-isolation=none .\tests\pet_mouse_policy.test.cjs .\tests\pet_window_policy.test.cjs`: 7 passed（只覆蓋既有 policy，尚未覆蓋 geometry）。
- Live baseline: host `5120 x 1526`；main anchor `(2177, 1526)`；renderer anchor `(2177, 1592)`。
- `node --test --test-isolation=none ../tests/pet_layout.test.cjs ../tests/pet_mouse_policy.test.cjs ../tests/pet_window_policy.test.cjs`: 12 passed。
- `npm run check:renderer`: passed。
- `npm run build:renderer`: passed（sandbox 內 Vite child-process `EPERM`，以核准的 sandbox 外 build 重跑成功）。
- `node --check`：`main.js`、`state.js`、`pet-layout.js` passed。
- 只透過 Launcher 重啟 Pet shell；LLM、TTS、Bridge 未重啟。新版 live process 為 PID `12792`、instance `12792-mt8jzkfv`。
- Live `/status`：`petHostMode=compact-follow-v1`、host `760 x 1280`、anchor `(2172, 1416)`、renderer WebSocket connected。
- Live `/live2d-inspector`：renderer host／anchor 與 main process 完全一致，canvas `760 x 1280`，`kuro-v1` interaction profile active，overlay 關閉。
- 實際拖曳時 mouse policy 由 `model-interactive` 進入互動，放開後恢復 `transparent-passthrough` 與 `ignoreMouseEvents=true`；沒有留下覆蓋其他視窗的互動層。
- 使用 Pet control 的 next-display 動作從 anchor `(2172, 1416)` 移至 `(4732, 1416)`，再回到 `(2172, 1416)`；過程 PID 與 renderer WebSocket 保持穩定。
- Inspector 觀察到 `ParamAngleX`、`ParamAngleY` 與眼球參數隨全域游標更新，證明 compact host 外仍能持續臉部追蹤。
- 最終 `git diff --check` exit `0`；僅顯示 repo 既有的 LF/CRLF 轉換警告。
- 第二輪修正後 targeted tests 為 `13 passed`，renderer typecheck 與 production build 通過。
- zoom-aware host 修正後 targeted tests 為 `16 passed`；`main.js`／`pet-layout.js` syntax、renderer typecheck 與 production build 通過。
- 驗收收尾關閉 Qt 主控台時，實際行為是停止整個 Launcher-owned runtime，而不是隱藏到 tray；`1188`、`9981`、`23456`、`23567`、`23568` 隨後均停止監聽。完整恢復需要使用者明確授權重啟 Launcher、Bridge、TTS、LLM 與 Pet。

## Decisions made

- 採 compact-follow window 與 main-process global cursor feed，不保留全虛擬桌面互動 host。
- display work areas 以矩形集合處理；anchor 必須落在其中一個真實 work area。
- face look 使用 Kuro-owned profile；interaction hit test 使用模型自己的可見 drawable triangle mesh，避免修改 moc／texture 與不可靠的 ArtMesh AABB 猜測。

## Known issues / risks

- mesh hit test 不讀 texture alpha；若少數 drawable 的三角網格涵蓋透明紋理邊緣，命中範圍可能比逐像素 alpha 稍寬，但不會退化成整塊 AABB。
- 動態 host 會在極端倍率下大於單一 display；仍需 scoped Pet reload 證明 Windows/Electron 實際採用後沒有內部裁切、native bounds 抖動或 click-through 回歸。
- 自動化已驗證狀態轉換與雙螢幕往返；長時間手感（臉部跟隨幅度、命中區鬆緊）仍適合由使用者日常操作再微調。

## Next step

- 取得明確授權後只 reload／restart Pet shell，確認 `model-bounds-follow-v6`、actual／expected convergence、drag finish reason、rapid-wheel pivot、host containment 與實測 FPS。

## 2026-08-30 frame pacing follow-up

- 使用者在新版 runtime 實際觀察到 Live2D 動畫明顯低幀率；source inspection 確認 adaptive cadence 將 idle 限制在 `12 FPS`，互動／說話最高只有 `30 FPS`。
- 舊 scheduler 每幀先等待完整 `setTimeout` interval，再等待下一次 `requestAnimationFrame`，因此實際 cadence 可能低於宣告 target。
- 新策略保留 adaptive rendering 與 Electron 預設背景節流：可見 idle 為 `30 FPS`，互動、說話、聆聽、思考與 inspector 為 `60 FPS`，真正 hidden 時為 `2 FPS`。
- frame pacing 改由單一 `requestAnimationFrame` 時鐘控制，只在 target interval 到期時繪製；`/live2d-inspector` 新增 `renderPerformance.targetFps` 與 `measuredFps`，供 runtime adoption 與實測驗收。
- 不恢復 global `disable-frame-rate-limit`／`disable-renderer-backgrounding` flags，避免桌寵在背景或不可見時長期佔用高 CPU／GPU。
- `npm run check:renderer` passed；Pet geometry/mouse/window policy targeted tests `16 passed`；`git diff --check` exit `0`，只有既有 LF/CRLF warning。
- `npm run build:renderer` 在 sandbox 內因 Vite child process `spawn EPERM` 失敗，依既有執行邊界在核准的 sandbox 外重跑後 passed；production bundle 含 `custom-renderer-2026-08-30-frame-pacing-v5`。
- 現有 live Pet PID `31632` 仍是舊 renderer：`/live2d-inspector` 沒有 `renderPerformance`，因此尚未宣稱 user-visible FPS 修正已採用。下一步只需在取得授權後 scoped reload／restart Pet shell，再以 inspector 實測 FPS 與畫面手感驗收。

## 2026-08-30 pivot zoom / compact host v2 follow-up

- 確認舊縮放只固定腳底 anchor；視覺上等於角色繞腳底放大，因此滾輪所在位置會持續漂移。
- `adjustZoomByWheel` 改為以 `WheelEvent.screenX/screenY` 為固定 pivot，依前後 zoom 比例換算新 screen anchor；renderer 立即套用本地幾何避免畫面先跳一次。
- preload 與 main-process IPC 將 zoom／anchor 合併為單一更新；main process 校正後再用 `pet-zoom-layout-set` 回送 authoritative host／anchor／zoom。
- host contract 升級為 `compact-follow-v2`：基準 `760 x 1280` 不變，zoom envelope 最大限制為 display 寬度 72%、高度 96%，不再長成整張 display 的透明全螢幕視窗。
- 保留向下移出 work area、外緣部分穿出螢幕、透明區 click-through，以及 tray／工作面板重設位置救援。
- Source validation：pivot geometry／layout／mouse／window policy `20 passed`；`main.js`、`preload.js`、`pet-layout.js` syntax passed；renderer typecheck 與 production build passed。Vite 在 sandbox 內遇到既有 Windows `spawn EPERM`，於核准的 sandbox 外重跑成功。
- 尚未 reload live Pet；PID `31632` 的執行中 runtime 仍不可視為採用 `compact-follow-v2`／pivot zoom／frame pacing v5 以上。

## 2026-08-30 live rejection / unclamped placement follow-up

- 使用者提供 `2026-08-30 11-27-26.mov`；逐幀可見角色在連續縮放時卡住外側邊界，之後在不同位置／尺寸間跳動。
- Live PID `52340` 已確認採用 `compact-follow-v2`，inspector host／anchor 一致且 renderer 為穩定 30 FPS；因此這次不是舊 bundle 或低 FPS 假象。
- Root cause：`resolvePetLayout` 仍將 anchor.x 限制在 display 外緣 220 px 內，並限制 anchor.y／host top；pivot zoom 需要 anchor 朝 pivot 反方向移動，一旦被 clamp，主程序回送的位置會破壞可逆縮放並累積漂移。
- 修正方向：`compact-follow-v3` 的 placement anchor 不再做任何 display clamp；display resolver 僅選擇 host sizing context，角色可進入螢幕外或 display gap，找回責任由 tray／工作面板既有 reset action 承擔。
- Regression 新增「anchor 實際越過 display 邊界後，連續放大／縮小仍可逆」案例；pivot／layout／mouse／window policy 共 `21 passed`，syntax、renderer typecheck 與 production build 通過，bundle tag 為 `custom-renderer-2026-08-30-unclamped-pivot-v7`。
- 現行 PID `52340` 仍是影片中的 `compact-follow-v2`；未經 scoped Pet reload 前，不宣稱使用者可見問題已修復。

## 2026-08-30 dynamic model-bounds host v4 follow-up

- 使用者提供的工程規格與目前 source 對照後確認：`compact-follow-v3` 雖解除 anchor clamp，但 `resolveZoomAwarePetHostSize` 仍把 bootstrap host 限制在 display 的 `72% x 96%`；模型在極端 zoom 下會先超過 BrowserWindow，形成螢幕內硬裁切。
- 新 contract 為 `model-bounds-follow-v4`：renderer 每幀從 visible drawable bounds、model matrix、projection matrix 與 canvas viewport 算出全域 screen DIP 邊界；main process 只負責 native host bounds、持久化 anchor／zoom 與 IPC 仲裁。
- host envelope 使用 `96 DIP` safety padding、最小 recovery viewport `280 x 420`、`24 DIP` 擴張 hysteresis 與 `360 ms` lazy shrink；正常 Live2D 頂點運動不會驅動每幀 native resize，模型接近 host 邊界時則立即擴張。
- 模型視覺尺寸改由 viewport-invariant target height 計算，BrowserWindow resize 只增加可繪範圍，不會回饋成第二次 model scale；所有 screen/window/canvas 幾何維持 Electron DIP，不重複套用 `scaleFactor`。
- `/status` 新增 `petHostSizing`、`petModelScreenBounds` 與 `petModelEnvelopeContained`；inspector 也輸出 `modelScreenBounds`，供 live acceptance 判斷是否仍有 host 內裁切。
- Source validation：host envelope／layout／pivot／model screen geometry／mouse policy／window policy 共 `30 passed`；`main.js`、`preload.js`、`pet-host-envelope.js` syntax passed；renderer typecheck 與 production build passed。Vite sandbox 內仍因 child process `spawn EPERM`，於核准的 sandbox 外重跑成功。
- 本輪完成後只讀查詢 `127.0.0.1:23567`，目前 Pet control 未監聽，無 live PID 可供 adoption 驗證。本輪未獲 runtime 啟動／reload 授權，因此尚未宣稱桌面可見問題已修復。

## 2026-08-30 transform ownership / revision v5 follow-up

- Source audit 確認 v4 的 renderer 與 main process 都會提交 anchor／zoom；快速 wheel、authoritative echo 與 host resize 交錯時沒有 revision，因此舊回覆仍可能覆寫新位置。
- 新增 main-owned `PetTransformState { revision, anchor, zoomScale }`。renderer wheel／drag 只送操作意圖；main process 依當下 canonical state 計算 pivot-preserving transform，revision 單調遞增後才廣播 `pet-transform-set`。
- wheel pivot 使用事件當下的 `WheelEvent.screenX/screenY` 快照；避免 IPC 延遲後再讀全域 cursor，導致使用者已移動滑鼠時套用錯誤 pivot。
- `pet-host-set` 已移除 anchor／zoom，只能更新 viewport，且缺少或落後 transform revision 時 fail closed；model envelope 也只接受與目前 revision 完全相符的回報。
- Live2D placement 改用模型初始穩定可見邊界；motion／expression／outfit 的 dynamic bounds 每 50 ms 更新 host envelope，但不再重新定義腳底與水平中心。
- state persistence 保留 anchor 小數精度，避免每次重啟或存檔把 sub-DIP 修正量化成整數而累積漂移。
- Source validation：transform state／revision／command isolation／host envelope／layout／model geometry／zoom／mouse／window policy共 `43 passed`；Electron main/preload/state/helper syntax、renderer typecheck 與 production build passed。
- build 保留既有 `live2dcubismcore.min.js` 非 module script 警告，但 Vite 成功產出 bundle，沒有 compile error。
- 目前 live Pet 尚未 reload；執行中的畫面仍是舊 v4 runtime，不能視為採用 v5，也尚未完成 rapid-wheel 與 5–10 分鐘實機手感驗收。

## 2026-08-30 Pet Geometry Core v2 / actual viewport cutover

- v5 live PID `55888` 已採用 `model-bounds-follow-v5`，transform／envelope revision 均為 `1570`、模型 contained、renderer 30 FPS；但 Main 與 inspector 的 host bounds 來自同一 IPC mirror，無法量測 native actual origin。
- Source 確認 Main 先 `BrowserWindow.setBounds()` 再 broadcast `pet-host-set`；renderer 當時仍用 cached host origin 執行 anchor、pointer、hit test、model screen bounds 與 debug overlay，存在 native move 後再校正的 race window。
- 新增 `pet-viewport-geometry.ts`，以 `window.screenX/screenY + canvas.getBoundingClientRect()` 產生 actual canvas viewport；所有 screen-space conversion 已一次切換，不保留 cached-host production geometry path。
- renderer cached host 改名 `expectedHostBounds`，只服務相容 inspector alias、command reconciliation 與 expected／actual drift telemetry。
- 每個 render frame共用一份 actual viewport snapshot；pointer／screen-hit event 也各自只取得一份，避免同一操作混合兩個 native observation。
- Inspector 新增 renderer build、expected host、actual viewport、origin error、dynamic visual bounds 與 drag lifecycle；Main `/status` 新增 native window／content bounds，同時保留既有 `bounds` 相容欄位。
- `lostpointercapture`、`pointercancel`、blur 與 pointerup 復原策略未改，只新增 finish reason 與次數以供實機歸因。
- Source validation：原 v5 regression 加 actual viewport／host move／resize invariance 共 `50 passed`；Electron main/preload/state/helper syntax、renderer typecheck 與 production build passed。
- Legacy scan：renderer 已無 `this.hostBounds`、`setHostBounds()`、`snapshot.hostBounds` geometry reader或散落的 screenX／screenY 換算；`expectedHostBounds` 僅存在 bootstrap fallback、command reconciliation、相容 inspector alias 與 drift telemetry。
- Production bundle build tag 為 `pet-geometry-core-v2`；Vite 仍顯示既有 Live2D core 非 module script warning，但 build 成功。
- 本輪未 reload live PID `55888`；目前使用者畫面仍是 v5，尚未以實機證明 `window.screenX/screenY` 在 native host move 與 mixed-DPI seam 上符合 <= 1 DIP 驗收目標。

## 2026-08-30 Interaction Freeze A/B proof

- 使用者提供 A/B 工程規格，將「互動期間 native `BrowserWindow.setBounds()` relocation」列為待驗證假設，而非已證實根因。
- 新增 process-scoped `KURO_PET_INTERACTION_FREEZE_HOST=1`；預設 OFF，不形成永久 product setting，也不修改 transform、pivot、ActualViewport、host envelope、hit test 或 FPS。
- pet drag 由 renderer 在成功 model hit 後送既有 `start-window-drag` signal；pointerup、pointercancel、lostpointercapture、blur 與 dispose 仍走既有 `end-window-drag` recovery。
- wheel request 在 Main 建立 `180 ms` zoom burst；Freeze ON 且 drag／zoom active 時，model envelope 仍更新 revision／bounds，但 native relocation 被抑制並保留最新 pending desired host。
- Mode A 不在 interaction 結束時主動 apply pending host；後續正常 envelope 仍可依既有 policy 重新仲裁，避免本輪偷偷引入 settle policy。
- `/status` 新增 flag、active state、pending bounds、suppressed／applied counters 與最近原因；renderer build tag 為 `pet-geometry-core-v2-freeze-ab1`。
- Host envelope policy regression 加入後，全部 Pet targeted tests `51 passed`；Electron main／preload／state／host helper syntax、renderer typecheck、production build 與 `git diff --check` 通過。
- Production bundle tag 已確認為 `pet-geometry-core-v2-freeze-ab1`；既有 Live2D core 非 module script warning 保留，沒有 compile error。
- Freeze ON 冷啟動採用已確認：Pet PID `19336`、instance `19336-mtfkuyaa`，五個 canonical ports 均由新 Launcher lineage 持有，WebSocket／模型 ready。
- Live `/status`：`petInteractionFreezeHost=true`、mode `hold-pending`；`/live2d-inspector`：renderer `pet-geometry-core-v2-freeze-ab1`、viewport origin error `(0, 0)`。
- 實際 drag active 取樣期間，suppressed count `652 → 684`，applied count固定為 `13`，且 `lostpointercapture=0`、`pointercancel=0`；證明互動期間 envelope仍持續進入，但 native relocation已被單一變因抑制。
- 放開後 interaction state回到 false，suppressed count停止於 `733`，applied count由 `13` 增至 `16`；符合本輪「互動中 freeze、結束後由後續正常 envelope重新仲裁」的預期，settle correction仍可能在放開後出現。
- 下一步：由使用者以相同位置／zoom重做拖曳與滾輪，判定互動中的 snap-back是否明顯消失；在取得主觀畫面結果前不宣稱 H1成立。

## 2026-08-30 Fixed Desktop Shell v1 source cutover

- 使用者實機確認 Freeze ON 明顯移除 drag／zoom correction，只剩 compact native host edge clipping；因此 dynamic native BrowserWindow relocation 被確認為主要 snap-back 來源。
- 新增 `pet-fixed-shell.js`：fixed shell 使用所有 physical `display.bounds` 的 union，保留負座標、不同高度與 display gap；不使用 workArea 縮掉 taskbar 區域。
- 新增 derived compact render-surface geometry 與 controller：initial surface 為 `760 x 1280 DIP`，dynamic visual bounds 只調整 surface envelope；anchor、zoom 與 transform revision 仍由 Main `PetTransformState` 唯一持有。
- renderer DOM 在建立 WebGL context 前就先套用 compact surface；後續 translate／resize 只排入 pending 並於 render frame 開頭原子 flush，避免 CSS 先移舊 framebuffer 再下一幀校正。
- Main normal Pet lifecycle 不再使用 model envelope 搬 native window；所有 `mainWindow.setBounds()` 收斂到單一 wrapper，fixed Pet mode 只允許 `startup`、`mode-switch`、`display-topology`、`recovery`。
- 新增 transparent click-through lease／watchdog；renderer load failure、process gone、unresponsive 或 hover lease 過期時清除 interaction 並強制回 passthrough。
- 預設 host contract 為 `fixed-desktop-shell-v1`；設定 `KURO_PET_FIXED_DESKTOP_SHELL=0` 可回到 `model-bounds-follow-v6`，並可搭配 `KURO_PET_INTERACTION_FREEZE_HOST=1` 作 rollback baseline。
- Source validation：全部 Pet targeted tests `58 passed`；`main.js`／`pet-fixed-shell.js` syntax passed；renderer typecheck passed。
- `npm run build:renderer` 在 restricted sandbox 內遇到既有 Vite child-process `spawn EPERM`；核准後於 sandbox 外重跑成功，production bundle 含 `fixed-desktop-shell-v1`。
- 尚未 reload／restart 目前 Pet PID；因此目前桌面畫面仍未證明採用 fixed shell，transparent click-through、mixed DPI、fullscreen 與 CPU／GPU 仍屬 Q3／Q4 pending。
