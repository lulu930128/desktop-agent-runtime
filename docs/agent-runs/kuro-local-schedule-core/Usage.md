# 本機時間表使用與維護

在工作面板選「今天」，時間表位於優先事項下方。「新增安排」可建立一般行程、學習安排或待辦期限，支援單日／七日檢視。

- 固定行程：選每天、每週指定星期或每月指定日期，可設間隔、總次數或截止日期。月末不存在的日期略過。
- 特殊行程：選不重複。編輯固定行程可選這次、這次及以後、整個系列；「這次及以後」會建立後續系列，表單中的次數是新系列次數。
- 全天區間的結束日不包含在內。跨多日且今天仍進行的安排會出現；追蹤完成的逾期安排會持續保留，直到完成、略過或取消。
- 每筆可自行開啟提醒，選面板或桌面與面板。全天安排另設提醒時刻；預設提醒關閉。
- 「提醒設定」可調整勿擾，預設 Asia/Taipei 22:00–08:00。提醒紀錄可標已讀或延後 10／30 分鐘，也可指定 1–10080 分鐘。
- 送出時遇到版本衝突，草稿保留。按「重新讀取版本（保留草稿）」後，確認內容與範圍再儲存。若有無法安全映射的既有例外，請改用單次修改。
- 取消保存歷史，不硬刪除。已送出是 OS 接受通知，不代表已讀；結果不明不自動重送，可自行查看或延後。

## 本機服務

Launcher 依 `kuro_launcher.settings.yaml` 啟動 Core（預設 23569），正式資料為 `local_state/core/work.sqlite3`，schema 3；DB、備份與 log 都不進 git。Core token 每個 Launcher session 產生，僅傳給自己的 child，不放 renderer、URL 或命令列。

Core 中断時時間表顯示無法確認；其他 Chat、Mail、Study 仍有各自來源。正常關閉並重開 Launcher／桌寵，可恢復既有資料。已送提醒不因重啟再送；睡眠期間未送提醒只補最近 30 分鐘且仍有效的項目，更早標錯過。

故障線索：`launcher_logs/core/<instance>.log`、Launcher component log；不要以未授權的 `/status` 401 誤判服務死亡，該入口本來就需要 session token。

## 回退

正常關閉 Launcher，將 `core.enabled` 設 false 後重開。時間表會顯示 unavailable，資料保留，其他來源維持原路徑；不退回 Mail 的舊 Calendar placeholder。

要還原舊 schema，先停止 Core 並備份整份目前 DB，核對 migration 前 `.pre-v2-*`／`.pre-v3-*` 備份。不得用舊程式強開 v3，也不自動覆蓋可能包含新安排的正式 DB。

## 驗證

`tests/schedule_renderer_smoke.cjs` 使用 temporary DB/profile、真實 Core HTTP／IPC／preload／SchedulePanel DOM，退出碼 0 與 `launcher_logs/schedule-validation/result.json` 同時確認成功。截圖僅含 synthetic 安排。正式桌面驗證另記於 [Progress.md](Progress.md)。

外部帳號與 Google Calendar 同步、聊天自動寫入、語音通知尚未接入。
