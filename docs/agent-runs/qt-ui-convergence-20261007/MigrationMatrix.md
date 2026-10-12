> 2026-10-09 最終靜態補記：**STATIC BLOCKED；NOT ACCEPTED**。本輪另刪除 8 檔，G7 累計 33/35，剩餘 briefing-window.html、briefing-preload.js 仍受目前執行權限阻擋。Force 的 ArgumentException 已定位到 set_Attributes；無 Force 的實際刪除回報 WinError 5。Python 單次完整 326/25 suites、Node 83、MCP targeted 14（另 OMI 4）、renderer check/build、syntax/diff 通過；最小 Electron 與 G8 fixture 都重現 renderer 49／GPU 0xC0000135。正式 Windows 全部 UNVERIFIED。
>
> 最新逐項結果與安全補刪命令見 repo-root [G8FinalizationResults.json](../../../G8FinalizationResults.json)／[G8FinalizationHandoff.md](../../../G8FinalizationHandoff.md)。以下為上一輪歷史證據，保留原文；舊 10 檔 blocker、舊 Force 命令與舊測試數字不代表本輪現況，不應直接照舊執行。

# Kuro Qt / Live2D Migration Matrix

> **2026-10-10 最新 G7 狀態：35/35 physical deletion PASS，已沒有舊實作實體檔案。** G8 完整 source regression 尚需在可建立暫存檔的環境補驗，Electron hidden runtime 歷史 FAIL，正式產品仍 NOT ACCEPTED。見 [G7 最終 Reviewer 驗收](G7PostDeleteAcceptance-20261010.md)。上方日期 2026-10-09 的 33/35 是歷史。

## G8 current source ownership（2026-10-09）

**G6 source cutover 完成；G7 physical deletion BLOCKED（25/35 已刪）；G8 release NOT ACCEPTED。** 本節取代下方歷史 current-owner 敘述。Source／isolated acceptance 不代表正式 runtime adoption；證據見 [G8Checkpoint](G8Checkpoint.md)。

| 能力 | 唯一 source owner／consumer | Legacy consumer／刪除狀態 | Runtime 限制 |
| --- | --- | --- | --- |
| Startup／single instance／tray | launcher_qt + QtActivate + Qt main/tray | WorkPanel activation/API/recovery 已刪，:23568 config/listener construction=0 | Windows UUID event PASS；canonical visible/second launch/tray UNVERIFIED |
| Chat／session／history／memory／tools/policy | Conversation Runtime；Qt qt-primary | Pet conversation commands=0；Qt 不經 :23567 send-text | 真 WS＋synthetic conversation PASS；正式模型/工具/私人 stores 未存取 |
| Core lifecycle／Mail poller lifecycle | 既有 Launcher controller/CoreRuntime/MailPollerRuntime | 不依賴 Pet spawn；Electron Core/Mail/Study service startup=0 | temporary Core child/API PASS；正式 restart/cleanup UNVERIFIED |
| Today／Work／Attention | Core projection → /v1/today → Qt | 舊 classifier/store 外部 consumer=0；檔案 access denied | disabled／missing／stale／reason synthetic regression PASS；正式缺資料不可說成無待辦 |
| Study | Core bounded adapter／handoff | Electron watcher/reader=0；legacy module access denied | 現有 disabled；未改外部系統或重新讀 private handoff |
| Mail | 既有 mail.refresh producer／single Launcher poller → bounded handoff → Core → Qt | mail_briefing_poller 已刪／改名；UI snapshot/HTTP fallback=0；舊 Electron module access denied | 現有 disabled；無真 provider refresh／OAuth／send |
| Schedule truth／eligibility／fencing | Core Schedule | Electron Schedule bridge/consumer=0；舊 delivery module access denied | API/store regression與臨時 DB PASS |
| Schedule OS delivery／confirm | QtScheduleDelivery／Qt native dialogs | Electron tray／notification／confirmation dispatch=0 | real HTTP claim→authorize→synthetic display→ack PASS；OS visible UNVERIFIED |
| Live2D／audio／motion／expression／geometry | 單一 Electron Pet window/renderer | 非 Pet window creation/IPC=0 | build PASS；hidden Electron renderer FAIL；實際模型/多螢幕/devices UNVERIFIED |
| Pet-local status／control | :23567 local inspector／pet command allowlist | 無 :23568 poll，無 Core／Launcher token／Mail env | Node HTTP contracts PASS；實際 Electron status未完成 |
| Presentation descriptor | Launcher presentation_state → set-presentation | 無 HTTP compatibility reader/fallback | strict ACK/local validation PASS；actual model未讀取 |
| Capture／interrupt | Qt 主導；Pet 只擷取與播放；Runtime執行對話 | Pet 不發 text/mic/history/interrupt WS；過期 history capture 丟棄 | bound/capture unit PASS；camera/screen/mic UNVERIFIED |
| WorkPanel／Reader／Briefing UI | 無 owner／無 production entry | renderer/Reader/Launcher sources 已刪；Briefing HTML/preload 殘留 access denied | 永久退役；不允許復接為 fallback |
| 舊 private userData／DB | 原有 private owner | 不為 source deletion 搬移／刪除 | 未存取或改 schema |

