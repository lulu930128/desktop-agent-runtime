# Work Companion V1 checkpoint

日期：2026-10-10。結論：**V1 synthetic preview source ready；產品及 V2 正式接線未接受。**

這是一個可重用的 Qt Widgets 呈現層，以及明確 opt-in 的匿名合成預覽。正式入口仍是 `launcher_qt.py` / `KuroQtLauncherWindow`。本輪沒有改動既有 source 或啟停任何正式服務。

## 新增範圍

| 檔案 | 責任 |
| --- | --- |
| [qt_work_companion_view.py](../../kuro_launcher/qt_work_companion_view.py) | QWidget、display dataclasses、頁面、drawers、原生輸入與 intent signals；沒有 controller／service／network／IO imports |
| [qt_work_companion_theme.py](../../kuro_launcher/qt_work_companion_theme.py) | 圖 A/B tokens、scoped QSS |
| [preview_work_companion_v1.py](../preview_work_companion_v1.py) | opt-in host、page/state/size/scale 選項、獨立 QApplication、顯式 PNG 輸出 |
| [work_companion_synthetic.py](../work_companion_synthetic.py) | 匿名 fixtures、記憶體內 preview model、可取消的固定回覆 timer |
| [test_v1_work_companion_view.py](../../tests/test_v1_work_companion_view.py) | offscreen 互動、layout、狀態、字型、DPI、IO／import boundary 與本次 source integrity |
| [V0Baseline.md](V0Baseline.md) | 使用者描述、Git 純視覺來源、精確 tokens／幾何、未確認版本 |
| [SourceIntegrityBaseline.json](SourceIntegrityBaseline.json) | 開工時 170 WIP status、373 source hashes、G7 35 路徑、tracked diff／index hashes |
| [ValidationResults.json](ValidationResults.json) | 測試原始輸出、各 screenshot command、exit、logical／physical size 與 widget 幾何 |
| [SourceIntegrityResult.json](SourceIntegrityResult.json) | 結束時新增 allowlist、前後 status／hash／G7 比對與文字檢查 |
| [previews](previews/README.md) | 8 張 Qt 原生合成 PNG 及說明 |

文件與圖片原定放在 `docs/agent-runs/kuro-work-companion-ui-v0-v1-20261010/`。
`apply_patch` 無法建立父目錄；針對該新目錄的審核後 `New-Item` 仍回 `UnauthorizedAccessException`。
因此改存 **`devtools/work-companion-ui-v0-v1-20261010/`**。這是路徑權限限制，不是 render 失敗；沒有修改 ACL，也沒有移動既有文件。

## 預覽與審核指令

從 repo root 執行。一般模式只開獨立 preview QWidget，關閉視窗即退出，不使用正式 mutex、tray、port 或 controller。

```powershell
cd C:\project\desktop-agent-runtime
.\envs\kuro-llm310\python.exe -B devtools/preview_work_companion_v1.py --page chat
.\envs\kuro-llm310\python.exe -B devtools/preview_work_companion_v1.py --page today
.\envs\kuro-llm310\python.exe -B devtools/preview_work_companion_v1.py --page settings --section assistant
```

可選參數：

- `--page chat|today|settings`。
- `--state idle|loading|partial|error|disabled|empty`；畫面右上也可切換。
- `--section assistant|conversation|perception|tools|appearance|advanced`。
- `--drawer history` 只用於 Chat；`--drawer detail` 只用於 Today。
- `--width 1120 --height 720`；允許 960..1920 × 600..1200 logical pixels。
- `--scale 1|1.25|1.5|2`：只影響本次 preview process。
- `--snapshot <新檔.png>`：強制 offscreen、`QWidget.grab()`、寫一張 PNG 後結束。目錄需已存在；檔案若存在會 exit 2，**不覆寫**。

可重現 snapshot 範例（請使用尚未存在的新檔名）：

