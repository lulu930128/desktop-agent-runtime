# 架構文件索引

本頁是導航，不是即時 health page，也不複製會快速過期的工具 inventory。

- [現況架構](RuntimeArchitecture.md)：元件、設定、資料流、local control 與已知架構債。
- [責任地圖](OwnershipMap.md)：能力 owner、truth、consumer 與 Qt／Pet 邊界。
- [資料流](DataLineage.md)：對話、工具、Schedule、Core Today／integrations、記憶與語音。
- [Runtime services](RuntimeServices.md)：process identity、port、啟停與 shared-service 邊界。
- [Core persistence](CorePersistence.md)：單庫 schema v3、migration owner、備份／還原與研究限制。
- [研究邊界](ResearchBoundary.md)：worktree／state／IPC 隔離、security baseline 與 experiment evidence。
- [中央語音服務](../central-voice-runtime.md)：共用 ownership、mapping 與驗收限制。
- [Product Vision](../product/ProductVision.md)：長期產品定位。
- [Operating Model](../product/OperatingModel.md)：目標分層，不代表已完成遷移。
- [Quality Bar](../product/QualityBar.md)：品質與驗證門檻。
- [Roadmap](../product/Roadmap.md)：逐項實作與驗收方向。

Source 的 config、policy、schema 與測試提供可執行 contract；正式 runtime 採用仍需核對啟動 root、PID、listener、載入 source 與使用者表面。

`kuro_core/` 是 Schedule／Work／Attention／Today／bounded integrations 的 owner；Qt 是唯一主 UI、tray 與通知 delivery owner；Electron 僅 Pet presentation。舊 Electron business modules 外部 production consumer 已為 0，但 10 個 source 檔受 OS 權限阻擋尚未實體刪除。G8 source regression 通過，隔離 Electron renderer smoke 失敗，正式桌面驗收仍 UNVERIFIED；release verdict 為 NOT ACCEPTED，見 [G8Checkpoint](../agent-runs/qt-ui-convergence-20261007/G8Checkpoint.md)。語音可連線、實際推論、播放與聽感仍須分開驗證。

`docs/agent-runs/` 保存歷史任務與日期性證據，不取代持續維護的架構文件。本次保留既有 Git 追蹤項目，不移除或改寫歷史；一般讀者無須先閱讀 agent 任務紀錄。新的長期結論應回寫 guides／architecture。

返回[文件入口](../index.md)。
