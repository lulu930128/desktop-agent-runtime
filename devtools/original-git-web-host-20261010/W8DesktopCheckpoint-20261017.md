# W8 桌面修正 checkpoint：Qt source 通過，Pet 修復受阻

日期：2026-10-17。整體裁定 **PARTIAL**，不是三項問題全部完成，也不是正式 runtime 驗收。

## 範圍與起點

- Checkout：`C:\project\desktop-agent-runtime`，`main`，HEAD `74b372f9c48a16c7deb129faf835970b6b1c2a05`。
- 起始 W7：12 modified + 3 untracked，共 15 paths。全部保留；本輪只在其中 `kuro_launcher/qt_app.py` 疊加局部變更。
- 修改前保存 1,309 個 tracked 檔案的 SHA256、21 份精確 preimage；證據目錄為 repo 下 `.tmp/w8-desktop-20261017/`。
- 六份 ORIGINALS、owner adapters、signed bundles、release pin、W6/W7 gate 與歷史 receipts 未寫入。未 rebuild bundle。
- 未 commit/push/tag、未 restart/kill 正式程序、未改 ACL／系統設定／使用者 anchor、zoom、userData、記憶或設定。

## 已套用的 Qt 修正

1. `qt_branding.py` 只引用既有 `pet-electron/src/assets/favicon.ico`，不複製或重新產圖。驗證 `QIcon.isNull()` 及 pixmap 解碼；缺失或毀損時記錄不含私人路徑的 warning，使用 Qt 標準 fallback。健康資產下 application、window、tray 使用同一 QIcon。
2. 只有 Web 分支使用 parentless `Qt.Tool | FramelessWindowHint`；不新增 owner、tray、WS 或 native handle 管理器，不設 always-on-top／拒絕焦點旗標。Widgets 保持原視窗類型、frame、menu 與最小化行為。
3. Web 最小化透過有 QObject lifetime context 的 `QTimer.singleShot`，在下一個 tick 呼叫既有 close-to-tray。這避免 `showMinimized()` 在同步 hide 後又顯示視窗；已 reveal 或 Quit 時不誤藏。tray 不可用時沿用現有顯示視窗及錯誤訊息路徑。
4. Show／Restart／Quit、tray 單擊／雙擊／訊息點擊、second-launch activation 與 HTML 三按鈕仍使用既有 owner。

