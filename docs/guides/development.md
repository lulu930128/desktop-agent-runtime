# 開發與驗證

命令從 repo root 執行，依風險選最接近的檢查。先確認 owner，避免把 domain 邏輯放進 renderer 或角色 prompt。

## 開發與驗證

只改文件時：

```powershell
git diff --check
```

Launcher / Python syntax：

```powershell
.\envs\kuro-llm310\python.exe -m py_compile `
  .\launcher_qt.py `
  .\kuro_launcher\qt_app.py `
  .\kuro_launcher\qt_controller.py `
  .\kuro_launcher\qt_chat_client.py
```

Electron main process：

```powershell
node --check .\pet-electron\src\main.js
node --check .\pet-electron\src\state.js
node --check .\pet-electron\src\main-process\control-server.js
node --check .\pet-electron\src\main-process\briefing-store.js
node --check .\pet-electron\src\briefing-preload.js
```

Electron renderer：

```powershell
Set-Location .\pet-electron
npm run check:renderer
npm run build:renderer
```

Runtime 或 UI 變更不能只看 build；至少要確認實際 listener、`/status`、`/briefing`，
並在有視覺風險時檢查真正顯示中的 Qt、Live2D、Reader 或 Briefing 畫面。

## 既有測試入口

| 範圍 | 測試 |
| --- | --- |
| Launcher／Pet lifecycle | `tests/test_launcher_entrypoint.py`、`tests/test_pet_lifecycle.py` |
| 工作面板 API | `tests/test_work_panel_api.py` |
| 中央語音 consumer | `tests/test_central_voice.py` |
| Shadow Core | `tests/test_kuro_core_contracts.py`、`tests/test_kuro_core_store.py`、`tests/test_kuro_core_shadow_probe.py` |
| 桌寵幾何 | `tests/pet_*.test.cjs`、`tests/pet_*.test.mjs` |
| OMI consumer／policy | `Open-LLM-VTuber/tests/test_market_preflight.py`、`Open-LLM-VTuber/tests/test_tool_policy_omi.py` |

例如工作面板 API：

```powershell
.\envs\kuro-llm310\python.exe -m unittest discover -s tests -p test_work_panel_api.py
```

這些是可用入口，不是本次執行的測試報告。Root 目前沒有 `.github/workflows/`；子專案上游設定不代表整套 Kuro CI 已通過。

## 交付原則

- `VERSION` 是 Kuro 產品版本；Electron 與上游 runtime package 版本各有用途。
- 上游／vendor 升級須記錄來源、Kuro patches 與回歸範圍，目前沒有已驗證的自動同步流程。
- 不提交 secrets、生成設定、history、memory、logs、模型、私人音訊或 dependency/build output。
- Source／測試、runtime 採用、provider 回應、桌面體驗與 Git 發布分開驗收。
- 公開截圖先移除私人內容。頂層授權待釐清，不能由子目錄 license 推定整套產品或模型可再散布。

詳見[現況架構](../architecture/RuntimeArchitecture.md)與[品質門檻](../product/QualityBar.md)。
