# Work Panel 啟動與恢復

## 範圍與決策

2026-09-13 使用者在唯讀確認後授權實作。Launcher 是 Electron lifecycle 唯一 owner；VBS 只送出啟動意圖。保留既有 dirty work、Core／MCP／Memory／TTS，日常入口維持新版工作面板。

- activation request、開始、結果以相同 request_id／source 記錄到 `launcher.combined.log`。Electron 啟動 stdout/stderr 另存 `launcher_logs/pet-electron/<instance>.log`。
- 失敗提供獨立、非阻塞、可重試的恢復提示；不回到舊控制台日常操作。
- Electron `/status` 與 `/command` 增加 `workPanel` contract v1；既有 `renderer.briefingVisible` 保留。`ok` 是 control acknowledgement，ready 另看 window contract。
- Work Panel ready 需要 exists／visible／非 minimized／rendererReady／responsive／非 loading／displayMatch。focus 僅供診斷，不因切換程式而 restart。
- rendererReady 只表示面板 shell 與操作 handler 已建立，不表示來源 current 或 Core／LLM 上線。
- 每次合併後的 activation 最多一次恢復。重新讀取 fresh status，延遲成功時只重試 reveal；需要替換時只終止持有的 Popen handle。
- service／protocol／PID／instance／sourceRoot／listener 必須一致。未知 listener 或錯誤 instance 停止恢復；不收養 HTTP 回傳 PID 來自動終止。
- Core unavailable 保留原本連線環境傳遞；不自動發送、刷新外部來源或操作私人排程。

## 驗證

- Python syntax：通過。
- `python -B -m unittest discover -s tests -p test_pet_lifecycle.py`：17 tests PASS。
- `python -B -m unittest discover -s tests -p test_work_panel_activation.py`：5 tests PASS；獨立 Qt recovery dialog 可見／非 modal，重試需要明確點擊，關閉提示不會退出背景 Launcher。
- `python -B -m unittest discover -s tests -p test_launcher_entrypoint.py`：5 tests PASS。
- `python -B -m unittest discover -s tests -p test_work_panel_api.py`：7 tests PASS。相關 Python regression 合計 34 tests。
- `node tests/work_panel_window.test.cjs`：4 tests PASS；涵蓋真實 display 間隙、renderer timeout、instance mismatch 與 HTTP 回應上限。
- `npm run check:renderer`、`npm run build:renderer`：PASS。Build 在沙箱受 spawn EPERM 限制，經允許的正常環境重跑通過；原有 Live2D script type=module 警告仍在。
- 隔離 Electron window smoke：9 checks PASS，正式 renderer、臨時 profile/port、offline sources，截圖已檢查。涵蓋 close/hide、minimize、off-screen、重複 reveal、renderer crash、destroy/recreate。
- `tests/work_panel_process_smoke.py`：5 checks PASS，exit code 0；使用真實 Launcher controller 與隔離 Electron child fixture。第一次 renderer crash 後僅替換一次；隱藏後重新顯示沿用相同 instance，連續啟動不新增子程序；子程序退出後可重新建立，Core failure 不阻塞面板。
- `git diff --check`：PASS；未 commit／push。

## 證據與執行方式

隔離輸出在 `launcher_logs/work-panel-validation/`，不應提交 git。

```powershell
.\envs\kuro-llm310\python.exe -B tests/work_panel_process_smoke.py
$run = Start-Process -FilePath .\pet-electron\node_modules\electron\dist\electron.exe -ArgumentList .\tests\work_panel_electron_smoke.cjs -WindowStyle Hidden -PassThru -Wait
$run.ExitCode
```

## 正式採用與限制（第一階段歷史記錄）

本輪未重啟既有正式 Launcher／Core／Bridge，也未改動正式記憶、排程、TTS 或外部 provider。既有 Launcher 需正常退出後，由根目錄 `桌寵啟動器.vbs` 重新啟動，才會載入新 Python source。

15:52 唯讀核對：原 Launcher／Core／Bridge 仍為原本 PID 與啟動時間；測試 Electron 已全部退出。

隔離測試不是正式 VBS／Windows activation event 的完整桌面驗收。正式 cold start、二次 VBS 喚回、快速重複 VBS、真實失敗提示的操作驗收尚待採用後執行。