```powershell
.\envs\kuro-llm310\python.exe -B devtools/preview_work_companion_v1.py --page chat --snapshot devtools/work-companion-ui-v0-v1-20261010/previews/chat-review.png
.\envs\kuro-llm310\python.exe -B devtools/preview_work_companion_v1.py --page settings --width 1120 --scale 2 --snapshot devtools/work-companion-ui-v0-v1-20261010/previews/settings-review-2x.png
```

互動確認流程：切三個頁面 → 開／選／關 History → Today 選一項並用 Escape 關詳情 → 逐一切六類設定及示範 combo → Chat Shift+Enter 換行、Enter 送出、停止 → 切換右上情境。
不提供檔案匯入、設定儲存、模型連線、真實工具或 service action。

## 已產出圖片

全部為 Qt 6.11.1 offscreen 的實際 widget capture，不是 image mock 或正式桌面程序截圖。前三張均為 1280 × 720。

| 圖片 | 用途 |
| --- | --- |
| [chat.png](previews/chat.png) | 圖 A 模式：180 rail、金色、760 正文／820 composer |
| [settings.png](previews/settings.png) | 圖 B 模式：73 rail、226 subnav、青綠選取 |
| [today.png](previews/today.png) | 三筆合成摘要，其中一筆明示 PARTIAL |
| [settings-1120.png](previews/settings-1120.png) | 1120 × 720，右側文字／選單未互相遮擋 |
| [chat-2x.png](previews/chat-2x.png) | 1280 × 720 logical／2560 × 1440 physical／DPR 2 |
| [chat-history.png](previews/chat-history.png) | 320px 按需 overlay，不固定擠壓正文 |
| [today-detail.png](previews/today-detail.png) | 摘要、排序原因、下一步、synthetic source／時間 |
| [chat-error.png](previews/chat-error.png) | 明確錯誤情境與保留內容 |

8 張均已視覺檢查。chat-history 在假紀錄筆數更新邏輯補齊後重新輸出；只替換本輪自己產生的這張圖。

## 驗證與結果

