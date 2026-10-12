# Qt Final Convergence Plan

> 2026-10-09 執行狀態：已依序推進至 G8；G6 source cutover 完成，G7 25/35 physical deletions、10 OS access denied；G8 source regression PASS，但 Electron renderer smoke FAIL、正式桌面 UNVERIFIED，release NOT ACCEPTED。最新結果見 [G8Checkpoint](G8Checkpoint.md)、[Progress](Progress.md)、[MigrationMatrix](MigrationMatrix.md)。以下 gate 規格／初版狀態保留，不以當時「尚未開始」描述現況。

日期：2026-10-09  
狀態：Product decisions locked；**G0 + G1 source checkpoints ready（2026-10-09），G2 尚未開始**。G0/G1 證據見 `G0Checkpoint.md` / `G1Checkpoint.md`；production runtime / UI adoption 尚未驗收。

## 0. 不可變更的終局決策

使用者已確認：

1. Electron 可以保留，但只能作為 **Live2D-only shell**。
2. Reader / Briefing / Work Panel 不保留獨立桌面視窗；全部能力回到 Qt。
3. Kuro 手動啟動後直接顯示 Qt；關閉主窗採 **X -> Tray**；真正退出只能由 Tray Quit。
4. Today 要呈現 actionable Mail / Study items，而不是只顯示 aggregate count。
5. 舊 Electron Briefing / Today / Reader / Work Panel 不做長期資料或功能保留。若需要調整功能，先完成 Qt cutover，再在 Qt / canonical backend 上修改。

因此最終產品只允許兩個 desktop surface：

- Qt Main App：唯一主 UI。
- Live2D Pet Shell：純寵物渲染與桌面互動。

舊 Electron application UI、legacy business ownership、fallback path 在完成逐項 cutover 後 **必須從 repository 實體刪除**，不是只停用。

---

## 1. Final target architecture

```text
User
 |
 v
Qt Main App
 |-- Chat
 |-- Today
 |-- Schedule
 |-- History
 |-- Memory
 |-- Settings
 |-- Diagnostics
 |-- Tray / confirmation / OS notifications
 |
 +-------------------------------+
 |                               |
 v                               v
Conversation Runtime           Kuro Core :23569
 |                             |-- Schedule
 |-- chat/session/history      |-- Integrations
 |-- MCP/tools/policy          |   |-- Study
 |-- character memory          |   `-- Mail
 |-- ASR/TTS protocol          |-- Work Projection
 |                             |-- Attention
 |                             `-- Today
 |
 `----------------------+
                        |
                        v
                 Live2D Pet Shell
                 |-- render/model
                 |-- motion/expression
                 |-- lipsync/audio
                 |-- mouse/window/display
                 `-- pet-local control only
```

### Ownership invariants

- Qt = presentation + explicit user commands only.
- Core = Schedule / Work / Attention / Today / integration projection.
- Conversation Runtime = chat / memory / tools / policy.
- External domain systems = their own truth.
- Live2D shell = rendering / pet interaction only.
- Qt 不直接查 SQLite。
- Qt 不直接讀 mail_status.json / study_snapshot.json。
- Qt 不直接呼叫 Gmail provider。
- Qt 不重做 Schedule recurrence / notification eligibility。
- API host 不承擔 domain business logic。
- 一次只允許一個 authoritative writer / reader path。
- Cutover 後不保留 silent fallback。

---

## 2. Legacy freeze rule

從本計畫開始，以下 Electron legacy 區域 **Feature Freeze**：

- Work Panel
- Reader
- Briefing UI
- briefing-store.js
- today-classifier.js
- study-briefing.js
- mail-briefing-service.js
- Electron Schedule UI
- Electron Tray
- Electron notification delivery
- Work Panel control proxy

允許：

- blocking bug fix
- migration / parity instrumentation
- rollback safety fix
- security / data-loss fix

不允許：

- 新功能
- UX 改版
- 新 business rule
- 新 provider behavior
- 新 persistence
- 新 fallback

若未來想改功能，必須等 capability 已搬到 Qt / canonical backend 後再改。

---

## 3. Delete, not deprecate

所有 legacy capability 都必須走：

```text
contract
-> shadow/parity
-> new consumer
-> runtime acceptance
-> authoritative cutover
-> consumer inventory = 0
-> physical delete
```

禁止：

```text
new path + old path both production
old path hidden but retained forever
silent fallback to Electron legacy
Qt reimplementing old business logic
```

Git history 是 rollback history；production source 不需要永久保留 legacy application。

---

# G0 — Foundation checkpoint freeze

## Goal

把目前 M1a-M1f backend foundation 收成一個可回溯 checkpoint，避免後續 Qt migration 與 Core foundation 混在同一個超大 diff。

## Must contain