回退時只移除本輪 lifecycle/helper/test hunks，保留其他既有變更與新記錄資料；不可 broad reset、刪除 profile 或停止共用 TTS。

## 第二階段：獨立載入與可恢復啟動（2026-09-13）

使用者授權依長期方案實作，並追加「舊版不需要兼容，可以直接移除」。本階段已完成 source、隔離故障測試與正式 runtime 採用。

### 原因與修正

- 原本中央 TTS 未上線會阻擋 LLM 啟動；桌寵又等待 LLM 的模型 metadata，因此面板存在時仍可能同時沒有對話與桌寵。中央 TTS 現在是可降級能力，健康檢查不合成音訊，失敗保留文字；完全無音訊的回合不等待 playback acknowledgement。
- `runtime_lifecycle.py` 保存 desired state、啟動階段、錯誤、boot ID、source revision 與最多兩次自動恢復；並行啟動合併，短暫成功不清除恢復預算，明確停止不自動復活。
- Launcher catalog 維持角色／模型來源；`presentation.py` 與 `local-model.js` 只放行模型目錄內已登錄的資產，Electron 用 `kuro-model://local/` 獨立載入。移除從 LLM HTTP 模型位址回退的分支。
- `pet-visibility.js` 依實際模型邊界與螢幕工作區修復離屏位置，保留有效負座標。啟動、模型 ready、螢幕配置變更均會檢查。
- 面板分別呈現對話、語音與桌寵狀態，診斷頁提供啟動重試、停止、位置恢復、模型重新載入與 Kuro 重新啟動。API 仍使用 Launcher session token 與明確確認；token 不進 renderer。
- 移除舊 Qt 控制台的入口、喚回事件與 mode 分支，VBS／直接 Launcher 都只開工作面板。Qt 仍作內部背景服務容器，不是日常相容介面；既有資料與其他 dirty source 保留。
- 隱藏 Qt 容器可能沒有原生視窗，且 close 後不一定結束事件迴圈。新版重新啟動會先清理自身服務，再明確退出 QApplication；`relaunch.py` 等待原 owner 退出後才啟動同一 checkout，逾時不產生第二個 Launcher。
- 本次 VBS 改檔曾引入 UTF-8 BOM，實際快速啟動抓到 Windows Script Host 解析失敗；已改回 ASCII、加入編碼 regression 並通過 `cscript //NoLogo //B 桌寵啟動器.vbs /check`。

### 中央語音的獨立常駐

在中央工作區 `C:\project\voice package\GPT-SoVITS` 新增 `scripts/voice_supervisor.py`、`scripts/install-autostart.ps1` 與 `SERVICE-LIFECYCLE.md`。使用原有 Python 環境，file lock 保證單一 supervisor；只恢復自身啟動的子程序，不清除未知 listener，五次失敗後停止自動重試。

目前使用者 Startup 已安裝 `Central Voice Runtime.lnk`，指向中央環境的 pythonw 與 supervisor。第一次真實重複執行抓到 Windows 已鎖定 byte 不可讀的問題，已修正為不讀鎖定 byte；新版重複啟動 exit 0，owner 不變。健康檢查沒有載入 GPU 模型或合成音訊。

### 本階段驗證

- Python 49 tests PASS：runtime capabilities 8、central voice 5、pet lifecycle 17、work-panel activation 6、API 8、Launcher entrypoint 5。另以 in-memory compile 檢查 10 個相關 Python 檔案。
- Node 7 tests PASS：`node tests/pet_capabilities.test.cjs` 3、`node tests/work_panel_window.test.cjs` 4。`node --test` 的子程序啟動受 sandbox EPERM 限制，改用直接執行同一測試檔通過。
- `npm run check:renderer`、`npm run build:renderer` PASS；只有原有 Cubism classic script bundling 警告。
- Work Panel 隔離 Electron 9 checks PASS（16:58），涵蓋真實 renderer、視窗隱藏／恢復、離屏、crash、destroy/recreate 與 offline navigation。
- 最終離線桌寵 smoke 4 checks PASS（17:10）：正式 main／preload／renderer、無 LLM 仍載入本機模型、保存的離屏位置恢復、backend 維持 offline。證據與截圖在 `launcher_logs/work-panel-validation/pet-offline-result.json`、`pet-offline.png`。
- 實際 relaunch helper 已成功等待舊 owner 退出並啟動新版；新版 Qt restart method 的 cleanup／quit 路徑另有 targeted test。
- `git diff --check` PASS，未 commit／push。

