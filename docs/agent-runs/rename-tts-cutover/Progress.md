# 進度

## 已完成（2026-09-11）

- 中央 Voice Runtime v1 已部署，使用 18890；18790 是 japanese-study-mcp，未更動。
- Kuro、Yuki、再 Kuro 真實推論成功；Open-LLM-VTuber factory/adapter、JLPT 男女聲 consumer 實際產音成功。
- Kuro central 新測試 5、launcher 5、pet lifecycle 6；中央 5；JLPT 32 項測試通過。
- syntax check 與 git diff --check 通過。
- listening_audio 隔離真實 MCP smoke 通過：男聲 303404、女聲 241964、混合 519724 bytes；resource 讀取與 cache reuse 成功。
- 首次 MCP smoke 揭露原生 OpenAPI readiness 假設，已修正中央分支並重跑成功。
- JLPT 正式 server 已重新載入；/api/health 回 central、18890、running=true，model/reference 路徑不再由 consumer 持有。
- Kuro 正式設定已改 central；目前桌寵未啟動，實際桌面/字幕/聽感留給使用者驗收。

## 2026-09-11 改名阻塞紀錄（歷史）

- Move-Item 被 Windows 拒絕：目錄正由其他程序使用。未移動任何資料，新目錄尚不存在，捷徑保持可用舊路徑。
- Handle 確認 Codex PID 43652 持有 C:\project\kuro\.codex 的 File handle；未強制關閉 Codex 或 handle。
- 已準備 C:\project\Complete-DesktopAgent-Rename.ps1，檢查模式已驗證；關閉此 Codex 工作區後由外部 PowerShell 執行。
- 腳本僅移動精確目錄、更新既有捷徑/active docs，保留 Git HEAD，執行新路徑 Python/config、central regression、VBS 與 diff 檢查；不刪除 legacy。
- 新路徑 runtime 驗證仍待實際改名，不能以目前路徑測試取代。

## 證據與後續

- 本機音訊與量測：launcher_logs/tts-cutover/evidence.json。
- MCP 證據：C:\GPT_MCPtool\listening_audio\.tmp\live-2026-09-11T09-20-47-990Z\evidence.json。
- 中央/JLPT 是外部工作區，變更在當地檔案；本 repo 未收錄模型或外部 source 副本。
- 人工聽感 pending、模型包 staged、legacy 保留。未 commit/push。

## 2026-09-12 版本整理

- checkout 已位於 C:\project\desktop-agent-runtime；新路徑 Python regression 共 38 項通過，變更 Python 語法檢查通過。這不代表桌面捷徑與人工互動驗收。
- 中央 inventory/result.json 確認 10,347 個相同副本、1 個另存檔案，source_removed=true；舊目錄已移除，覆蓋前述保留 legacy 的歷史狀態。
- 使用者授權整理、commit、push，產品版本升為 1.1.0；子元件版本不變。
- 人工聽感與桌面互動仍待驗收；本輪未啟停中央服務。