- Study bounded adapter / handoff / parity.
- General Core API Host.
- ScheduleCapability boundary.
- IntegrationRegistry.
- Mail bounded producer handoff.
- Mail Core adapter.
- Mail Launcher CLI/env wiring.
- Windows handoff reader/writer bounded retry.
- M1f regression evidence.

## Acceptance

- Core tests PASS.
- Schedule tests PASS.
- Mail producer / Mail adapter / Study adapter PASS.
- Electron core-client PASS.
- diff check PASS.
- no validation temp / pyc side effects.
- current ownership docs match source.

## Exit rule

建立明確 checkpoint 後，下一 Gate 才能開始。

---

# G1 — Work / Attention / Today backend

## Goal

建立 Electron-independent canonical Today backend，不複製 today-classifier.js。

## New contracts

至少：

- TaskCandidate
- Task / WorkItem
- AttentionReason
- AttentionDecision
- TodayItem
- TodaySection
- TodayView
- SourceEvidence

## Required semantics

- source identity
- observedAt / receivedAt / validUntil
- availability / freshness / connection
- dedup key
- reason for inclusion
- reason for priority
- timezone / date boundary
- missing / partial / stale semantics
- deterministic ordering
- privacy projection

## Data flow

```text
Study Observation --+
                    +-> Work Projection -> Attention -> TodayView
Mail Observation ---+
```

## Restrictions

- no Qt dependency
- no Electron dependency
- no Gmail provider call
- no direct study file read outside integration adapter
- no Task = Observation shortcut
- no copying Electron classifier line-for-line

## Acceptance

- synthetic Study + Mail can produce TodayView with deterministic reasons.
- stale/offline/missing data does not become false zero.
- no production writer cutover yet.
- shadow comparison tooling exists.

---

# G2 — Backend legacy owner cutover

## Order

1. Study reader
2. Mail status / refresh ownership
3. Briefing composition
4. Today projection

## Study

Target:

```text
Study system -> handoff -> Core integration -> Work/Today
```

Cut:
- Electron study-briefing.js no longer authoritative reader.

## Mail

Target:

```text
Mail provider adapter / explicit producer
-> bounded handoff
-> Core integration
-> Work/Today
```

Need separate decisions for:
- provider fetch
- poller lifecycle
- preferences/rules
- message detail
- manual refresh

Electron cannot remain lifecycle owner at final state.

## Briefing / Today

- briefing-store.json stops being canonical.
- Core owns Today composition.
- old memory candidates are not migrated into a second memory workflow.
- old Briefing snapshot is rollback evidence only until cutover finishes.

## Acceptance

Each owner is cut one at a time.
No dual writer.
No fallback.
Old module remains only for parity until consumer inventory is zero.

---

# G3 — Qt conversation independence

## Goal

Qt Chat must work even if Live2D shell is completely closed.

Current forbidden production dependency:

```text
Qt
-> :23567 send-text
-> Electron main
-> renderer
-> conversation runtime
```

Target:

```text
Qt
-> /client-ws
-> Conversation Runtime

Conversation Runtime
-> presentation/audio events
-> Live2D shell
```

## Must support

- send
- interrupt
- history create/select/delete
- attachments
- active conversation identity
- runtime reconnect
- tool output
- mic/ASR control
- playback acknowledgement / active frontend semantics

## Acceptance

- Live2D process stopped: Qt text chat fully functional.
- Qt stopped: Live2D shell cannot become a second conversation UI.
- no duplicate-turn risk.
- no dual canonical frontend.

---

# G4 — Qt feature parity

## Final main navigation

```text
Chat
Today
Schedule
Settings
```

No independent Reader or Briefing desktop window.

## Chat

Contains:
- transcript
- attachments
- long-form/detail panel
- tool result details
- history
- stop/interrupt
- mic/perception controls where appropriate

## Today

Contains:
- Focus / Attention
- Mail
- Study
- Calendar
- Market / other sources
- source health / stale / partial / offline

Mail / Study show actionable items and reason, not only count.

## Schedule

Qt consumes canonical Core Schedule API.
No direct DB.

## Settings

Suggested grouping:

- Assistant
- Conversation & Memory
- Perception
- Tools & Permission
- Pet
- Notifications
- Diagnostics

## Acceptance

Qt parity checklist covers every Work Panel/Reader/Briefing feature still considered valid.
Anything intentionally not migrated must be explicitly DELETE, not silently forgotten.

---

# G5 — Desktop ownership cutover

## Startup

Current:

```text
construct Qt
-> open Electron Work Panel
-> hide Qt
```

Target:

```text
Launcher
-> show Qt
-> start/reconcile Core + Conversation
-> start Live2D shell in background
```

## Single instance

Second launch activates/reveals Qt.

Remove WorkPanel activation event naming/semantics.

## Window behavior

