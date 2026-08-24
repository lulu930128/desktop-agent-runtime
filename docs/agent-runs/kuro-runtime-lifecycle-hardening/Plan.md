# Plan

## Milestones

1. 固定 lifecycle contract
   - Scope: Launcher singleton、activation event、Electron status identity、close semantics。
   - Acceptance: owner、desired state、ready 條件與 fail-closed 行為都有單一實作位置。
   - Validation: source inspection、targeted contract tests。

2. 實作 Launcher-owned Work Panel recovery
   - Scope: `launcher_qt.py`、`kuro_launcher/qt_app.py`、`kuro_launcher/qt_controller.py`。
   - Acceptance: secondary launch 只 signal primary；primary coalesces requests，必要時重建 exact Electron，確認 ready 後 reveal。
   - Validation: `python -m unittest tests.test_launcher_entrypoint` 與新增 lifecycle tests。

3. 強化 Electron lifecycle 與 identity
   - Scope: `pet-electron/src/main.js`、control status contract、Node tests。
   - Acceptance: close/Alt+F4 只 hide，tray 仍常駐；status 可辨識 service、protocol、PID、instance。
   - Validation: `node --check`、renderer typecheck/build、targeted Node tests。

4. 真實 runtime acceptance
   - Scope: 精確 Kuro process lineage、1188／9981／23456／23567／23568、可見 Work Panel。
   - Acceptance: cold start、close/reopen、unexpected Electron exit/reopen、repeated launch 全部通過，沒有陌生或重複 owner。
   - Validation: VBS、endpoint probes、process identity、Computer Use 可見畫面。

## Stop-and-fix rules

- 若 listener identity 不明，停止沿用或終止該 PID；不得 broad kill。
- 若 targeted test、syntax、renderer build 或 runtime identity 失敗，先修正再進入 UI acceptance。
- 若變更會覆蓋既有 `pet-electron/src/main.js` mouse policy 或其他 dirty work，先重新對齊 diff。
- 若 Work Panel 只能在 LLM／TTS ready 後顯示，不得宣稱 cold-start 修復完成。
- 若只有 endpoint 200 而無可見 Work Panel，不得標記 Q4 完成。

## Decisions

- 2026-08-24：保留 VBS 為薄入口；使用 Windows named activation event 將 Work Panel intent 交給 primary Launcher。
- 2026-08-24：先做按需 crash recovery與 tray-resident close；不在尚未區分 intentional exit 前加入無限或自動 watchdog restart。
- 2026-08-24：Pet readiness 由 service identity + protocol + PID + control response 定義，不只看 process 或 port。
