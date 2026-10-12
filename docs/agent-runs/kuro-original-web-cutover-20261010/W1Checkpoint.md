# W1 Qt WebEngine 同源渲染驗收 — preflight checkpoint

> **最新驗證（2026-10-10 15:12 Asia/Taipei）：W1 Smoke 已 PASS，Parity 仍 FAIL。** 正常 Windows 使用者的隔離 Qt 6.11.1 實測 Chat／Settings 渲染 PASS，原版 16 CSS tokens、1280×720 DPR 1、Qt WebChannel 兩頁各 11 requests。原版 Edge vs Qt 比對 Chat 與 Settings DOM 幾何完全一致，changed pixels 分別 **1.7490%／2.1088%**；Today tokens 相同，但 `.local-schedule.y` **493.921875 → 496.921875（Qt +3px）**，changed pixels **5.0845%**，因此嚴格驗證失敗。
>
> 舊的 [ParityResult.json](../../../devtools/original-git-web-host-20261010/.runtime/parity-msedge-1-20261010T071240461324Z/ParityResult.json) 與所有 PNG 保留不覆寫。獨立核對像素及視覺診斷見 [W1TodayParityCheckpoint.md](../../../devtools/original-git-web-host-20261010/W1TodayParityCheckpoint.md)：Today 超過 48% 不同像素集中在排程區；對 Qt 畫面僅做取樣 +3px 分析，標題/priority 誤差大幅下降，但日期 input 原生寬度差異仍在，未確認唯一根因。Codex 僅在隔離 helper 增加明示 `--collect-geometry-drift`，繼續採證時 **FAIL 不得變成 PASS**；原版 6 source/Qt host 沒有改動。獨立 History 截圖、Qt 鍵盤/IME、navigation/download 防護與其他解析度/DPI 仍待驗，**W2–W7 不得開始**。
>
> 以下 PyPI／Codex ACL／Bridge 斷線內容僅為較早期歷史事件，不再代表當前阻塞。


日期：2026-10-10（Asia/Taipei）
判定：**BLOCKED_INFRASTRUCTURE**；W1 尚未獲得 Qt WebEngine import/render、瀏覽器↔Qt 截圖或像素比較證據。不得聲稱 W1 PASS 或開始正式 W2 cutover。

## 基準及 source
- 已提交原始前端與 W0–W7 計畫的本地 Git baseline：`af83df273602be3a616d6567855ea71d61a9ace7`。
- 源 Git 版：`995c23c7c8d1be62000229d58610d2214f3bb745`，六個 HTML/TS/CSS 原始碼在 `devtools/original-git-web-host-20261010/frontend`，由前輪 SourceVerification 和驗證工具記錄。
- 本輪唯讀 Git status 觀察：`main`、387 未提交路徑（61 M、34 D、292 ??），保留不動。
- 正式 Qt `launcher_qt.py`、Conversation、Core、Pet、TTS 不得為隔離測試而停止/重啟。正式 Python venv 不得更動。

## 本輪新阻塞（不是前端 defect）
- Codex Bridge 工具調用回 `INVALID_ARGUMENT: McpServerError: Session terminated`，送出 W1 工作委派時未取得 job ID/acceptance；不可宣稱 Codex 已接單，也不可未查明就重複送新 job。
- 使用 Project_Workspace 的 Windows TCP listener 唯讀診斷：`127.0.0.1:18828`（Bridge server）與 `127.0.0.1:18829`（tunnel health）都為 `no_listener`。
- Project_Workspace repo 讀取/狀態診斷仍正常。現階段沒有經授權的 Windows 命令執行連線可自動安裝 task venv 或執行 Qt screenshot，因此 W1 仍 BLOCKED。

## 安全恢復動作

使用者可從自己的 PowerShell 執行（先 Status，再 EnsureRunning；不修改 Kuro repo，也不啟動 Kuro 程序）：

```powershell
cd C:\GPT_MCPtool\codex_bridge
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\runtime-control.ps1 -Action Status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\runtime-control.ps1 -Action EnsureRunning
```

兩個命令來自 `C:\GPT_MCPtool\codex_bridge\scripts\runtime-control.ps1` 實際 `ValidateSet` / defaults；若 EnsureRunning 回傳失敗，將不含 token/secret 的 `errorCode` / `message` 供 Reviewer 定位。若 server 已復原但本 ChatGPT 工具仍顯示 Session terminated，重新整理工具連線／ChatGPT 頁面後再確認；不重複 dispatch 未有接受回條的工作。

## W1 後續必做（尚未完成）

1. Repo Git W0 baseline/dirty diff guard + 原版 SHA verified。
2. 隔離 `devtools/original-git-web-host-20261010/.venv` 真實 import `PySide6.QtWebChannel` / `QtWebEngineWidgets`；前輪還有 OS socket 10013 blocker，需重新驗證，不修改正式 venv。
3. Qt WebEngine 在不關 sandbox、不關 GPU 防護的安全條件下真實載入本地 Git renderer + synthetic read-only bridge。
4. Chromium baseline ↔ Qt host 在 Chat、Settings、History、Today/Schedule 相同 synthetic fixture、1280×720 與 1380×860、100/125/200% DPI 比較；儲存 PNG、CSS tokens、DOM geometry、font、pixel MAE/RMS 和互動結果。
5. 只有 W1 圖像及安全／操作 Gate PASS，經獨立 Reviewer 複查，才開始 W2。不能由「使用者看過普通瀏覽器原版」推定 Qt 版已過關。

本 checkpoint 是前置觀察，無 Git commit/push，亦未嘗試修改或重啟正式 Kuro runtime。