- Manual start -> Qt visible.
- X -> hide to Qt tray.
- Tray Show -> reveal Qt.
- Tray Quit -> explicit full application shutdown.
- Pet show/hide independent from runtime.

## Move to Qt

- Tray
- native confirmations
- restart/recovery UX
- OS Schedule notifications

## Acceptance

- Work Panel never launches.
- Electron app can start only as pet shell.
- only one Tray owner.
- only one OS notification delivery consumer.

---

# G6 — Live2D shell slim-down

## Electron may keep

- BrowserWindow for pet only
- Cubism / WebGL renderer
- model loading
- motion
- expression
- lipsync
- audio playback
- pointer / drag / click interaction
- passthrough
- display / DPI / geometry
- pet-local state
- pet-only local control API

## Electron must lose

- Work Panel
- Reader
- Briefing
- Today
- Mail integration
- Study integration
- Schedule UI
- Schedule notification delivery
- Tray
- Launcher management UI
- history/memory/tool-policy proxy
- confirmation UX

## :23567 target

Only pet-local commands/status.

No:
- /briefing/*
- /mail/*
- /work-panel/*
- schedule
- memory candidates
- conversation send-text proxy

---

# G7 — Physical legacy deletion

## Delete candidates

After consumer inventory reaches zero:

- renderer/src/work-panel/*
- work-panel.html / preload / bridge
- reader-window.html / reader preload
- briefing-window.html / briefing preload
- briefing-store.js
- today-classifier.js
- study-briefing.js
- mail-briefing-service.js
- Electron schedule UI bridge
- Electron schedule notification delivery
- Electron tray code
- Work Panel activation / recovery
- WorkPanelControlServer
- legacy confirmation flow
- legacy control routes
- Briefing memory candidates
- unused localStorage/state keys
- unused package dependencies
- obsolete tests/docs

## :23568

Default final decision: remove entire Work Panel control surface if consumer inventory = 0.

If a non-UI consumer is discovered, it must be explicitly justified and renamed to its real responsibility. No legacy-name compatibility layer.

## Acceptance

Repository-wide search:

- imports
- require()
- IPC
- HTTP routes
- preload exposure
- renderer entrypoints
- config
- tests
- docs
- fallback
- package dependencies

must show production consumer count = 0 before deletion.

After deletion, another search must show old implementation count = 0 except historical docs/changelog where intentional.

---

# G8 — Final acceptance

## Runtime acceptance

- cold boot
- Windows startup / login
- second launch
- Qt reveal
- tray hide/show/quit
- full shutdown
- Qt restart
- Core restart/reconnect
- Conversation runtime restart/reconnect
- Live2D crash/restart
- Live2D absent while Qt Chat works
- Qt hidden while pet remains functional

## Feature acceptance

- Chat
- attachments
- history
- memory
- tool policy
- microphone
- camera/screen if retained
- Schedule CRUD
- recurrence
- completion / skip
- notification delivery
- Mail refresh / auth_required / stale / offline
- Study stale / missing / current
- Today inclusion reasons
- Today priority reasons
- actionable Mail / Study items
- source health
- Voice
- Live2D motion / expression / lipsync
- multi-monitor / DPI / placement

## Architecture acceptance

Must all equal zero:

- Work Panel production consumer
- Reader production consumer
- Briefing window production consumer
- briefing-store writer
- parallel Today owner
- parallel Study reader
- parallel Mail poller
- Qt direct provider access
- Qt direct Core DB access
- Electron business ownership outside pet shell
- silent legacy fallback
- duplicate notification consumer
- duplicate tray owner

## Final release verdict

Only after G8 may reviewer say:

**Qt Final Convergence 完成，可以刪除 migration scaffolding / 封版。**

---

# Execution policy

## One Gate at a time

每個 Gate：

1. reviewer reads actual repo
2. define exact owner / consumer / delete scope
3. Codex implements
4. reviewer rereads diff/source
5. targeted tests
6. runtime acceptance if applicable
7. update migration matrix
8. only then next Gate

## No opportunistic redesign

直到 Qt 已 canonical：

- 不順便重做 Mail UX
- 不順便改 Study priority
- 不順便改 Today visual design
- 不順便改 Live2D renderer architecture
- 不順便替換 provider

先完成 ownership convergence，再做 product improvement。

## Commit strategy

建議至少依 Gate 建 checkpoint commit，不把 G1-G7 壓成一個 commit。

可接受更細：
- backend contract
- consumer cutover
- legacy deletion

但不可把 unrelated cleanup 混進 migration commit。

---

# Current position

已完成 foundation：

- M1a Study adapter
- M1b bounded handoff
- M1c Study parity
- M1e Core API Host
- M1f Mail integration boundary

下一正式 Gate：

**G0 checkpoint freeze -> G1 Work / Attention / Today backend**

不應直接跳 G4 Qt UI，因為 Today/Briefing business ownership 尚未移出 Electron。

