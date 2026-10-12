# Git Work Companion 功能移植

以 Git 原始 DOM、CSS、function、event 恢復唯一 Qt 主 UI 的可見行為，優先 History 與 Chat。這不是 synthetic preview 交付。

- Source of Truth：`995c23c7c8d1be62000229d58610d2214f3bb745`（HEAD）及 `3baf05728921607d71306c98d43eaad155b0dbc1`。
- 不恢复 G7 35 檔、不新增 service／UI owner／provider／cache；Qt-primary、Conversation、Core、Pet 邊界維持。
- 不操作正式 runtime、私人歷史／記憶／DB／secrets、Mic／camera、Mail 或外部 provider。
- 不 checkout／restore／reset／clean／commit／push，不改 ACL。使用 fixture、mock 或 repo 內可拋棄 temp。
- 所有成功狀態需由 owner 回應；不支援的控制禁用並顯示原因。source-ready 不代表實機驗收。
- `docs/agent-runs` 寫入遭 Windows WinError 5 拒絕（含一次提升權限重試）；任務證據改存本目錄，source 本身可寫。

WIP 起點：main、58 modified、34 deleted、97 untracked。`Baseline.json` 是此次開始時的逐檔 SHA-256；`rollback/*.before` 僅保存本次預計修改的 source 原始 bytes，不是第二個可啟動 UI。
