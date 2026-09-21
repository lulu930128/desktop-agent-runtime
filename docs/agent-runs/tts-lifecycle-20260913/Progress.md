# 修復進度

## 狀態

原始碼修復與下列自動驗證完成；正式 Launcher/對話程序採用及人工桌面驗收待完成。2026-09-13。

## 已確認

- 使用者回報無聲；當日對話 log 記錄合成開始後約 30 秒出現 ReadTimeout。
- 修復前，已載入 kuro 的短句直接合成成功，0.70 秒產生 1.82 秒 WAV；音訊 payload 與嘴型音量資料可建立。
- 使用者已授權修改；桌寵視窗關閉後 Launcher、對話 runtime 與中央語音仍在執行。
- Consumer、Launcher readiness、既有 runtime/文字降級共 29 項 targeted tests 通過；syntax、renderer typecheck/build 通過。

## 驗證證據

- `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p 'test_central_voice*.py' -v`：21 項。
- `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p 'test_runtime_capabilities.py' -v`：8 項，包含文字降級及不等待不存在的音訊播放。
- 修改的三個 Python source 執行 `py_compile`；`npm run check:renderer`、`npm run build:renderer` 通過。首次 build 遇 sandbox `spawn EPERM`，核准後以相同命令重跑成功。
- 有限真實合成：kuro 0.86 秒、yuki 3.70 秒、切回 kuro 3.48 秒；每次有效且非靜音 WAV、payload、readiness 與 active voice 一致。中央 service PID 未變。
- 隔離 HTTP fixture 延遲 31.5 秒才回傳：正式 client 於 31.516 秒接收有效 WAV，確認超過舊 30 秒門檻後仍可完成。這不是中央程序 cold boot 的耗時測量。
- 隔離 Electron：正式 BackendClient/adapter 經真實 WebSocket 接收本次中央 WAV；HTML Audio `playing=1`、`ended=1`、`errors=0`，33 次非零嘴型輸入，服務端收到 `frontend-playback-complete`。model renderer 僅記錄嘴型輸入，未驗證畫面中模型嘴部。
- 真實 WAV、結果與隔離播放腳本保存在 ignored `launcher_logs/tts-fixed-20260913-212537/`，未納入 Git。

## 套用與剩餘驗收

- 修改前啟動的 Launcher/對話程序仍存活。需完整重新啟動 Kuro 以載入新 Python 程式及 renderer；僅重新顯示桌寵不能證明已套用。
- 完整桌寵的實際對話、角色 hot switch、可見嘴型及人工聽感仍待驗收；本次未發送 LLM/MCP 測試對話或修改使用者 profile。
- 中央服務未重啟，故未重現程序完全冷啟動；已用延遲 HTTP 驗證舊 timeout 邊界，並用真實中央引擎驗證語音模型切換。

## 2026-09-21 整合提交複驗

- 本批 TTS source、測試與文件獨立提交，與架構文件收斂分開。
- 重新執行 `test_central_voice*.py`：21 項通過；`test_runtime_capabilities.py`：8 項通過，無 skipped。
- 三個修改的 Python source 與兩個測試檔 `py_compile` 通過；renderer `check:renderer` 與 `build:renderer` 通過。
- Build 首次受 sandbox `spawn EPERM` 阻擋；相同命令在核准的執行範圍重跑成功。保留既有 Live2D script 缺少 `type=module` 警告。
- 本日未啟停正式程序、未做真實合成或桌面播放驗收；上方 2026-09-13 的 live 結果是歷史證據，不能視為本日 runtime 已載入的證明。
