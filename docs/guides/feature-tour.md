# 功能導覽

Kuro 將工作資訊與角色互動整合在桌面。以下為現有入口，來源內容仍取決於本機設定、權限與服務可用性。

| 需求 | 入口 | 限制 |
| --- | --- | --- |
| 開始或回到主畫面 | 工作面板 | VBS 啟動；關閉視窗通常只隱藏到 tray。 |
| 對話、歷史、附件 | 對話／Reader | 長內容保留文字，語音是另一條處理流程。 |
| 掃描當日摘要 | Today／行事曆／Briefing | Connected 不代表 current，缺漏與 stale 要一起看。 |
| 切換角色與情境 | 設定 | 人格與聲音不能改變外部資料或權限。 |
| 常駐短互動 | Live2D 桌寵 | 表情、動作與音訊呈現，不是市場分析或工作資料庫。 |
| 管理記憶 | 工作面板／Launcher | 長期記憶與 snapshot／工具結果分開，修改有確認邊界。 |
| 查看市場結果 | OMI 工具 | OMI 擁有資料與判斷；Kuro 保留 stale、partial、missing。 |
| 排查啟動 | Qt 控制台 | 背景 orchestration 與診斷入口。 |

## 既有實際畫面

![工作面板設定頁](../assets/readme/kuro-v1-work-panel-settings.jpg)

![Live2D 桌寵](../assets/readme/kuro-v1-desktop-pet.jpg)

以上為 2026-08-24 runtime 截圖，使用設定頁與角色裁圖避開私人內容，不是本次重新驗證的 1.1.0 畫面。

## 現況與目標

統一 Task Store、Attention Queue、quiet hours、完整 Action／Policy／Audit 與 scoped automation 依 [Roadmap](../product/Roadmap.md)逐項實作驗收。Shadow Core 不代表 Today 已完成切換。

一般工具的 `confirm` 模式目前阻擋執行，不能與工作面板特定操作的原生確認混為一談。中央語音仍有人工聽感待驗收，見[語音文件](../central-voice-runtime.md)。

返回[文件入口](../index.md)。