Qt 6.11.1 的 [Windows platform source](https://github.com/qt/qtbase/blob/v6.11.1/src/plugins/platforms/windows/qwindowswindow.cpp) 將 Tool 映射為 `WS_EX_TOOLWINDOW`；[Microsoft 文件](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles) 說明這類視窗不列入 taskbar 與 Alt+Tab。這是實作依據，**不是本機 taskbar PASS**。Tool 也可能限制 Win Snap／Snap Layout；實際鍵盤焦點、modal、輸入法、跨螢幕 DPI 及 Snap 均待人工驗收。

## Pet：BLOCKED_PERMISSION_DENIED

Canonical geometry root 已定位於既有 Electron main：`pet-fixed-shell.js` 計算 display union，`main.js` 建立唯一 BrowserWindow、發送 bootstrap／pet-host-set；renderer 的 `PetRenderSurfaceController` 與 `PetLive2DRenderer` 消費這個 frame。

使用者提供的 13:50 live 證據：virtual shell 5120×1440，native window/content 2560×1440，model left≈2772，因此完全落在 native content 外。本輪沒有重新驗證該 PID 或 live 狀態。constructor 的底層 clamp 原因仍未最終證明。

另確認 `petCapability()` 只以 displays 判斷 model 可見，沒有 native content intersection，因此該 snapshot 的 ready/visible 不足以證明真正可見。`pet-layout` 被 fixed-shell whitelist 拒絕是既定保護，不應刪除。

阻塞紀錄：

- `Get-CimInstance Win32_Process`：`PermissionDenied`／`0x80041003`。
- `Get-NetTCPConnection`：`PermissionDenied`。
- `apply_patch` 寫入 `pet-electron/src/main-process/pet-fixed-shell.js`：`Failed to write file`。
- 使用者明確停止指示抵達前，另一次同路徑 Python 寫入得到 `PermissionError: [Errno 13] Permission denied`。
- `Get-Item` 顯示不是 read-only attribute；ACL 可讀，但不足以區分最後拒絕來自 OS、sandbox 或其他 policy。沒有更改 ACL／attrib、提權、替換檔案或啟動程序；收到停止指示後沒有再嘗試被拒寫入。

**正式 Pet main、fixed-shell、status 全部與起始 preimage 相同。沒有單獨改 status 掩飾 geometry 問題。**

停止指示抵達前已保存的 `.tmp/w8-desktop-20261017/candidate/` 僅為未套用、未測試提案，未 import／執行／發布。另保存 `PetProposal.UNAPPLIED.patch` 供工程討論；不得視為可直接採用的修復。

後續方案需在寫入邊界由使用者另行處理後重新審核：

1. 在既有 main owner 的合法 startup／topology 階段套用 union，隨即讀回 `getContentBounds()`；renderer frame 必須用實際 native content。
2. 若 spanning 仍被 clamp，評估 bounded、可觀察的 anchor 所在 display shell，不重設 anchor／zoom、不強迫 primary。拖曳／縮放期間維持 freeze，禁止 envelope 任意重定位；跨螢幕接續 recovery 需獨立驗證，未驗證前不採用候選設計。
3. 純讀 status 增加 `visibleWithinNativeContent`／`hostClip`，以 model、display、native content 的共同可用交集判 visible；未知 native geometry 不得 false-ready。讀取不能寫入、移動或重啟。
4. 加入精確 2×2560／model x2772 fixture，涵蓋 constructor clamp、持續 clamp、第二螢幕、負座標、不同 DPI、oversized partial model、interaction freeze、topology、拒絕 pet-layout、讀取零副作用。**這些 Pet regression 本輪未實作／未執行。**

## 驗證證據

正式 Python：repo `envs/kuro-llm310/python.exe`，Qt **6.11.1**；Qt platform 為 `offscreen`。WebEngine surface inert，controller／私有 settings／正式網路隔離；不啟動 Chromium renderer 或正式服務。

| 項目 | 結果 |
| --- | --- |
| Python Qt targeted regression | 59 tests，0 failures，0 errors，0 skipped，exit 0 |
| Node Qt frontend regression | 20 tests，20 pass，0 fail／skip，exit 0 |
| W8 Qt source/pin gate | `W8_QT_SOURCE_PIN_VERIFIED`，exit 0 |
| Python source syntax | exit 0 |
| `git diff --check` | exit 0 |
| 隔離 mirror W8→W7→W8 | 精確 SHA／compile 通過；checkout 未回滾 |
| Windows taskbar、Snap、focus／modal、正式 Live2D | UNVERIFIED；Pet 修復 BLOCKED |

圖示測試包含真實 ICO decoder、16/32/64/256px 解碼與 application/window/tray 像素及 cache key 一致；fallback 包含 missing/corrupt。其餘涵蓋 tray lifecycle、延遲最小化 race、Widgets rollback、既有 native gesture guard、Chat transport、Today/Core projection。

初輪 `QtTargeted.log` 保留 29 tests／1 failure（同步最小化 hide 問題）。`validation-2/` 保留 syntax-check runner 缺括號失敗；runtime tests 當輪已通過。兩項均已修正，最終 `validation-final/Results.json` 五個 command groups 全部 exit 0。沒有將先前失敗刪除或改寫成成功。

重現指令（output 必須是未存在的新目錄）：

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
.\envs\kuro-llm310\python.exe -B .\devtools\original-git-web-host-20261010\validate_w8_qt.py --output .tmp\w8-review-new
```

本 profile 是 Qt targeted scope，**不是 W7 全量 profile PASS**。W7 exact gate 對 `qt_app.py` 應拒絕；新版 gate／manifest 明列 `EXPECTED_SOURCE_DRIFT`，不修改歷史 W7 expected SHA，也不重用 W6 native acceptance。W7 signed fingerprint 仍為 `8ba8ea29313601f944f760b901410efb8fc92bc801199d3b0b72ba22b7fa9b14`。

## 回復 checkpoint

- `Before.json`：起始 HEAD／Git status／1,309 tracked hashes／21 preimages。
- `Integrity.json`：既有 tracked 檔案只有 `qt_app.py` 與起始不同；另 20 preimages 完全相同，15 W7 paths 保留，Pet source 不變。
- `RollbackRoundtrip.json`：新建 mirror 中測試 W8→W7→W8；W7 階段移除的只有剛建立的 mirror helper，從未移除 checkout 檔案。
- `W8QtSources-20261017.json`：30 份 exact source／test／icon hashes；不包含私人 runtime state。

`qt_app.py` W7 preimage SHA：`ff6d7ad5894647df4fc25097931afa8126b8ce10ceb9f18f2e5f650397cf3096`。

`qt_app.py` W8 SHA：`00487ea9021c9af010cc33551b694425247517330cf02e8cb80e5c1643fc392c`。

`qt_branding.py` W8 SHA：`10fdd978ba21ed026b10bdde6dc137dcf3e1656b055cf77366727d7ed0e276c0`；W7 時不存在。

若日後明確授權回復 W7：先比對目前檔案等於 W8 SHA、有任何新 WIP 即停止；只還原本 checkpoint 的 `preimages/kuro_launcher/qt_app.py`，並另行處理本輪新增且 W7 不引用的 helper／tests／gate。保持原 W7 pin、adapters、bundles 不變，不可使用 HEAD 版本覆蓋 W7 WIP。此處僅記錄回復方案，未執行正式 checkout rollback 或 runtime restart。

後續正常 Windows session 驗收必須另有啟動授權：UI 顯示時 taskbar 無按鈕、tray 圖示正確、Show／X／minimize／second launch／Restart／Quit、Chat／Today、modal／IME／focus、Alt+Tab 取捨、Snap 與雙螢幕 DPI。Pet 在 source 修復受阻時仍不得標記完成。
