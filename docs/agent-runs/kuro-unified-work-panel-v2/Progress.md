# 進度紀錄

## 目前狀態

程式與 production renderer 已完成；本輪新增的麥克風暫停／繼續／明確送出／取消流程尚未套用到目前執行中的 Kuro，需精確重啟後再做真實麥克風與 WebSocket 驗收。

## 已完成

- 讀取 `ProductVision.md`、`OperatingModel.md`、`QualityBar.md` 與工程企畫書。
- 確認使用者最後決策：單一工作面板，模式為普通對話與今天／行事曆，設定固定左下角。
- 確認現有 Briefing store 已提供 `today.levels`、`today.items`、`sections`、`sourceStatus`、`mail`、`study`。
- 確認現有 Reader contract 可送出文字與附件，並收到即時 AI state。
- 修改前 `npm run check:renderer` 通過。
- 修改前 `npm run build:renderer` 在 Vite config 載入階段遇到 sandbox `spawn EPERM`；尚未進入原始碼 bundling。
- 新增 Vite `work-panel.html` 與獨立 TypeScript/CSS 模組。
- 完成普通對話、Today／行事曆、來源 filter、共用詳情與左下角設定。
- 普通對話可讀目前 active history，並沿用既有文字／附件傳送與 interrupt contract。
- Today 沿用 backend 分級，Mail 詳情維持按需讀取且不下載附件。
- tray 與桌寵右鍵選單新增單一「Kuro 工作面板」入口與停止輸出。
- 最終 `npm run check:renderer`、Node syntax 與 `npm run build:renderer` 通過。
- 以本機 production build 檢查 1280×800 的 Today／Chat／Settings，以及 860×620 窄視窗；browser console 無 warning/error。
- 確認 `桌寵啟動器.vbs` 原本只啟動 `launcher_qt.py`，且 launcher 會硬性顯示舊 Qt 主視窗。
- 新增 `--work-panel` 啟動模式：Qt orchestrator 完全隱藏在背景，profile ready 後透過既有 allowlist 開啟唯一的工作面板。
- 保留直接啟動 `launcher_qt.py` 的診斷入口；自動啟動失敗時會恢復 Qt 控制台。
- 以 live pet control API 成功開啟新版工作面板；`briefingVisible=true`、renderer 同步為 true、WebSocket connected。
- 重新啟動後，launcher log 顯示新 Qt window `visible=False`、`minimized=False`；Windows 視窗清單沒有 Qt 控制台。
- Windows 視窗盤點只有一個「Kuro 工作面板」主操作視窗；`Kuro Pet Renderer` 是無工作列的 Live2D 覆蓋層。
- Runtime status 驗證 `bridge`、`tts`、`llm`、`pet_shell`、`ws_connected` 與 `briefing_visible` 全部為 true。
- 重現 `briefingVisible=true` 且 Windows 存在「Kuro 工作面板」，但視窗實際落在其他應用後方；將該精確視窗 raise 後立即恢復。
- 右鍵／tray 選單改為固定「顯示 Kuro 工作面板」，避免把 Electron visibility 誤當成使用者看得到。
- 新增共用 reveal 流程：restore minimized window、校正 bounds、show、moveTop、Windows app focus 與 window focus。
- `minimize`、`restore`、`closed` 與 `loadFile` failure 現在會同步真實狀態；`/status` 增加 focused、minimized 與 bounds 診斷。
- 現場取樣發現兩個同路徑隱藏 Qt launcher；新增 Windows 單例 mutex，第二次 VBS 啟動改為要求既有工作面板顯示後退出。
- `launcher-single-instance-check` 已驗證第一個 process 取得 mutex、第二個 process 被正確拒絕。
- 本輪 Node syntax 與 `npm run check:renderer` 通過；`npm run build:renderer` 首次受 sandbox `spawn EPERM` 阻擋，核准後在 sandbox 外通過。
- 以原始 `桌寵啟動器.vbs` 做乾淨重啟後，四個固定 listener 全部恢復；新版 `/status` 回報 `briefingVisible=true`、`briefingFocused=true`、`briefingMinimized=false`。
- 主螢幕擷取確認新版「Kuro 工作面板」位於 OMI 視窗前方，能直接看到普通對話、Today 與左下角設定入口。
- 再次執行相同 VBS 前後，Kuro `pythonw.exe` launcher 數量維持 `1 -> 1`，probe process 正常退出且既有面板重新取得焦點。
- 新增 `127.0.0.1:23568` launcher control API，profile、history、memory 與 tool policy 都由既有 Qt controller 提供，renderer 不直接讀寫來源檔。
- Launcher 每次啟動產生臨時 bearer token，只透過 child-process environment 傳給 Electron main；未授權 request 會回傳 `401`。
- Profile、長期記憶與對話刪除在 Electron main 顯示原生確認視窗，確認後才代理到 launcher control API。
- 對話模式加入覆蓋式歷史抽屜、新對話／切換／刪除、角色／模型／推理 selector、麥克風／鏡頭／本回合螢幕與持續 privacy indicator。
- 設定改為一次一個分類，接回角色／專案／模型、對話保存、長期記憶、工具政策、感知功能與桌寵外觀。
- 修正 Qt 的 `low / high` 與 runtime `fast / deep` 對映落差，統一為 `fast / normal / deep`。
- 新增 launcher control unit tests；Python syntax、5 個 API tests、Node syntax、renderer typecheck 與 production build 通過。
- 以 production build 實際檢查 1280 寬 Today／Chat／History／Settings 與 800 寬 Settings／Chat；瀏覽器 console 無 warning/error。
- 麥克風改為明確錄音流程：開始後可暫停／繼續，只有按「完成並送出」才建立語音回合；「取消」會丟棄錄音。
- 對話 composer 與設定頁共用相同麥克風狀態，暫停時仍顯示 privacy indicator，並以不同狀態色避免誤認為已關閉。
- 本輪 Node syntax、renderer typecheck 與 production build 通過；650×900 production 頁面無水平溢出，隱藏錄音 action 在 idle 時不佔版面，browser console 無 warning/error。
- `桌寵啟動器.vbs` 現在只使用 repo 內的 Kuro Python，並先驗證新版 `renderer-dist/work-panel.html`；缺少 build 或環境時會明確報錯，不再退回系統 `pyw`。
- `--work-panel` 改為 fail-closed：既有工作面板無法顯示或 startup 失敗時，不再喚出舊 Qt 控制台，維持單一面板產品入口。
- Launcher Python syntax 與 5 個入口測試通過；本輪依使用者要求未實際啟動 GUI/runtime。
- 修正 Windows Script Host 將 UTF-8 無 BOM 中文 VBS 誤判為系統碼頁、造成 `800A0401` 編譯失敗；VBS 原始碼改為純 ASCII，並新增 `/check` 無副作用編譯檢查。
- `cscript //nologo 桌寵啟動器.vbs /check` 與 5 個入口測試均通過，且檢查過程未啟動 Kuro runtime。

