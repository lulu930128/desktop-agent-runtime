# G5 — Desktop ownership cutover plan

日期：2026-10-09
狀態：G5 source-ready；驗證結果見 [G5Checkpoint.md](G5Checkpoint.md)。正式 runtime／人工桌面驗收未做；G6/G7 未實作。下列保留實作規格。

## Goal

Qt 成為 canonical desktop owner：startup、single-instance reveal、Tray、Schedule OS notification delivery、canonical confirmations。Work Panel 不再由 launcher 啟動；`:23568` 不再由 canonical launcher listen。Electron canonical desktop mode只保留 Pet shell/presentation，不建立 Tray或claim Schedule notifications。

## 1. Launcher / single instance

- 保留 launcher mutex。
- activation event改為 Qt/application activation語意，不再叫 WorkPanelActivate。
- second launch只 signal primary Qt instance。
- primary收到 activation -> `showNormal()` / `show()` / `raise_()` / `activateWindow()`。
- first launch construct `KuroQtLauncherWindow(..., open_work_panel_on_start=False)`（或移除 canonical arg）並直接 reveal Qt。
- 不要求 `startup_profile.auto_start=true` 才能顯示 Qt；false時仍能開UI，由使用者手動啟動Profile。
- 不啟動 `WorkPanelControlServer`，canonical launcher不listen :23568。
- 不呼叫 `request_work_panel_activation()`。

## 2. Qt Tray / shutdown

- Qt建立唯一 `QSystemTrayIcon`。
- Tray至少提供：Show Kuro、Quit；可保留明確 Pet show action，但不得重新建立第二desktop UI。
- X/close：若不是 explicit quit/restart，只 hide Qt到tray並 ignore close event；不 stop runtime。
- Tray Show / second launch：reveal Qt。
- Tray Quit：設定 explicit quitting flag -> chat disconnect -> controller.close exact child runtimes -> tray hide -> QApplication.quit。
- restart launcher必須走 explicit quitting path，不可被 close-to-tray攔截。
- Qt tray unavailable時 fail safe：不得讓使用者永遠失去入口；保持window可見或明確退出，不可 silent hide。

## 3. Qt Schedule OS notification delivery

Core仍唯一決定 due/quiet/retry/lease/fencing。

Qt delivery流程：
`claim -> authorize -> QSystemTrayIcon.showMessage -> ack(delivered)`。

要求：
- no delivery if system tray/messages unavailable。
- authorize false不show、不ack delivered。
- claim/authorize/ack都走 QtController Core wrapper。
- single in-flight poll，bounded background request，不阻塞 Qt UI。
- notification click / tray message click reveal Qt（Qt API無 per-message identity時可採 general reveal）。
- delivery failure/exception用 `failed` 或 `unknown` ack，不能假裝delivered。
- Electron canonical Qt-owner mode不得同時 `startScheduleNotifications`。

## 4. Electron desktop-owner flag

Launcher/QtController spawn Pet時注入 `KURO_DESKTOP_OWNER=qt`，先清 inherited value。

Electron main在 `KURO_DESKTOP_OWNER=qt`：
- 不 createTray。
- 不 startScheduleNotifications。
- Pet BrowserWindow / Live2D / audio / presentation仍正常。
- mail canonical poller no-spawn規則維持。
- Work Panel/Reader/Briefing legacy code可存在但 canonical startup不reveal。

## 5. Confirmations

Canonical Qt writes继续使用Qt native QMessageBox/dialog confirmations：history delete、memory writes、Schedule mutate/cancel、restart等。

Electron Work Panel confirmation handlers可以保留到G7，但canonical Qt flow不得依賴。

## 6. G5 boundary

G5完成後：
- Work Panel never launches from launcher startup/second-launch。
- :23568 canonical listener = none。
- Qt main window = product entry。
- Qt tray = only tray owner。
- Qt = only Schedule OS notification delivery consumer。
- Electron = Pet shell/presentation only in canonical desktop mode。

暫不physical delete WorkPanelControlServer、activation legacy methods、Electron tray/notification code；G7 consumer inventory=0後刪。

## 7. Tests

- launcher entry: first launch shows/reveals Qt；does not construct WorkPanelControlServer；does not call request_work_panel_activation；auto_start false仍顯示Qt。
- second launch signals Qt activation event。
- Qt closeEvent -> tray hide without controller.close。
- Tray Quit -> controller.close once + chat disconnect + app quit。
- restart uses explicit quit path。
- Qt tray unavailable fail-safe。
- notification claim/authorize/show/ack happy path；authorize false；failure；single in-flight。
- Electron `KURO_DESKTOP_OWNER=qt` -> no tray / no schedule notification start。
- QtController Pet child env canonical desktop owner，inherited env cleared。
- :23568 not opened by launcher entrypoint。
- G3/G4/Core/Schedule/Node/renderer regressions。
- git diff --check + temp/pyc integrity。

## 8. Stop conditions

- 删除 legacy files（G7）。
- 改 Live2D render/presentation logic（G6）。
- 新增第二tray/notification consumer。
- Qt notification直接判定due/quiet（必须仍由Core claim/authorize决定）。
- WorkPanel fallback重新成为second-launch/startup path。
- stop/restart Central Voice。