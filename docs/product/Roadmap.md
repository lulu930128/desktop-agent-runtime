# Roadmap

## 北極星目標

Kuro 成為單一使用者可長期信任的 local-first AI 工作經理：即使替換 LLM、關閉 Live2D／TTS 或單一 integration 離線，仍能維持正確的工作狀態、來源時間、優先順序、提醒設定與 action audit；它能說明現在最值得注意的事情、理由與下一步，同時保留使用者對記憶、打擾與自動化的控制權。

Kuro 的研究主軸不是訓練另一個通用模型，而是驗證：可信的長期狀態、calibrated proactivity、受政策約束的行動與 embodied attention，能否讓可替換的模型在真實個人工作中比單次聊天更穩定有用。

## 近期優先順序

1. 建立 Kuro Research Core v0 的 versioned observation、freshness、persistence 與 decision trace，先以 shadow path 運作。
2. 將既有 mail／study source health 轉成 Core observation，修正 `connected` 與 `current` 混用問題，建立 legacy-vs-Core comparison。
3. 建立 backend-owned Task Store 與 Attention Queue，讓 Today priority、dedup、cooldown、quiet hours 與排序理由離開 Electron 展示層。
4. 建立 model-agnostic context compiler、replay lab 與 feedback metrics，能比較 rule-only、不同模型及 hybrid ranking。
5. 完成統一 Action／Policy／Confirmation／Audit contract 後，才逐項考慮 scoped automation。

## 里程碑

### 本機時間表的局部採用（2026-09-12）

使用者選定本機固定／特殊行程、待辦期限與學習安排作為下一條 Core 流程。
已完成 schema v3、時間投影、工作面板 CRUD 與 Core 通知排程；本機設定已啟用，正式 Launcher／Electron 已採用。
M4–M6 的自動化與正式操作證據見[交付紀錄](../agent-runs/kuro-local-schedule-core/Progress.md)。Observation path 仍為 shadow，不代表整體 R2／R5 完成。
Google Calendar 帳號與同步接入延後，參見[本次 contract](../agent-runs/kuro-local-schedule-core/Contract.md)。

### R0：Research Core shadow foundation

- 成果：Observation contract、正交的 availability／freshness／connection、SQLite schema、idempotency、bounded context projection、decision trace。
- 驗證：timezone、stale、partial／missing、schema、duplicate、concurrency 與 trace targeted tests。

### R1：真實 read-only source shadow

- 成果：至少一個真實來源透過 adapter 產生 observation；legacy 與 Core 結果可比較，差異可解釋。
- 驗證：不落盤的 live aggregate probe、synthetic fixtures、private payload audit。

### R2：Task／Attention owner

- 成果：正式 task、attention、dedup、cooldown、quiet hours、priority reason 與 Today materialized view 由 Kuro Core 管理。
- 驗證：migration、idempotency、concurrency、restart recovery 與 shadow comparison。

### R3：AI Manager 與 Replay Lab

- 成果：相同 observation set 可重播給 rule-only、不同 LLM 與 hybrid ranking；保留模型、policy、config digest、選擇與 feedback。
- 驗證：deterministic fixtures、repeat-run reliability、Top 3-5 helpfulness 與錯誤確定化指標。

### R4：Safe Action Control Plane

- 成果：Action Request、Policy Decision、Confirmation Queue、Execution Status、Audit 與 unknown-result reconciliation。
- 驗證：payload binding、allow／deny／confirm、quota、cancel、timeout、duplicate 與 exactly-once tests。

### R5：Runtime／Work Panel adoption

- 成果：Core 成為唯一 task／attention／policy／action truth；Launcher 只管理 lifecycle，Electron 與 AI runtime 透過 contract 消費。
- 驗證：Q3 exact-runtime identity、restart／crash／reboot recovery，以及 Q4 使用者可見流程與 screenshot。

### R6：Proactive／Embodied longitudinal evaluation

- 成果：依重要度與使用者設定選擇 Work Panel、notification、Pet short overview 或 voice，並持續量測效果。
- 驗證：helpful intervention、dismissal、duplicate、missed critical event、time-to-action、interruption burden 與模型替換比較。

## 延後事項

- 自有基礎模型訓練或 fine-tuning。
- 全面新增 mail、calendar、news、message 或其他 integration；先讓現有來源通過 Core contract。
- 自動寄信、交易、發布、刪除或其他高風險 `scoped_auto`。
- 再次大型 UI／Live2D 視覺改版。
- 將所有 chat、tool result 或每日 Briefing 自動升級成長期記憶。
- 公開 SaaS、多租戶、跨裝置同步或雲端作為唯一真相來源。

## 風險與依賴

- 現有 Qt、Electron、conversation runtime 與 local state 責任重疊；遷移必須 shadow-first，避免兩個 authoritative writer。
- 各 domain source 的 freshness 與 TTL 不同，不能用一個全域數值推定 current。
- 長期研究 trace 可能累積私人資訊；schema、retention、export 與清除必須最小化並可審計。
- LLM output 具有不穩定性；評估需使用可回放輸入、重複試驗與 rule-only baseline，而不能只保存一次漂亮結果。
- SQLite 適合單機 v0，但仍要驗證 lock、migration、backup、restore、crash recovery 與未來 service boundary。
- Memory Core、OMI 與其他外部專案各自有 ownership；Kuro Core 不得因整合方便而複製其 domain truth。
