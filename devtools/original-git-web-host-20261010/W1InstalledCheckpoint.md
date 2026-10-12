# W1 安裝後實測 checkpoint — 2026-10-10

**W1：BLOCKED（套件檔案讀取權限）。W2–W7：NOT STARTED。**

本輪接續使用者完成隔離安裝後，實際執行 task `.venv` 的四個 import。没有以使用者的安裝陳述當 PASS，亦沒有沿用上輪 cache miss／10013 作為本輪結論。

## 實際環境與結果

- interpreter：`C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\.venv\Scripts\python.exe`。
- `sys.prefix` 為該 task `.venv`，`sys.base_prefix` 為 `C:\miniconda3`；Python 3.13.9，Windows 11 build 26200。
- 一般執行身分實測為 `lulu\codexsandboxoffline`。`require_escalated` 重驗也遭相同 PermissionError；未將其描述為已成功切換到互動使用者身分。
- `QT_QPA_PLATFORM`、`QT_SCALE_FACTOR`、`QTWEBENGINE_DISABLE_SANDBOX`、`QTWEBENGINE_CHROMIUM_FLAGS` 都未設定；沒有寫入或加入安全／GPU override。

| 真實 import | 一般執行 | require_escalated 重驗 |
| --- | --- | --- |
| `PySide6.QtWebChannel.QWebChannel` | PermissionError errno 13，PySide6 `__init__.py` | 相同 |
| `PySide6.QtWebEngineWidgets.QWebEngineView` | PermissionError errno 13，PySide6 `__init__.py` | 相同 |
| `PIL.Image.open` | PermissionError errno 13，PIL `__init__.py` | 相同 |
| `playwright.sync_api.sync_playwright` | PermissionError errno 13，playwright `__init__.py` | 相同 |

套件路徑已被 import machinery 找到；在讀取 package initializer 時遭拒絕，尚未執行 Qt DLL 載入或 GPU 初始化。`importlib.metadata.version()` 對六個 distributions 回傳 null，故版本為 **UNVERIFIED**，不可由套件目錄名稱推定版本或完整安裝成功。Qt `qVersion()` 同樣被套件讀取拒絕阻擋。

最初 `imports-default.json` 的版本欄將 metadata 回傳 null 錯標為 PASS；本輪立刻修正 probe，保留原始 artifact 作為歷程。該欄不可作 acceptance 證據；以 `imports-default-final.json`／`imports-escalated.json` 的 UNVERIFIED 為準。整體 import Gate 從未標記 PASS。

## 唯讀診斷與可確定範圍

- `icacls` 可讀 `.venv\Scripts\python.exe`、`site-packages` 與 `PySide6` 目錄的 DACL，其中有 inherited CodexSandboxUsers 權限。
- 對 PySide6／PIL／playwright 的 `__init__.py` 讀取 DACL 各回 `Access is denied`（各自處理 0 個成功、1 個失敗）；直接 `.NET ReadAllBytes` 讀 PySide6 initializer 也遭拒絕。
- 交叉證據定位在 **目前執行身分對已安裝套件檔案的讀取限制**。目錄可存取不代表其內檔案可存取。因檔案 DACL 本身也無法读取，沒有證明是哪條 ACE、cache hardlink、安裝方式或安全產品造成，不宣稱根因已修復。
- 本輪未安裝／重裝、未外連 PyPI、未改 ACL／registry／machine setting，也未嘗試用另一份正式 env 或停用 sandbox 迴避限制。

`file-access.log` 的外層 PowerShell exit 0 只代表診斷記錄完成；內部 package-file 檢查明確失敗，不能當權限 PASS。`imports-default-final.json` 與 `imports-escalated.json` 對應 Python exit 均為 2。

## W1 驗收狀態

| 表面 | 狀態 |
| --- | --- |
| main／W0、staged 空、原始六檔 SHA | PASS |
| 四項 runtime import | BLOCKED |
| distribution versions／Qt version | UNVERIFIED |
| 安全 Qt profile、WebEngine load／render、bounded synthetic WebChannel | UNVERIFIED，未越過 import stop |
| Chat／Settings／History／Today/Schedule，1280×720／1380×860 × 100%／125%／200% | BLOCKED，24 組均未執行 |
| browser／Qt PNG、DOM geometry、computed CSS tokens、font、pixel MAE／RMS／changed fraction | UNVERIFIED / null，不填 0、不使用舊 screenshot 代替 |
| History drawer、六 Settings groups、composer、焦點／鍵盤、Today/Schedule 互動 | UNVERIFIED |
| Qt screenshot reviewer | UNVERIFIED，無圖可審 |
| W2–W7 | NOT STARTED |

依 Plan W1 與本輪「若 import PASS 才執行 render」條件停止；沒有啟動 Qt／Chrome／Edge 或改 capture helper。上輪發現的 History／Qt interaction／DPI／locale coverage 缺口仍待 import 可用後局部修補並實測，未將現有 helper 視為完整 W1 驗證。

## 修改與證據

- 本輪新增 `w1_import_probe.py` 與本 checkpoint；只寫隔離 task `.runtime/w1-20261010-installed/` 的新 evidence。
- 六個原始 Git source 與 W0／舊來源／SourceVerification 四方 SHA 保持一致。正式 Qt launcher／Core／Pet、正式 env、原本 WIP、master Plan 與受 ACL 阻擋的原 W1Checkpoint 不改；沒有 restart、stage、commit 或 push。
- [證據目錄](.runtime/w1-20261010-installed/)：`before.json`／`after.json`、三份 import probe JSON、`file-access.log`、`GateResult.json`。最終 helper 與 evidence digest、actual exit、矩陣狀態列於 GateResult。
- 結束 guard exit 0：HEAD／branch／六個 source SHA 均符合基準，index byte SHA 未變，task 外 WIP 變更清單為空；391 → 393 paths，差額就是本輪兩個新檔。helper syntax、UTF-8／whitespace、task-scoped `git diff --check` 與 null metadata 保持 UNVERIFIED 的結果檢查均 exit 0。

## 最小重現命令

在需要比較的執行身分下執行同一支 task Python，不需要網路、不修改安裝；每次使用新 evidence 檔名：

```powershell
Set-Location C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010
$w1Probe = '.runtime\w1-import-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json'
& .\.venv\Scripts\python.exe -B w1_import_probe.py --output $w1Probe
$LASTEXITCODE
```

這個命令在一般 PowerShell 成功，仍不能代替 Codex 執行身分的成功；下次必須從實際執行 render 的相同身分重新 import，再開始 W1 渲染。此處不要求更改 ACL。