環境：既有 `envs/kuro-llm310/python.exe`，Python 3.10.12、PySide6-Essentials 6.11.1、Qt 6.11.1；沒有安裝依賴。
採最小 targeted unittest，不執行舊全量 convergence runner、正式 runtime smoke 或任何 provider refresh。

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:KURO_V1_VERIFY_BASELINE = '1'
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_v1_work_companion_view.py -v
```

結果：**18 tests，exit 0，5.354 秒**。涵蓋：

- 1120／1280／1440 × 720，三頁與全部六類設定，無水平溢出。
- Chat／Settings palette 實際 pixel、rail／chrome／正文／composer／subnav 的幾何。
- History 選取、Today detail、Escape 與焦點返回。
- Enter、Shift+Enter、IME preedit、空白輸入、實際 timer 完成、取消及換對話不出現遲到回覆。
- 新回合自動捲到下方，History 筆數同步更新，長 CJK 與無空白 Latin 內容換行。
- 六類 synthetic combos、disabled 能力、還原示範值。
- idle／loading／partial／error／disabled／empty 三頁狀態與恢復。
- preview 互動期間禁止 Python file open、socket connect、process spawn／system call 的動態檢查。
- presentation／fixtures 的 AST import allowlist；正式五個入口檔案沒有 preview import。
- 373 source SHA-256 不變；G7 **35/35** 路徑仍不存在。
- snapshot 子程序 1120 × 720／2× = 2240 × 1440；第二次對同檔輸出 exit 2，原 PNG hash 不變。

測試的 `tempfile.TemporaryDirectory(prefix="kuro-v1-qt-")` 使用 OS TEMP，child 的 TEMP／TMP 只指向該專用目錄；正常結束後自動移除。未使用 worktree TEMP 或 private state。

歷史 WIP hash audit 以 `KURO_V1_VERIFY_BASELINE=1` opt-in，避免把這次 373 檔快照變成未來所有改動必須符合的永久測試。一般跑法仍檢查 import boundary；這項歷史快照稽核會明示 skipped。

5 個新 Python 檔另做 UTF-8 讀回、`ast.parse`／記憶體 `compile`（不產生 pyc），全部通過；本輪 Markdown 相對連結均存在。`git diff --check` exit 0。
新增文字檔使用 `git diff --no-index --check -- NUL <path>`；exit 1 表示新檔與 NUL 不同，stdout 沒有空白錯誤，不能誤當檢查失敗。初次 audit harness 把此 exit 1 誤判為失敗，已校正判定並保留命令 exit。Git 的 LF→CRLF 提示沒有造成檔案寫入。結果見 SourceIntegrityResult。

## 過程中修正的問題

- Composer 初始化採到 QPlainTextEdit 最大高度，y≈565；加入初始行高計算後收斂到 y=609。
- Windows Qt offscreen 起初回傳 0 個系統字型，初次草圖全為方框。host 在自己的 QApplication 登錄已存在的 Windows 微軟正黑體／Segoe UI／Consolas，必要時才用 repo 既有 NaikaiFont；不安裝字型、不改全域設定，view 仍不讀檔。
- 初始 baseline JSON 經 PowerShell／Python 預設輸出編碼時三個中文檔名損壞；以原始 SHA-256 對回 Git 的 UTF-8 路徑，保留原始 hash，不重新放寬基準。
- 長字串使用純文字 QPlainTextEdit 加任意長字換行；測試等待 bounded Qt layout event chain 後驗證 scrollbar，而非只讀第一次 layout。
- 原生 dropdown 補上本機 QPainter chevron；不依賴 offscreen 平台的 arrow 資源。
- 送出／回覆後會追蹤新回合；切換歷史或狀態會取消 pending timer。

## 視覺差異與尚未確認

| 項目 | 本輪實測／差異 |
| --- | --- |
| Chat 正文 | x=350..1110，寬 760；相對描述 x≈346..1106 右移 4px |
| Composer | x=320..1140，寬 820，y=609，高 60；相對 y≈614 上移 5px |
| Chat 頁高 | 統一 720；原圖 A 為 714 |
| Settings | rail=73、chrome=52、subnav x=125/w=226、右內容 x=393..1230 |
| Settings 頁高 | 統一 720；原圖 B 為 723 |
| 字型／icons | 本機 Windows 字型與原生線條 icon；未對原圖原檔做 pixel diff |
| Preview 識別 | 額外 DEMO / PREVIEW、SYNTHETIC、情境選單及不保存說明 |
| History／Today detail | 320px 按需 overlay；不是原圖已確認的精確 drawer 幾何 |
| Today | 圖 A 的延伸設計，尚無使用者原圖基準 |
| Window chrome | capture 是 widget client area；未仿造或測試 Windows 原生 titlebar／正式 tray lifecycle |

使用者還需要審核字級、密度、間距、金色／青綠兩種模式及 Today 延伸設計。Windows 可見視窗、實體 IME、多螢幕 DPI 與實機操作仍未驗收。

## Git 與正式邊界

開工：`main`，HEAD `995c23c7c8d1be62000229d58610d2214f3bb745`；**58 modified、34 deleted、78 untracked，共 170 WIP**。
結束：**58 modified、34 deleted、97 untracked，共 189 WIP**；只新增本輪 allowlist 的 **19 檔**。既有 170 條 status、tracked diff SHA-256、index SHA-256、373 source hashes 全部保持一致，明細見 SourceIntegrityResult。

沒有 commit、push、reset、restore、checkout、clean；沒有修改 launcher_qt.py、qt_app.py、qt_core_pages.py、qt_controller.py、qt_chat_client.py、Core、Conversation 或 Pet。
G7 的 35 個路徑仍不存在；Git 的 34 deleted 與 manifest 的 35 是不同集合語意，不把兩者混算。
沒有存取私人記憶、聊天、信件、模型、market、secrets；沒有實際 API／port／LLM／TTS／Windows 啟動設定／長駐服務操作。

**下一個 gate 是使用者視覺審核。V2 才能在獨立授權下由既有 Qt 唯一 owner 嵌入 view、處理 signals、供應正式資料與可信狀態；本輪沒有任何正式接線或產品 ACCEPTED 宣告。**
