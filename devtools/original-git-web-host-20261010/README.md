# Git 原始 Work Companion 隔離還原 checkpoint

本目錄只供 synthetic preview／審核，**不是正式 UI 入口**。正式 `launcher_qt.py`、Qt window/tray、Controller、Conversation、Core、Pet 與 shared voice 沒有接入這個目錄。

本輪總狀態：**BLOCKED；產品 NOT ACCEPTED**。六個原始 Git 檔位元一致、TypeScript／Vite build 和 targeted regression 通過；WebEngine 依賴及 Chromium OS 權限阻塞，沒有可採信截圖或 DOM／像素比對。詳見 [Checkpoint.md](Checkpoint.md)。

本輪對原 Reviewer 計畫的追加寫入遭 OS 權限拒絕；完整結果另存 [PlanAddendum.md](PlanAddendum.md)。最終核對時原計畫已出現另一份並行 checkpoint，已記錄隔離路徑與阻塞；本輪保留其內容，不再重複追加或修改 ACL。兩個 SHA 與說明見 `SourceVerification.json`／`Checkpoint.md`。

## 原始碼與最小差異

- `frontend/src/work-panel/{main.ts,styles.css,model.ts,types.ts,schedule.ts}` 以及 `frontend/work-panel.html` 都是 `995c23c7c8d1be62000229d58610d2214f3bb745` 的原始位元。
- `frontend/vite.config.mjs` 僅在 build 時將原始 HTML script entry 改成 bootstrap，並加入限制外部載入的 CSP。保存的原始 HTML 不改動。原始 DOM/CSS、78px rail、50px chrome 與青綠色 tokens 沒有重畫。
- `frontend/src/baseline.ts` 安裝 synthetic bridge 後 dynamic import 原始 main；`qt.ts` 等待 QWebChannel ready 後才 import，失败不退回 browser bridge。
- `synthetic.json` 是唯一匿名 fixture。讀取成功只代表 fixture 可用；正式連線為 false。寫入、發送、profile、Memory、Mail、感知和 Schedule mutation 都回傳 unavailable。附件 picker/drop 被 preview adapter 阻擋。原始 source 中提到 Electron/native confirmation 的歷史文案原樣保留，**在本 preview 不代表功能已接通**。
- `qt_preview_host.py` 是未經 WebEngine runtime 驗證的隔離候選 host。只有 allowlisted synthetic reads；request id、context/revision、payload 有限制。無 Controller、Core、DB、WS、provider 或 tray。具 off-the-record profile、資源範圍限制、拒絕導航／新視窗／下載／權限請求。它不能證明 production bridge 的 confirmation/identity fences 已整合。
- 原本提議的 `kuro_launcher/work_companion_web` 已移出 production tree；G8 原測試未修改，也沒有新增 production import。

## 本機可重現命令

原有 Vite 8.0.13／TypeScript 6.0.3 由 repo 的 `pet-electron/node_modules` 使用，未安裝 npm 套件或改 lockfile。

```powershell
Set-Location C:\project\desktop-agent-runtime
python -B devtools/original-git-web-host-20261010/verify_sources.py
python -B devtools/original-git-web-host-20261010/validate.py
Set-Location devtools/original-git-web-host-20261010/frontend
npm run check
npm run build
npm run preview
# 手動開啟 http://127.0.0.1:4179/work-panel.html?view=chat
# 或 ?view=settings / ?view=today；完成後 Ctrl+C 停止本 preview。
```

`validate.py` 只用 synthetic tests／暫存 DB／ephemeral loopback ports；阻擋正式 ports 及外網。Pet renderer build 直接用原 Vite config、輸出到 task `.runtime`，不呼叫會複製 Live2D assets 的 prepare script，不覆蓋正式 `renderer-dist`。本輪 preview server 已結束。

## 有權限 Windows 環境安全接力

僅在本機正常權限可下載套件及啟動 Chromium 時執行。每一步失敗即停止；不要加 `--no-sandbox`、`--disable-gpu`、改安全設定或重啟正式 Kuro。下面安裝目的地只有 task `.venv`，不使用正式 `envs/kuro-llm310`。

```powershell
Set-Location C:\project\desktop-agent-runtime
$previewRoot = Join-Path $PWD 'devtools\original-git-web-host-20261010'
$previewPython = Join-Path $previewRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $previewPython)) {
    python -m venv (Join-Path $previewRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Isolated venv failed' }
}
$env:UV_CACHE_DIR = Join-Path $previewRoot '.uv-cache'
uv pip install --python $previewPython -r (Join-Path $previewRoot 'requirements-preview.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency Gate BLOCKED' }
& $previewPython -B -c "from PySide6.QtWebChannel import QWebChannel; from PySide6.QtWebEngineWidgets import QWebEngineView; print('real imports PASS')"
if ($LASTEXITCODE -ne 0) { throw 'Import Gate BLOCKED' }
Push-Location (Join-Path $previewRoot 'frontend')
try {
    npm run check
    if ($LASTEXITCODE -ne 0) { throw 'TypeScript failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Vite build failed' }
} finally { Pop-Location }
& $previewPython -B (Join-Path $previewRoot 'capture_parity.py') --channel chrome --scale 1
if ($LASTEXITCODE -ne 0) { throw 'Parity BLOCKED or FAIL; inspect evidence, do not cut over' }
```

接力 capture 使用已安裝的 Chrome executable、自有暫存 profile、Chromium sandbox 啟用、Qt offscreen。不安裝或啟動 Electron。比對 1280×720、1380×860 的 Chat、Settings、Today/Schedule；各自保存 PNG、DPI/devicePixelRatio、DOM rect/font、CSS variables、影像尺寸與差異圖、MAE/RMS／changed pixel fraction。裁切邊界固定為 Web viewport，不含 Windows 外框。`--scale 1.25`／`--scale 2` 可另做 DPI 檢查；相同輸出目錄存在時拒絕覆寫證據。

這些 capture／interaction helper 本輪只有 syntax check，**尚未跑通**。capture 的 host `PASS` 只指 import/load/render/WebChannel，不代表視覺或 release PASS。geometry/token 不同會停止；像素差異沒有虛構門檻，需 Reviewer 檢查。baseline History 開關／搜尋、Settings 六類、composer draft／Tab 僅為接力腳本中的 checks，**本輪未執行**。Qt 操作、IME、a11y、responsive breakpoints 與真實 Windows 桌面仍須另行驗收。

## 後續 adoption 前置條件

1. WebEngine 真正 import/render、原版／Qt 同狀態圖、幾何與互動 Gates 通過。
2. 由使用者提供的舊 Settings／Chat 圖作人工目標確認；本輪未取得兩張原圖檔。
3. 再設計 production adapter：Qt native confirmation、Conversation context/revision、Core Today/Schedule read contract，保留所有 owner/fences。不得將 synthetic fixture 或舊 Electron Briefing/IPC 復活成正式資料來源。
4. 正式 source adoption 與 Windows runtime 驗收分開；本 checkpoint 不修改正式入口、不重啟程序、不 commit/push。

Qt API 設計參考：[WebChannel JavaScript](https://doc.qt.io/qtforpython-6/overviews/qtwebchannel-javascript.html)、[off-the-record profile](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineProfile.html)、[request interceptor](https://doc.qt.io/qt-6.8/qwebengineurlrequestinterceptor.html)。這些文件不代替本機 runtime 證據。
