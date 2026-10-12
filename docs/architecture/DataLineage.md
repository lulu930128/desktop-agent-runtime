# Kuro 資料流

2026-10-09 source 現況；provider 與正式桌面 acceptance 狀態見 [G8Checkpoint](../agent-runs/qt-ui-convergence-20261007/G8Checkpoint.md)。

## 對話與 presentation

Qt Chat → qt-primary WS → Conversation Runtime → tools/memory/policy → Qt text。Runtime 只將 allowlisted presentation payload 投給 pet-presentation WS；history、tool result、confirmation 不是 Pet 的輸入責任。

Pet 真正播完 audio queue 才回 correlated request_id ack；Qt 不偽造播放完成。Pet 離線或中斷時，Runtime 保留 primary conversation。相機／螢幕／麥克風擷取由 Qt 明確要求；Pet 回傳 transient capture，Qt 檢查目前 history 再送出，沒有 Pet 自行觸發對話路徑。

## Today 與 integrations

```text
Gmail provider → existing classification/preferences/rules
  → mail.refresh / Launcher mail_poller.py
  → mail_status_handoff + mail_work_handoff
  → Core bounded readers → SourceEvidence / TaskCandidate / Work / Attention
Study producer → configured snapshot → Core bounded readers ────────────┘
  → /v1/today → Qt Today
```

Mail handoff producer 不再建立舊 overview/tasks/modules UI snapshot；只保留 Mail evidence/time/privacy。沒有 Electron briefing store、Today classifier、Study watcher、Mail service 或 HTTP dashboard publish consumer。空資料不捏造 actionable items；原 provider policy 與 Core Today policy 不改。

`mail.daily_brief` 是明確的 provider query，不是 Today 的 cache 或 fallback；不將它的回應冒充 canonical Today。沒有背景讀取失敗後自動刷新 Gmail 的路徑。

Study 進度、Mail message truth、OMI 市場判斷仍屬外部 owner。Core GET 不持久化 integrations、不刷新 provider；來源時間、有效期、缺資料與 failure 依原 contract 傳遞。Mail failure 保留 bounded last-good status，不以寫入失敗取代 provider outcome。

## Schedule 與記憶

Qt Schedule → authenticated Core API → ScheduleStore／notifications／audit → Qt view/delivery。確認綁定 payload、expectedRevision、idempotency key；UI 不推導 eligibility 或建立第二份 queue。

History、character memory 與工具政策沿用 Runtime 的 canonical store/manager。Qt 提供既有讀寫管理；Pet status 不包含 history IDs 或 conversation text。舊 Briefing memory candidate store 無 production consumer；既有 private userData 未讀取或刪除。

## 保存邊界

Core DB schema 與 rollback 見 [CorePersistence](CorePersistence.md)。Tests 只建立 disposable synthetic DB/handoffs/userData；history、mail body、memory、OAuth、model/voice 素材沒有作本轮測試輸入。歷史 checkpoint 留存，source archive 只含被改 source，不含 private state。
