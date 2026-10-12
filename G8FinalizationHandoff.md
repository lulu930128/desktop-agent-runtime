# Qt G7–G8 最終靜態交接（2026-10-09）

> **2026-10-10 後續現況：G7 33/35／STATIC BLOCKED。** 原權限刪除最後兩檔仍為 `UnauthorizedAccessException (0x80070005)`，兩檔仍在。最新 SHA/CRC/consumer 與 integrity 證據見 [本輪結果](G7FinalTwoResults-20261010.json)，安全補刪指令、原測試重跑及正式桌面清單見 [兩檔收尾交接](G7FinalTwoHandoff-20261010.md)。下方前輪結果保留為歷史；本輪沒有重跑測試。

**STATIC BLOCKED；正式產品 NOT ACCEPTED。** 本輪已獨立重跑靜態／隔離回歸，未啟動正式 Qt、Pet、Core、Conversation 或 Central Voice。Windows 桌面實測由使用者執行。

## 本輪結果

| 項目 | 本輪證據 |
| --- | --- |
| G7 實體刪除 | 原 25 檔＋本輪 8 檔＝33/35；下列 2 檔仍 BLOCKED |
| Production consumer | 323 個現存 production source/config/build/policy 檔掃描，cluster 外引用 0；不代表剩餘 legacy 實體檔為 0 |
| Python root runner | 單次完整 326 tests／25 suites，各 exit 0 |
| Node runner | 83 tests，exit 0 |
| MCP targeted | identity 3＋M0 policy 5＋market routing 6＝14，全部 exit 0；另 OMI policy 4 通過 |
| Renderer | typecheck、build 各 exit 0；86 modules，唯一 index.html entry；保留既有 Cubism classic script warning |
| Syntax／diff | Python in-memory compile 248 檔、node --check 44 檔、git diff --check 均通過 |
| Electron | 最小 data-URL renderer exit 1；原 G8 fixture exit 2147483651；兩者均 renderer launch-failed 49、GPU -1073741515，FAIL |
| 正式 Windows | Qt startup、tray、模型、notification、voice/device 全部 UNVERIFIED |

機器可讀逐項結果、SHA、suite count／exit、例外 stack 與 smoke bootstrap 見 [G8FinalizationResults.json](G8FinalizationResults.json)。原任務目錄拒絕寫入，歷史 JSON／checkpoint 未修改；[G8FinalizationDocs.patch](G8FinalizationDocs.patch) 是尚未套用的文件更新，不冒充已完成更新。

## G7 根因與剩餘檔案

`Remove-Item -Force` 的 `ArgumentException` 已在兩個剩餘檔重現：throw site 是 `System.IO.FileSystemInfo.set_Attributes()`，HResult `0x80070057`，發生在刪除之前。拿掉不必要的 `-Force` 後，本輪 8 個 main-process 舊檔已實際刪除。

剩餘兩檔不加 `-Force` 仍在 `FileInfo.Delete()` 拋出 `UnauthorizedAccessException`（`0x80070005`）；Python `Path.unlink → os.unlink` 同樣回報 WinError 5／errno 13。不是把 `ArgumentException` 直接改名成 ACL 問題。

| 剩餘精確路徑 | manifest／備份／現存 bytes 一致的 SHA256 |
| --- | --- |
| pet-electron/src/briefing-window.html | 17507d1d3e06a3450351bf5ffadc5cb479a1cb91678b819d9b409335d28f0c43 |
| pet-electron/src/briefing-preload.js | e6314e5442bc283fce1b459b4505723eff8b6167a2a81640e0d3d3025cbf8ce2 |

兩檔都是普通檔案，屬性 Archive，沒有 ReadOnly／ReparsePoint。唯讀權限探測顯示目前 token 是 restricted；Win32 `CreateFileW(OPEN_EXISTING)` 的 READ_ATTRIBUTES 成功，WRITE_ATTRIBUTES／DELETE 均被 WinError 5 拒絕。一般 ACL 摘要有 inherited Allow、未見 Deny；尚不能進一步指定哪個 restricted SID、政策、filter 或 handle 是最後原因。未改 ACL／owner／屬性／安全政策，未升權。`handle` 的 EULA 狀態未確認，未為診斷接受 EULA 或改 registry。

## 最窄的人工補刪（2026-10-10 修訂）

原內嵌命令已由 [完整兩檔 guarded 腳本](G7FinalTwoDelete-20261010.ps1) 取代，補上所有父目錄 reparse guard、固定 manifest SHA、ZIP CRC／entry SHA 與 production inventory/bytes guard。使用一般使用者 PowerShell：

```powershell
Set-Location -LiteralPath 'C:\project\desktop-agent-runtime'
.\G7FinalTwoDelete-20261010.ps1
```

可加 `-VerifyOnly` 做唯讀檢查。若 denied 就停止；不加 `-Force`、不升權、不改 ACL／owner／屬性、不改名或刪目錄。腳本只可能刪除 `pet-electron/src/briefing-window.html` 與 `pet-electron/src/briefing-preload.js`，成功後驗證原 manifest 35/35 都不存在。精確 SHA、測試命令與驗收接力見 [本輪交接](G7FinalTwoHandoff-20261010.md)。不重套歷史 `G8FinalizationDocs.patch`。