### 正式採用證據

17:11:28，正式入口快速啟動五次，均沿用同一 Launcher 55768 與 Electron 54924，instance `08b7045bb5064663a84878505db66cef`。Work Panel visible／rendererReady／responsive／displayMatch 全為 true；LLM WebSocket connected=true、aiState=idle；實際 Kuro 模型使用本機 protocol，桌寵 modelReady／visible／responsive 全為 true。

執行與磁碟 revision 均為 `4ec717c96ee9140d`，restartRequired=false。原先的 Launcher 3624／53720 與各自持有的舊 Kuro 子程序均已退出，新版採用已完成。原始回應只保存必要狀態於忽略的 `launcher_logs/work-panel-validation/formal-runtime-result.json`，不保存 token 或私人對話內容。

中央 supervisor 最終 PID 50784；共用 gateway PID 36304 自 16:45:41 持續存活，Kuro 版本切換未停止它。`/health` service=voice-runtime、protocol_version=1、status=available、model_loaded=null。

### 剩餘驗收範圍

未登出／登入 Windows，因此登入後自動啟動尚未實測；捷徑 target、args 與 supervisor 實際啟動已驗證。未發出付費 LLM 對話或真實語音合成，語音聽感與播放驗收仍獨立進行。未實際拔插螢幕；離屏／負座標與真實顯示器 geometry 已測。原生「重新啟動 Kuro」確認按鈕未人工點擊，backend handler／Qt method／實際 relaunch helper 分別驗證。

## 拖曳彈回回歸修正（2026-09-13 17:32）

使用者回報角色移動後彈回固定位置，並要求滑鼠穿透預設關閉。根因是第二階段將 `repairPlacement` 放在每次模型 envelope／heartbeat 的處理中，且要求模型完整落入單一螢幕。放大角色與靠邊拖曳在放開後再次觸發修正，模型動畫也可能反覆改變 transform revision。先前只驗證「可見」的 smoke 未涵蓋這項回歸。

- `main.js` 改為啟動／螢幕配置改變後的一次性恢復；有效使用者拖曳或縮放會取消待處理恢復，普通模型 heartbeat 不得改寫位置。
- `pet-visibility.js` 保留有可操作可見區域的部分離屏、放大與跨螢幕模型。啟動時先保留保存的 anchor，再以真實模型邊界決定是否找回，不再只用 anchor 是否位於螢幕內判斷。
- `state.js` 的 `forceIgnoreMouse` 預設 false；移除每次啟動強制 true 的覆寫，保存使用者選擇。透明區仍維持原本穿透行為，角色本體可操作。
- 新增 `tests/pet_placement_smoke.cjs`：正式 main／preload／renderer、隔離 userData、離線 backend，透過正式 preload 的 drag／transform IPC 驗證放開後兩次 heartbeat 仍保留位置。修正前可重現 Y=1738.90 被拉回 1497.47；修正後 6 checks PASS，涵蓋初始離屏恢復、拖曳放開、跨實際顯示器移動、放大與動畫、模擬 topology 事件的一次恢復、真正啟動流程的穿透預設。此為 IPC 互動測試，不宣稱人工滑鼠操作或實際拔插螢幕驗收。
- Node targeted regression 共 17 tests PASS：capabilities 5、transform state 5、renderer revision 2、mouse policy 5；三個變更 JS 檔 syntax check 與 `git diff --check` PASS。沒有 renderer source 變更，不重建 renderer。

正式套用：當時 Electron 已退出，因此先核對 Launcher 55768 與其三個既有子程序身分，只重啟該組 Kuro，保留共用語音。17:32:42 新 Launcher 16204、Electron 57176，source/disk revision=`55bd8fdf4fc79295`、restartRequired=false，面板 ready、WebSocket connected、桌寵 ready。連續三秒位置與 revision（121）不變，forceIgnoreMouse=false。證據位於忽略的 `launcher_logs/work-panel-validation/pet-placement-result.json` 與 `pet-placement-formal-result.json`。未 commit／push。
