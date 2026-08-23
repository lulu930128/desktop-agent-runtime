# 實作計畫

## Milestone 1：基線與邊界

- [x] 讀取產品文件、工程企畫書與 repo instructions。
- [x] 確認 Electron Reader／Briefing／Pet 與 Qt 的現有責任。
- [x] 記錄修改前 renderer typecheck 與 build 結果。

驗收：確認只需改 Electron consumer 與相容 IPC，不碰 domain truth。

## Milestone 2：工作面板骨架

- [x] 新增 Vite 多入口 `work-panel.html`。
- [x] 建立工作面板的 token、layout、view model 與 DOM 入口。
- [x] 將既有 Briefing BrowserWindow 指向新入口，保留內部 contract。

驗收：工作面板可載入，三個主入口和右側詳情結構成立。

## Milestone 3：功能接線

- [x] 對話接回 `reader-send-text`、active history 與附件。
- [x] Today 接回 Briefing snapshot、today classifier 與各來源 section。
- [x] Mail 詳情沿用既有按需讀取 contract。
- [x] 設定只暴露 allowlist 內桌寵控制與本機顯示偏好。
- [x] tray／右鍵選單增加單一工作面板入口。

驗收：主要功能都在同一視窗完成，資料狀態不被 UI 改寫。

## Milestone 4：驗證與收斂

- [x] `node --check` 檢查 main/preload/menu。
- [x] `npm run check:renderer`。
- [x] `npm run build:renderer`。
- [x] 檢查 build artifact 與主／窄視窗 responsive layout。
- [x] 以本機 production build 取得 Today／Chat／Settings 與窄視窗 screenshot，完成視覺複查。
- [x] 更新 Progress 與已知限制。

驗收：沒有新增編譯錯誤，工作面板在可驗證的 UI 表面成立。

## Milestone 5：預設啟動入口採用

- [x] 確認 `桌寵啟動器.vbs` 仍需透過 Qt launcher 擁有 runtime orchestration。
- [x] 新增工作面板啟動模式，讓 Qt 完全在背景運作並在 profile ready 後開啟 Electron 工作面板。
- [x] 保留直接啟動 `launcher_qt.py` 的完整診斷控制台。
- [x] 啟動或工作面板開啟失敗時，恢復 Qt 控制台供使用者處理。
- [x] 以 VBS 重新啟動做端到端可見驗證。

驗收：一般入口只有新版工作面板可見，Qt 只保留背景服務管理與失敗時的故障診斷能力。

## Milestone 6：首次顯示與前景狀態修正

- [x] 重現選單顯示「收起」但工作面板落在其他應用後方的假陽性。
- [x] 將所有顯示入口統一為 restore、座標校正、show、moveTop 與 focus。
- [x] 選單改為固定「顯示 Kuro 工作面板」，不再用 visibility 猜測使用者是否看得到。
- [x] 補上 minimize／restore／load failure 的實際狀態同步與診斷欄位。
- [x] Launcher 加入 Windows 單例 mutex；再次執行 VBS 只要求既有工作面板回到前景。
- [x] 通過 Node syntax、renderer typecheck 與 production build。
- [x] 重啟 Electron runtime，驗證首次開啟、被其他程式遮住後再次顯示及選單文字。

驗收：選單不再出現錯誤的「收起」狀態；呼叫顯示後，唯一工作面板必須實際位於前景且可擷取。

## Milestone 7：完整功能接回與單一舞台改版

- [x] 建立 loopback-only launcher control API，提供 profile、history、memory 與 tool policy 的窄 contract。
- [x] 對話模式加入覆蓋式歷史抽屜、新對話、切換與確認刪除。
- [x] 接回角色、專案、模型與 canonical `fast / normal / deep` 推理深度。
- [x] 接回麥克風、鏡頭與本回合螢幕擷取，並持續顯示 privacy state。
- [x] 設定改為單一分類內容，加入記憶審核、工具政策檢視與桌寵外觀。
- [x] 以月藍／青綠 token 與窄導航脊柱重整視覺，保留 Today 真實資料狀態。
- [x] 通過 Python、Node、renderer typecheck/build 與 production build 的實際瀏覽器 screenshot 驗證。
- [ ] 重新啟動目前正在執行的 Kuro，驗證 session token、原生確認視窗與 live profile/history/memory payload。

驗收：一般入口只開一個工作面板，且使用者可在其中完成主要對話、歷史、感知、profile、記憶檢視與桌寵設定；資料 owner 與確認邊界不被 renderer 繞過。

## Stop-and-fix 規則

- 若既有 dirty diff 與本次修改重疊，先縮小 patch，不覆蓋使用者內容。
- 若 renderer state 缺少資料，顯示空狀態或 unknown，不建立假資料。
- 若某設定無法透過安全 allowlist 落實，不做假按鈕。
- 若 build 只因 sandbox `spawn EPERM` 失敗，改用核准的同一指令重跑；其他錯誤先修正再繼續。
