# W1 重驗 checkpoint — 2026-10-10

**Gate W1：BLOCKED。W2–W7：NOT STARTED。**

本輪可執行 Windows 命令，但 task env 缺少 Qt WebEngine 依賴，官方 PyPI 連線仍回 `OS socket 10013`。依 W1 stop rule 停止，沒有啟動正式或 preview Qt、Chrome／Edge、backend、Pet、TTS 或 provider。本文件取代前輪 Bridge 斷線作為本輪阻塞說明，不聲稱已檢查 Bridge runtime。

## 基準與保護範圍

- Repo：`C:\project\desktop-agent-runtime`；branch `main`；HEAD/W0 `af83df273602be3a616d6567855ea71d61a9ace7`；staged 空。
- 初始逐檔 WIP：388 paths（61 modified、34 deleted、293 untracked）。`before.json` 在新增 `w1_preflight.py` 後記錄 389 paths，差額為本輪 task-owned helper。
- 六個 original source 的 working-tree、W0 blob、`995c23c7c8d1be62000229d58610d2214f3bb745` blob、既有 `SourceVerification.json` SHA256 四方一致。
- 原版六個 source、原有 preview helper、master Plan、正式 envs/kuro-llm310、Qt UI／Controller／Conversation／Core／Pet／TTS 不修改；沒有 stage、commit、push、reset、clean、stash、checkout、restore。
- 新 helper 只寫 task-local 新 evidence，不覆寫舊 SourceVerification。舊 `verify_sources.py` 固定 HEAD 為舊來源 commit，不適用 W0 後的本輪 guard，因此沒有執行它。
- frontend-design／ui-ux-pro-max 僅作 fidelity review 準則，沒有產生新 design。未到 rendered page，沒有視覺 reviewer PASS。
- 結束 guard exit 0：HEAD／branch 不變、六份 source 全部一致、index byte SHA 不變、task 外 WIP 變動清單為空。最終 391 paths，新增的三個路徑即兩份 probe 與本 checkpoint。
- 兩份 Python helper 的 AST syntax、報告 UTF-8 讀回、`git diff --check` 均 exit 0；未跑與本次 probe 無關的 production unit/build/runtime tests。

## 指定 checkpoint 寫入阻塞

對 `docs/agent-runs/kuro-original-web-cutover-20261010/W1Checkpoint.md` 的 apply_patch 寫入失敗；其後 `require_escalated` 精確寫入重驗仍回「拒絕存取路徑」，exit 1。檔案不是 ReadOnly attribute；本輪不更改 ACL，不刪除／替換原檔。原 checkpoint 保留前輪內容，本輪完整結果保存在本文件，故「更新指定原 checkpoint」這項交付也為 BLOCKED。這是執行時檔案拒絕，沒有收到自動審批拒絕。

## 實際執行結果

| 檢查 | 結果 | exit／狀態 |
| --- | --- | --- |
| W1 基準及六份 source guard | main/W0；staged 空；SHA 全一致 | 0 / PASS |
| task `.venv` | Python 3.13.9；PySide6、Pillow、Playwright 未安裝 | 讀取完成 |
| uv 版本 | 0.11.24 | 0 |
| task cache offline wheel install | PySide6 6.11.1 不在 cache | 1 / BLOCKED |
| 官方 PyPI wheel install | tcp connect error / OS socket 10013 | 2 / BLOCKED |
| 同命令 require_escalated 重驗 | 同樣 OS socket 10013 | 2 / BLOCKED |
| 真正 import QWebEngineView | ModuleNotFoundError: No module named 'PySide6' | BLOCKED |
| 真正 import QWebChannel | 同上 | BLOCKED |
| ephemeral loopback | 127.0.0.1:0 bind/connect/accept/synthetic round trip，隨即關閉 socket | PASS |
| task Python 官方 PyPI HTTPS | urllib 無 proxy/credential，仍 WinError 10013 | BLOCKED |
| environment probe 整體 | 完整落盤各子檢查 | 2 / BLOCKED |

全域 uv cache 列目錄遭 `Access is denied`，不可宣稱其中沒有 wheels；task cache 則由 offline resolver 確認缺少所需 PySide6。未改 cache ACL，未拼接正式 env 的部分套件。安裝設定僅 task cache／task .venv、official PyPI、binary wheels、20 秒 HTTP timeout、0 retry。

**已確認的阻塞鏈**：task env 缺依賴 → task cache 無所需 package → uv 與 Python 的官方 PyPI 外連都遭 10013 → 無法開始 Qt render。loopback 可用，故不是所有 socket 均失效。具體攔截 owner（執行環境限制、Windows 網路政策或其他安全產品）仍未確認；提權命令同樣失敗，不能聲稱根因已排除，也不能歸咎 frontend。沒有改防火牆、registry、ACL 或安全設定。

