# G4 — Qt feature parity plan

日期：2026-10-09
狀態：Ready for implementation

## Goal

把 Qt 主 UI 收斂成最終 navigation：`Chat / Today / Schedule / Settings`。

G4 只做 canonical consumer parity；不做 G5 startup/tray/notification ownership cutover，不 physical delete legacy Electron。

## 1. Main navigation

- 主頁只保留 Chat / Today / Schedule。
- Settings 仍以 Qt dialog/entry呈現，不建立獨立 Reader/Briefing視窗。
- 舊 `briefing` 主頁改為 Today；不得再從 pet `/briefing` 取資料。
- Reader/long content 整合在 Chat detail / Today item detail / dialog，不新增獨立 window。

## 2. Qt Core client boundary

在 QtController 提供明確 Core read/write wrapper，統一使用 `CoreRuntime.request()`：
- `read_today()` -> GET `/v1/today`
- `read_schedule_view(...)`
- `read_schedule_item(id)`
- `mutate_schedule(payload)`
- `prepare_schedule(item)`
- `read_schedule_notifications()`
- `schedule_notification_action(payload)`
- `materialize_schedule(through)`

不得 Qt direct SQLite / ScheduleStore / handoff/provider IO。

Core unavailable 要明確 fail，不回空成功。

## 3. Today page

Qt Today consume `kuro.core.today.v1` only。

呈現：
- generatedAt / asOf / localDate / timezone / complete
- sections: immediate / focus / watch / normal
- sourceStates: availability/freshness/connection/limitations
- actionable item：title / summary / source / level / reasonCodes / dueAt / actionKind
- suppressed count

重要語意：
- complete=false 顯示「來源不完整」，不能當 0 tasks。
- complete=true 也只代表 caller supplied source/evidence健康，不宣稱真實世界 work coverage 完整。
- Mail/Study actionable item點擊先提供 detail/action metadata；G4 不直接讀 Gmail body / Study provider。
- Today page 不提供 legacy Briefing refresh。

## 4. Schedule page

Qt 直接 consume Core Schedule API。

最低 parity：
- status/today/timezone
- single-day / 7-day view
- coverage/limitations
- add/edit event/study/deadline
- all-day / start/end/due
- recurrence basic: none/daily/weekly/monthly + interval/end count/until
- notification enabled/minutesBefore/allDayTime/channel
- completion / reopen / skip
- cancel scope this/future/all
- optimistic revision conflict 顯示
- pagination/load more
- reminder records + dismiss/snooze

不要求逐 CSS/DOM 翻譯 Work Panel；Qt 可使用 existing dialogs/widgets。

## 5. Settings

保留現有 Qt settings canonical sections，調整命名到最終語意：
- General -> Assistant / Profile
- Appearance -> Pet
- Conversation -> Conversation & Memory
- Briefing -> Notifications / Sources（不再用 Briefing snapshot owner）
- Advanced -> Tools / Diagnostics / Runtime

至少顯示：
- Core capability status（Schedule/Today/Integrations）
- Mail/Study source health
- Mail manual refresh action可以保留既有 provider command compatibility，但不可重新引入 Briefing snapshot為 Today truth。

## 6. Legacy boundary

G4 完成後：
- Qt 不再呼叫 `read_briefing_summary()` 作主頁。
- Qt 不再要求 Work Panel 才能使用 Chat/Today/Schedule/Settings。
- `briefing-store.js` / `today-classifier.js` 可以暫時留在 Electron，直到 G7 physical delete。
- Electron Schedule UI可以暫時存在，但不是 canonical consumer。

不要在 G4 刪 WorkPanelControlServer / startup activation / tray / OS notification，這些屬 G5/G7。

## 7. Tests

新增/更新：
- Qt navigation keys = chat/today/schedule；Settings entry存在。
- Today payload rendering: healthy/degraded/empty/source states/reasons。
- Qt Today 不呼叫 pet briefing。
- Schedule read/add/edit/complete/skip/cancel/conflict/pagination/reminder actions用 mocked CoreRuntime。
- Core unavailable明確狀態。
- no direct SQLite/provider/handoff imports in Qt。
- G3 direct chat path regression。
- existing Core/Schedule/G1/G2/G3/Node regressions。
- Qt module compile/import smoke（offscreen若可用）。
- git diff --check / temp integrity。

## 8. Stop conditions

- 把 Work Panel Schedule TypeScript line-by-line翻成 Qt。
- Today重新讀 pet `/briefing`。
- Qt直接查 DB / provider / handoff。
- 在 G4 搬 Tray / second-launch / OS notification owner。
- physical delete legacy Electron。
- 為 UI方便新增第二套 Today/Schedule business logic。