## 重要決策

- 使用現有 `briefingWindow` 作為工作面板相容容器，不建立第四個主要視窗。
- 保留舊 Reader 檔案與 IPC 作過渡，不把它當新產品入口。
- 採 Vite + Vanilla TypeScript，不導入 React。
- 視覺方向為「月夜工作台」：深靛墨色、月光紙白、月藍與安靜青綠；狀態色只表示資料／感知狀態。
- 普通對話與 contextual handoff 共用同一 composer；上下文由使用者可見文字帶入，不建立隱藏 project chat。
- Launcher control token 不進 renderer、設定檔或 git；工作面板只能透過 Electron main 的窄 IPC 呼叫。

## 已知限制

- Briefing 資料未提供真實排程時，Today 只顯示未排程空狀態，不生成假行事曆。
- Browser panel 在既有 renderer 只有 boolean state，沒有真正的瀏覽／上下文面板，因此本輪沒有放一個看似可用的假按鈕。
- 本輪沒有重啟目前執行中的 Kuro；麥克風暫停、繼續、取消與完成送出的真實 Windows 權限／音訊／WebSocket 路徑仍待 live 驗收。

## 下一步

取得使用者同意後，只重啟 Kuro launcher／pet shell，實測一段「錄音 → 暫停 → 繼續 → 送出」與一段「錄音 → 取消」，確認只有明確送出的那段進入對話。