### Consumer inventory 與 rollback

[G7DeletionManifest](G7DeletionManifest.json) 預列 35 paths；逐檔 hash/path 驗證後刪除 25、OS 拒絕 10。[G7DeletionResults](G7DeletionResults.json) 保存精確結果。Imports/require/routes/HTML/preload/IPC/config/tests/fallback/bridges 的 cluster 外 production consumer=0；blocked cluster 內相互 references 不代表可達 entrypoint。故 architecture consumer cutover 可驗證，**repository legacy implementation count 尚非 0**。

Package dependencies 全仍供 Pet 使用；舊 state keys 只從 source schema 移除，未讀取 private state。歷史 docs/screenshots/checkpoints 保留。

Rollback 使用 ignored source archive 與初始 WIP snapshot（[G8Integrity](G8Integrity.json)），不 reset HEAD、不雙 writer、不動正式 DB。補刪／正式 runtime checklist 見 [G8ManualAcceptance](G8ManualAcceptance.md)。

---

以下為歷史 source ownership／prerequisites；非 G8 現況。

## G5 canonical source ownership（2026-10-09，前輪歷史）

**G5 source-ready；正式 runtime／人工桌面驗收 UNVERIFIED；G6/G7 未做。** 驗證與限制見 [G5Checkpoint.md](G5Checkpoint.md)。本表取代下方歷史 inventory 中對相同能力的 current-owner 描述；下方保留 migration prerequisite／legacy 邊界紀錄。

| 能力 | Canonical source owner／path | G5 結果／保留邊界 |
| --- | --- | --- |
| Startup／single instance | launcher mutex + QtActivate event → Qt reveal | 首次顯示 Qt、second launch 只 reveal；auto_start=false 仍可見；VBS 不要求 Work Panel build |
| Qt 主視窗／tray | KuroQtLauncherWindow | X → hide；Show/click → reveal；Quit/restart explicit cleanup；tray 不可用保留入口 |
| Launcher control :23568 | Canonical launcher 無 listener construction | work_panel_api.py 保留到 G7；未量測正式 listener |
| Schedule 決策 | Core Schedule capability | due／quiet／retry／lease／fencing 不變 |
| Schedule OS 配送 | QtScheduleDelivery → controller notification-action | background claim/authorize → Qt showMessage → background ack；單一 inflight；delivered 僅 API handoff |
| Electron desktop-owner | KURO_DESKTOP_OWNER=qt | 無 Tray／Schedule consumer；Pet／Live2D／audio／presentation 保留；standalone legacy code 未刪 |
| Confirmations | Qt native dialogs | Canonical flow 不依賴 Work Panel handlers |
| WorkPanel／Reader／Briefing files | Legacy retained | G7 consumer inventory=0 之前不 physical delete；G6 render slimming 未做 |

以下為較早階段的歷史 inventory；「未開始」「現行」僅描述當時 checkpoint。

日期：2026-10-07  
Action：`KEEP` 保留現 owner；`MOVE` 移出現 owner；`REWIRE` 保留 owner但更換 consumer/path；`DELETE` parity 後刪除；`UNVERIFIED` 缺本輪 live evidence。

## G1 backend contract（2026-10-09）

**G1 source/backend contract ready；G2 未開始。** `work_contracts.py` / `work_projection.py` / `attention.py` / `today.py` / `today_shadow.py` 只提供 pure in-memory contract/policy/shadow helper，沒有 route、DB、Qt/Electron production consumer。Current Study/Mail aggregate status不會產 TaskCandidate；真正 actionable evidence producer與 legacy owner cutover屬 G2。詳見 `G1Checkpoint.md`。

