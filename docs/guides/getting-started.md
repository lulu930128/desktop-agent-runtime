# 開始使用 Kuro

Kuro 目前是 Windows 個人本機 runtime，沒有經本文件驗證的完整新機安裝流程或可攜安裝包。Clone 不包含 Python 環境、模型、私人語音、憑證或中央服務。

以下命令預設從 checkout 根目錄執行，範例路徑請換成實際位置。先確認已有工具與設定，避免覆蓋既有環境。

## 啟動方式

這個 repo 目前假設本機 runtime 已準備完成，還不是一鍵安裝的公開產品。

主要需求：

- Windows 與 PowerShell。
- `envs/kuro-llm310`：Launcher、Bridge 與 Open-LLM-VTuber 使用的 Python 3.10 環境。
- `envs/kuro-tts310`：歷史 legacy 環境，中央模式不使用。
- `pet-electron/node_modules` 與已安裝的 Electron/Vite dependencies。
- 對應角色的 Live2D model，以及已啟動且提供對應 voice ID 的中央 Voice Runtime。

建立本機 env 檔：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

安裝 Qt launcher dependency（環境已完成時可跳過）：

```powershell
.\envs\kuro-llm310\python.exe -m pip install -r .\requirements-qt.txt
```

安裝 Electron dependency：

```powershell
Set-Location .\pet-electron
npm ci
npm run build:renderer
Set-Location ..
```

從 repo root 啟動：

```powershell
Set-Location "C:\project\desktop-agent-runtime"
.\envs\kuro-llm310\python.exe .\launcher_qt.py
```

也可以從 Explorer 執行：

```text
桌寵啟動器.vbs
```

`桌寵啟動器.vbs` 會以工作面板模式啟動 Qt orchestrator。Qt 控制台在背景管理 runtime，
不建立第二個可見面板；Electron 工作面板會先顯示，不需要等待完整 `startup_profile` ready。
再次執行同一支 VBS 時，secondary process 只向既有 Launcher 送出 activation intent；由既有 Launcher
驗證、復用或重建 Pet shell，再把工作面板帶回前景。關閉工作面板只會隱藏視窗並保留 tray runtime。
若啟動失敗，控制台才會例外恢復到前景顯示診斷資訊。

需要直接進入完整 Qt 控制台時，仍可執行上方的 `launcher_qt.py` 命令。現在
`startup_profile.auto_start` 為 `true`，所以控制台會依設定嘗試啟動預設 profile。

## 第一次準備環境

- `requirements-qt.txt` 只涵蓋 Qt／WebSocket，不是整套 runtime 依賴。對話依賴見 `Open-LLM-VTuber/pyproject.toml` 與該目錄 lockfile；Bridge 與角色資產也要各自準備。上述局部安裝命令不代表可完整重建新機。
- 檢查 `kuro_launcher.settings.yaml` 的 paths、ports、startup profile 與 voice mapping；不要直接沿用其他機器路徑。
- `.env`／`.env.local` 保存本機 provider 設定，不放入 Git、截圖或公開 issue。
- 依[中央語音服務](../central-voice-runtime.md)準備獨立服務；consumer 不停止共用引擎。舊引擎已移除，不能只改回 legacy mode 就回復。
- VBS 會檢查 `pet-electron/renderer-dist/work-panel.html`，所以安裝 dependencies 後還需要 build。

## 啟動確認

先確認工作面板，再觀察各服務 readiness。面板可見不代表 LLM、語音推論或播放成功；對話、文字、音訊與 lip sync 需分別確認。

既有 Pet shell 運行時可唯讀檢查（port 以 settings 為準）：

```powershell
Invoke-RestMethod http://127.0.0.1:23567/status
```

結合 service identity、PID 與畫面判讀，不只看 HTTP 200。遇到問題見[故障排查](troubleshooting.md)，返回[文件入口](../index.md)。