## Gate 證據狀態

| 表面 | 本輪狀態 |
| --- | --- |
| Git original source integrity | PASS |
| Qt 模組 import | BLOCKED |
| 安全 profile／sandbox／resource、navigation、download 防護實際執行 | UNVERIFIED，依賴阻塞 |
| Qt load、render、bounded synthetic WebChannel | UNVERIFIED，依賴阻塞 |
| Chat、Settings、History、Today/Schedule screenshot pair | BLOCKED，沒有本輪 baseline 或 Qt PNG |
| 1280×720／1380×860 × 100%／125%／200% | 全部未執行 |
| DOM geometry、computed CSS tokens、font、overflow | UNVERIFIED，沒有 rendered-page 量測 |
| Pixel MAE／RMS／changed fraction | UNVERIFIED / null；不得填 0 |
| History drawer、六 Settings groups、composer、焦點／鍵盤、Today/Schedule 互動 | UNVERIFIED |
| Qt 截圖人工 reviewer | UNVERIFIED，無圖可審 |
| 本輪 Chrome／Edge GPU | UNVERIFIED，未啟動瀏覽器；舊 2147483651 僅是歷史證據 |
| **W1** | **BLOCKED** |
| W2–W7 | NOT STARTED |

沒有新增或使用 `QTWEBENGINE_DISABLE_SANDBOX`、`--no-sandbox`、`--disable-gpu`；沒有以 import-only、HTTP 200 或使用者已接受的普通瀏覽器 preview 代替 Qt render。

原有 `capture_parity.py` 的 coverage 不足以單独接受 W1：只跑 chat/settings/today、Qt 指定 offscreen、沒有獨立 History screenshot、Qt 互動或兩端 locale/timezone 一致性 assertion。這是 source review 的測試缺口，未判定視覺 defect。本輪依賴 blocked 後不擴寫無法實測的 capture helper；環境恢復後仍須先局部修補與回歸，再執行完整矩陣及 reviewer 審查。

## 證據

本輪檔案位於 [.runtime/w1-20261010-retry/](.runtime/w1-20261010-retry/)，依原本 gitignore 保持本機 evidence：

- `before.json`／`after.json`：四方 source SHA、index SHA、完整 status、task 外既有 WIP digest／缺檔狀態與結束比對。
- `environment.json`：interpreter、兩個 import、loopback、官方 PyPI 的實測結果。
- `install-offline.log`、`install-pypi.log`、`install-pypi-approved-network.log`：實際安裝輸出。
- `GateResult.json`：各 exit、整體狀態、未執行矩陣與 evidence digest。
- `checkpoint-write.log`：指定既有 checkpoint 精確寫入重驗結果；不改 ACL。

## 重現

每次選用新的 run 目錄以保留舊證據。安裝失敗即停止，不接著 render：

```powershell
Set-Location C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010
$w1Run = '.runtime\w1-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& .\.venv\Scripts\python.exe -B w1_preflight.py "$w1Run\before.json"
if ($LASTEXITCODE -ne 0) { throw 'W1 integrity guard failed' }
& .\.venv\Scripts\python.exe -B w1_environment_probe.py --output "$w1Run\environment.json"
# 缺依賴時 probe 預期 exit 2；個別 loopback/PyPI 結果仍保留。
uv pip install --offline --cache-dir .uv-cache --python .venv\Scripts\python.exe --only-binary :all: --requirements requirements-preview.txt
# 僅 cache miss 時，可做一次已授權的官方 PyPI 安裝：
$env:UV_HTTP_TIMEOUT = '20'
$env:UV_HTTP_RETRIES = '0'
uv pip install --cache-dir .uv-cache --python .venv\Scripts\python.exe --only-binary :all: --index-url https://pypi.org/simple --requirements requirements-preview.txt
if ($LASTEXITCODE -ne 0) { throw 'W1 BLOCKED: preserve install error; do not start render' }
& .\.venv\Scripts\python.exe -B w1_environment_probe.py --output "$w1Run\environment-after-install.json"
if ($LASTEXITCODE -ne 0) { throw 'W1 BLOCKED: imports/environment did not pass' }
```

安裝來源核對：[Qt 官方安裝說明](https://www.qt.io/product/qt6/qml-book/ch19-python-installing)、[Qt 官方 WebEngine 文件](https://doc.qt.io/qtforpython-6/QtWebEngine.html)。官方文件不構成本機安裝或渲染成功的證據。