## Electron 診斷

Electron package／binary version 同為 32.3.3；7 個本地 PE executable/DLL 都是 x64，直接 import 所需檔案在 package 或 System32 可找到。VC++ vcruntime140／vcruntime140_1／msvcp140 均為 14.50.35719.0，ucrtbase 為 10.0.26100.9444。這是本地存在性與 metadata 檢查，沒有可信 distribution archive 可證明整包 bytes 完整，也未驗證所有 delay/runtime DLL loads。

Windows `RtlNtStatusToDosError(0xC0000135)` 回傳 126（找不到模組）；這不指出實際缺少或無權載入的 DLL。近 10 分鐘 Application EventID 1000／electron.exe 篩選無匹配事件。

最小 Electron 對照只載入 `data:` HTML、不 import Kuro，仍重現相同 child failure；因此已確認失敗存在於 Electron／Windows 執行層，不是 Kuro bundle 專屬。確切 DLL／sandbox child 存取原因仍 UNVERIFIED；不能據此保證 Kuro runtime 沒有其他錯誤。

兩次 probe 都使用獨立 repo-local TEMP、userData、sessionData、crashDumps、logs；window 隱藏、無 model/device/provider，未傳入降低安全性的 flags。測試前後均無 Electron process，disposable 目錄已清除。原 fixture 的 FAIL 保留，未改 mock 或 fixture 來製造 PASS。

## 重跑靜態回歸

```powershell
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group python
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group node
npm.cmd --prefix pet-electron run check:renderer
npm.cmd --prefix pet-electron run build:renderer
git -c core.safecrlf=false diff --check
```

本輪保持原測試 runner 的 disposable/offscreen／blocked live ports 邊界。Core／WS transport 是 temporary DB、ephemeral loopback、synthetic provider／tray；未執行正式 runtime。MCP 使用相同隔離環境，另攔截所有 socket.connect，逐 suite 執行 unittest discover；精確 patterns 見 JSON。

## WIP 與文件交接

開始時 main、HEAD 995c23c7c8d1be62000229d58610d2214f3bb745，60 modified／24 deleted／68 untracked。上一輪 127 個 currentHashes 與原始 88 dirty paths 的上一輪狀態全部吻合。8 個刪除檔均通過 manifest／backup／disk 三方 SHA 驗證，包含原有 dirty core-client.js 與 mail-briefing-service.js。其餘既有 WIP 保留。

35 個備份 entry 全相符、CRC 無錯誤，archive SHA 仍為 49c39cccbf702eac763bb3b132d9706432ac564fccfc5c83ac1e6c016288c376。231 個既有 pyc 的 path/hash digest 前後一致，沒有一次性 temp 殘留；未 reset／clean／checkout HEAD、commit／push。

原 checkpoint 目錄在 Codex 執行環境的 Python、apply_patch、PowerShell Set-Content 曾遭拒。**後續獨立 Reviewer 已透過 Project Workspace 的 SHA-guarded patch 成功更新**：G7/G8 checkpoint 最新說明、G8ManualAcceptance（含移除刪除命令的 `-Force`）、Progress、MigrationMatrix、G7DeletionResults、G8ValidationResults，以及 README；並建立 `G7FollowupDeletionResults.json`、`G8ReviewerStaticFollowup.md`。上述更新保留舊測試歷史值；正式 verdict 仍 STATIC BLOCKED。`G8FinalizationDocs.patch` 現僅供差異審計，**不得再對相同工作樹直接套用一次**，以免重複記錄。新增文件未混入先前測試 batch，屬後續證據整理。

## 最少實機驗收

以下全部待使用者操作、記錄時間／source revision＋dirty digest／PID／instance／結果；不由 agent 執行。

| 流程 | 最小可接受觀察 |
| --- | --- |
| Qt startup | 根目錄 VBS 啟動唯一 Qt；第二次啟動喚回同一視窗；auto_start=false 不自行起服務 |
| Tray | X 隱藏、tray 喚回；明確 Quit 收斂自有 child；無第二個 Electron application tray |
| Chat without pet | 無 Pet 仍可送文字；附件、history 切換正常；舊 history capture 不送入新對話 |
| Pet render | 既有模型實際可見、拖曳／DPI／多螢幕正常；Pet 只有 presentation，不持有 business／對話 owner |
| Notification | 使用者自行建立可辨識測試排程；Core claim→authorize→單次 Qt 實際可見→ack；不重複通知，測後由 UI 取消 |
| Voice/device | 使用者另外允許後測 mic／camera／screen、音訊中斷與播完 ack；不由本任務啟停或呼叫 Central Voice |

保持 Mail／Study 原配置；不為展示啟用 provider，不使用真實私人內容作公開證據。G7 實體檔歸零、靜態重驗成功後才可改為 STATIC READY FOR MANUAL ACCEPTANCE；只有實機證據也通過後，產品 verdict 才能另行改判 ACCEPTED。

另有其他流程於本輪期間新增 `G7FollowupDeletionResults.json`、`G8ReviewerStaticFollowup.md`（位於原 checkpoint 目錄）；已保留，不列為本 agent 的修改。最後 worktree 為 58 modified／32 deleted／73 untracked，包含既有 WIP、8 個新刪除、3 個本輪交接 artifact 與上述 2 個外部新增檔。