## G0 freeze（2026-10-09）

**G0 source checkpoint ready。** 詳見 `G0Checkpoint.md`。M1e/M1f 正式 runtime adoption 仍為 **UNVERIFIED**；Study/Mail 預設 disabled、尚無 UI consumer cutover；Today/Briefing/Study UI reader 與 Mail poller/preferences/rules/detail 仍是 legacy primary。G0 已修 inherited Mail env leak 與 timestamp boundary robustness，完整 isolated regression 全綠。**G1 未開始**；後續依 `QtFinalConvergencePlan.md` 逐 Gate 執行，cutover 後以 consumer inventory=0 為 physical delete 門檻，不保留 silent fallback。

| Capability | 現行 owner / truth | Persistence | 現行 consumer / path | 最終 owner / UI | Source / function | Action | Cutover prerequisite | Rollback boundary | 風險 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Launcher config / profile | Launcher | `kuro_launcher.settings.yaml` + generated runtime conf | Qt / Work Panel / runtime | Launcher + Qt UI | `kuro_launcher/config.py`, `runtime_conf.py`, `qt_controller.py` | KEEP / REWIRE | Qt 完成全部 profile UX | 回到既有 controller，不新增第二 writer | P1 duplicate UI |
| Process lifecycle | Launcher | child handles / runtime lifecycle state | Qt + Electron status | Launcher + Qt | `qt_controller.py`, `services.py`, `procs.py`, `runtime_lifecycle.py` | KEEP | Qt 顯示/recovery parity | 保留既有 Launcher owner | P1 |
| Single instance / activation | Launcher but target=Work Panel | Windows mutex/event | second VBS -> Work Panel | Launcher -> Qt main window | `launcher_qt.py` mutex + WorkPanelActivate event | REWIRE | Qt tray/window reveal + second-launch tests | 恢復舊 activation event consumer | P1 |
| Qt main window | Qt | Qt state only | 目前 startup 後 hidden | 唯一主 UI | `kuro_launcher/qt_app.py::KuroQtLauncherWindow` | KEEP / REWIRE | M1/M2 parity | 逐 capability 回退，不雙 UI writer | P1 |
| Electron Work Panel | Electron | localStorage + downstream stores | main product UI | 無 | `renderer/src/work-panel/*`, `work-panel.html`, `briefing-preload.js` | DELETE | Qt parity + backend cutover + activation cutover | cutover 前保留 legacy primary | P1 |
| Reader window | Electron | appState bounds/visibility | long-form/chat auxiliary | 無；能力併 Qt | `reader-window.html`, `reader-preload.js`, `createReaderWindow` | DELETE | Qt long-content/attachment parity | 暫時保留 Reader 到 Qt parity | P2 |
| Conversation engine | Open-LLM-VTuber | runtime session/history | Electron frontend + Qt launcher-console | Runtime；Qt canonical frontend，Pet presentation subscriber | `routes.py /client-ws`, `websocket_handler.py` | KEEP / REWIRE | 定義 Qt frontend role、turn target、playback ack | 可回 Electron frontend，但不可雙主 session | P1 |
| Qt chat receive/status | Qt launcher-console client | 無獨立 truth | Qt chat UI | Qt | `qt_chat_client.py`, `qt_app.py::_runtime_chat_url` | KEEP / REWIRE | protocol tests | 保留 launcher-console read path | P2 |
| Qt chat send | Electron renderer 實際執行 | runtime history | Qt -> `:23567` -> Electron renderer | Qt -> conversation runtime | `qt_app.py::_send_chat_text`; `qt_controller.send_pet_text_for_chat/send_pet_text`; `main.js::sendTextToFrontend` | MOVE / REWIRE | Qt 成 canonical frontend；attachments/history/playback ack parity | 單一 feature flag 回舊 send path；不可同時雙 send | P0/P1 duplicate-turn |
| Chat history truth | Conversation runtime | chat history files | Qt / Work Panel | Runtime + Qt UI | `chat_history_manager.py`, Qt controller/history API | KEEP / REWIRE | Qt create/select/delete parity | 不搬 persistence | P1 |
| Character memory truth | Runtime memory manager | canonical long-term memory store/index | Qt + Work Panel + agent | Runtime + Qt UI | `character_memory_manager.py`, launcher memory helpers | KEEP / REWIRE | Qt management parity；移除 Briefing candidate ambiguity | 保留 canonical store | P1 |
| Briefing memory candidates | Electron Briefing store | `briefing-store.json` | Work Panel | 無；正式 Memory workflow | `briefing-store.js` candidate mutation | DELETE | 確認沒有 consumer 依賴 candidate 狀態 | 保留 legacy store backup到 cutover完成 | P2 dual memory truth |
| Tool identity/policy/execution | Runtime `mcpp/` | catalog/policy config + execution state | agent + Qt/Work Panel status | Runtime + Qt UI | `mcpp/*` / tool policy manager/executor | KEEP / REWIRE | Qt policy view parity | 不搬 policy logic到 Qt | P1 security |
| Core API host | Kuro Core process | 無獨立 domain persistence | Launcher / Electron main | Core transport/composition | `api_server.py`, `core_app.py`, `core_runtime.py` | KEEP / REWIRE | M1e `kuro.core.api.v1` + nested capability gate 已驗證；Qt consumer 仍待接 | 回復需整組 host/consumer identity contract；不可雙 server | P1 boundary |
| Schedule truth | Kuro Core Schedule capability | `work.sqlite3` schedule tables | Work Panel Schedule | Core + Qt UI | `schedule_api.py::ScheduleCapability`, `schedule_store.py` | KEEP / REWIRE | Qt client contract + CRUD/conflict tests | UI 可回舊 consumer，DB owner不變 | P0 data |
| Schedule notification decision | Kuro Core | notification/preferences/audit tables | Electron delivery worker | Core | `schedule_notifications.py` | KEEP | Qt delivery adapter可 claim/ack | delivery consumer可回 Electron，eligibility owner不變 | P1 |
| OS notification delivery | Electron | delivery state ack 回 Core | Windows user | Qt | `pet-electron/src/main-process/schedule-notifications.js` | MOVE | Qt adapter claim/authorize/display/ack parity | 一次只啟用一個 delivery consumer | P1 duplicate notification |
| Observation / Decision | Kuro Core shadow | observation/trace tables | tests / explicit shadow probe | Core backend foundation | `contracts.py`, `service.py`, `storage.py`, `shadow_probe.py` | KEEP / REWIRE | versioned production contract before adoption | 不用 shadow schema假裝 Today truth | P1 |
| Today priority/projection | Electron legacy primary | snapshot projection | Work Panel | Core/Backend Task-Attention-Today + Qt | `today-classifier.js`, `briefing-store.js` | MOVE | contract + timezone/freshness/dedup parity + shadow compare | legacy primary 保留直到單次 cutover | P0/P1 divergent truth |
| Briefing snapshot composition | Electron | `userData/briefing-store.json` | Work Panel / Qt legacy read | Backend/Core composition + Qt | `briefing-store.js` | MOVE / DELETE | versioned snapshot contract + backup + reader parity | legacy store只讀回退，不雙 writer | P1 |
| Mail provider truth | Mail provider / local MCP | provider state + private OAuth | Electron mail service | integration adapter；Qt只呈現/命令 | `Open-LLM-VTuber/local_mcp/mail_*` | KEEP | provider contract / auth / quota不變 | provider truth不搬 | P1 privacy |
| Mail status handoff / Core read API | 既有 explicit refresh producer 寫 bounded status；Core pure-read adapter | private mail_status.json，不含 raw mail/token | Core /v1/integrations/mail；尚無 UI reader cutover | Mail adapter/backend + future consumer | `mail_status_handoff.py`, `mail_adapter.py`, `handoff.py`, `core_runtime.py` | KEEP / REWIRE | M1f source-level adoption 已驗證：CLI/env 同一路徑、missing startup、disabled 404、auth_required、bounded Windows sharing retry；正式 runtime/consumer parity 待驗收 | 預設 disabled；保留 Electron legacy primary；不得雙 poller | P1 privacy / stale / missing |
| Mail poller / rules / preferences | Electron legacy primary | private Gmail preference/rule files | Briefing/Today | Integration plane/backend；Qt settings UI | `mail-briefing-service.js` | MOVE | single poller owner、source timestamp/failure contract、parity | 切換前停新 owner或舊 owner，絕不雙 poller | P0/P1 duplicate refresh/write |
| Study external truth | external study system | external snapshot/data | Electron | external owner | study system | KEEP | adapter只投影 | 不複製 progress algorithm | P1 |
| Study projection | Electron Briefing/Today legacy primary；Core read-only backend path 已存在 | legacy 合併 briefing；Core route 只讀 handoff、不持久化 | Electron Briefing/Today；Core `/v1/integrations/study` 目前無 UI consumer | Study adapter/backend + Qt | legacy: `study-briefing.js`, `main.js::studySnapshotPath`; Core: `integrations.py`, `study_adapter.py`, `core_app.py` | MOVE / REWIRE | M1a–M1c parity + M1e general host/read API 已通過；下一 gate 是 Qt/Today consumer parity 與單次 reader cutover | legacy UI read path保留到單次 cutover；Core GET 不寫 DB | P1 stale/missing semantics |
| Market data | OMI | OMI persistence/provider | runtime tools -> UI | OMI + Qt presentation | Runtime `market_preflight.py` / OMI MCP | KEEP / REWIRE | Qt保留 stale/partial/missing | 不在 Kuro複製 market logic | P1 domain |
| Pet Live2D render | Electron renderer | model assets + transient renderer state | desktop pet | Electron Live2D shell | `renderer/src/live2d/*`, `pet-live2d-renderer.ts` | KEEP | slim shell仍可獨立 render | 保留 renderer | P1 |
| Pet motion/expression/outfit | Electron pet renderer/control | transient pet state | Qt/Work Panel commands | Electron pet shell + Qt controls | `main.js::handleControlAction`, renderer commands | KEEP / REWIRE | :23567 pet-only allowlist | 不把 render logic搬 Qt | P1 |
| Pet window / mouse / geometry | Electron | `state.js` + OS window state | desktop | Electron pet shell | `pet-*.js`, renderer geometry/interaction | KEEP | Work Panel/Reader code移除後 regression tests | 保留 pet state | P1 |
| Pet control :23567 | Electron | process/window/pet state + legacy Briefing state | Launcher / Work Panel | pet-only local contract | `main-process/control-server.js` | REWIRE / DELETE non-pet routes | 所有 Briefing/Mail/WorkPanel consumer先切走 | 可暫保 legacy routes到 consumer=0；不可再新增 | P1 attack surface |
| Launcher control :23568 | Launcher | session token + controller state | Electron main / Work Panel | 待 Qt cutover後重新評估；可能刪除 | `work_panel_api.py` | REWIRE / DELETE | consumer inventory=0 或另有明確非-UI consumer | 先移 consumer，再刪 server | P2 |
| Work Panel confirmation dialogs | Electron main | 無 persistence | Work Panel writes | Qt native confirmation | `main.js::confirmWorkPanelAction` | MOVE | payload binding / confirm tests | cutover前保留舊 dialog | P1 safety |
| Tray | Electron | appState | user | Qt | `main-process/menus.js`, `main.js` | MOVE | Qt tray commands + recovery parity | 一次只顯示一個 tray owner | P2 |
| Central Voice inference | external Voice Runtime | external models/references | Kuro + others | external owner | `:18890` | KEEP | Kuro consumer tests | 不由 Kuro stop/restart | P0 shared service |
| Spoken rendering / bridge | Kuro bridge + runtime TTS consumer | transient derived text/audio | Pet audio/Qt text | Bridge/runtime + Live2D playback | `bridges/deeplx_bridge.py`, runtime TTS adapters | KEEP / REWIRE | Qt主 UI 不破壞 pet playback/completion | 文字 lane可獨立降級 | P1 |

## Cutover ordering constraints

1. 先 backend contract，再 Qt UI。
2. Today / Mail 維持 legacy primary；Study 已有 read-only Core backend route，但 Electron Briefing/Today 仍是 legacy UI primary，consumer parity 前不得切除。
3. Schedule 不重新實作。
4. Qt chat send 在 Electron Work Panel/Pet frontend縮減前必須先脫離 renderer。
5. OS notification delivery移到 Qt 前，不得同時讓 Electron 與 Qt claim同一批通知。
6. Work Panel、Reader、Briefing、:23568、:23567 legacy routes只有在 consumer inventory=0 後才能刪。
7. 每次 cutover 後重新搜尋 old import/route/IPC/fallback，確認沒有 parallel production path。
