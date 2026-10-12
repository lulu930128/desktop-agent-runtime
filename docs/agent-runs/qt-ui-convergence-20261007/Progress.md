> 2026-10-09 最終靜態補記：**STATIC BLOCKED；NOT ACCEPTED**。本輪另刪除 8 檔，G7 累計 33/35，剩餘 briefing-window.html、briefing-preload.js 仍受目前執行權限阻擋。Force 的 ArgumentException 已定位到 set_Attributes；無 Force 的實際刪除回報 WinError 5。Python 單次完整 326/25 suites、Node 83、MCP targeted 14（另 OMI 4）、renderer check/build、syntax/diff 通過；最小 Electron 與 G8 fixture 都重現 renderer 49／GPU 0xC0000135。正式 Windows 全部 UNVERIFIED。
>
> 最新逐項結果與安全補刪命令見 repo-root [G8FinalizationResults.json](../../../G8FinalizationResults.json)／[G8FinalizationHandoff.md](../../../G8FinalizationHandoff.md)。以下為上一輪歷史證據，保留原文；舊 10 檔 blocker、舊 Force 命令與舊測試數字不代表本輪現況，不應直接照舊執行。

# Kuro Qt / Live2D 收斂進度

> **2026-10-10 新增：G7 35/35 physical delete 已獨立複查 PASS。** 本輪 G8 targeted source tests／syntax PASS，但完整 Python／Node／Renderer build 受執行環境寫入權限限制未完成，正式桌面仍待人工驗收；release NOT ACCEPTED。請以 [最新 G7/G8 閘門記錄](G7PostDeleteAcceptance-20261010.md) 為準。下方各輪 33/35 是歷史證據。

## G5 → G8 本輪結果（2026-10-09，取代下方歷史現況）

**已依序執行至 G8；release verdict：NOT ACCEPTED。** Source regression 已通過；G7 剩 10 個 OS 拒絕刪除的檔案，隔離 Electron renderer smoke FAIL，正式 Windows 桌面驗收 UNVERIFIED。不得宣告封版或移除 migration evidence。

| Gate | 實際結果 | Checkpoint |
| --- | --- | --- |
| G5 adoption／查缺 | 既有 Qt canonical startup／event／tray／notification source 已核對；isolated Windows event 與 offscreen tests PASS；正式 desktop 未啟動 | [G5](G5Checkpoint.md) |
| G6 Pet-only | 移除 Electron business／application UI ownership；pet-local status 不再輪詢 :23568；Qt 直接持有 conversation／capture send | [G6](G6Checkpoint.md) |
| G7 physical deletion | 35 檔預列與備份、外部 production consumer=0；25 已刪、10 access denied。BLOCKED | [G7](G7Checkpoint.md)、[manifest](G7DeletionManifest.json)、[結果](G7DeletionResults.json) |
| G8 acceptance | Source／architecture checks PASS；HTTP／WS／Qt isolated smoke PASS；Electron renderer smoke FAIL；正式桌面／devices UNVERIFIED | [G8](G8Checkpoint.md)、[人工 checklist](G8ManualAcceptance.md) |

### 本輪實際變更與驗證

- Electron 僅一個 Pet window、pet-only :23567、local renderer status／presentation、render/audio/input/geometry；沒有 tray、Schedule consumer、WorkPanel/Reader/Briefing startup、launcher proxy、history/memory/policy IPC 或 send-text。
- Qt／Launcher 仍是既有 lifecycle owner；Core/Mail 啟動不依賴 Pet。移除 legacy control config、Qt dead methods／flags、舊 state keys；Qt command ACK 必須明確 ok=true。
- Mail 舊 HTTP Briefing consumer 已移除；既有 poller 改名 mail_poller.py → mail.refresh，identity/catalog/policy 同步。只保留 bounded Mail handoff，移除 UI sections／假空 tasks；Today/Mail/Study business policy 不變。
- 第一輪 Python 全 root regression **323 tests／25 suites，exit 0**；後續新增 strict ACK 2 tests／Mail snapshot 1 test 後，受影響 suites 全通過，最終已驗證 root test 集合 **326**。另 Runtime MCP identity/policy/routing **14**、Node **83** PASS。不將 326 描述成單次完整重跑。
- Renderer typecheck／build、syntax、diff 與 UTF-8 checks 見 [G8 results](G8ValidationResults.json)。實際 changed/path sets、初始 88 dirty paths 保全與 archive checksum 見 [G8 integrity](G8Integrity.json)。
- 跨層 smoke 使用真 loopback HTTP／WS、temporary DB、Qt offscreen、synthetic provider/tray；未驗證實際模型、語音或 OS notification。
- Electron 隱藏 fixture：renderer launch-failed 49、GPU -1073741515，process exit 2147483651；完整 OS/dependency 原因未定位，不視為 source 或正式桌面 PASS。

### 邊界、rollback 與 pending blockers

初始 main/HEAD、35 modified＋53 untracked 已完整快照：[G5G8InitialPathSnapshot](G5G8InitialPathSnapshot.json)。本輪只修改本 repo；未 commit/push、改 ACL／registry／logon、讀取 private payload／history／memory／model／voice，或操作 Central Voice :18890。Mail/Study 保持 disabled；未刷新 provider／發送外部內容／遷移正式 DB。

G7 source rollback archive 為 repo-root ignored `g7-source-rollback.zip.bak`；含 35 個候選刪除檔（包括起點 WIP）與 G7/docs 修改前 preimages，不是完整 G6 前 worktree 備份。回退必須局部配對 source/consumer，避免第二個 UI/tray/poller；不以 HEAD reset 覆蓋起點 WIP。

下一步由有既有檔案權限的使用者完成 10 檔補刪及 Electron／Windows checklist；精確命令、判定與停止條件在 [G8ManualAcceptance](G8ManualAcceptance.md)。無法完成的項目保留 FAIL／BLOCKED／UNVERIFIED，不能只改文件狀態。

---

以下保留各階段歷史紀錄；「最新」「未開始」只描述該 checkpoint 當時狀態。

## G5 checkpoint（2026-10-09，前輪歷史）

**G5 source-ready；正式 runtime adoption／人工桌面驗收未做；G6/G7 未實作。** 詳見 [G5Checkpoint.md](G5Checkpoint.md)。Qt 已接管 canonical startup、single-instance reveal、tray、Schedule notification delivery 與 native confirmations；launcher 不再啟動 Work Panel／`:23568`。Electron child 使用 `KURO_DESKTOP_OWNER=qt`，不建立 tray、不 claim Schedule notification，保留 Pet／Live2D／presentation。

最終完整回歸：Python **317/317 PASS**（G5 17、launcher 6、G4 15、G3 27、Core 137、Schedule 44 等）；全部 Node **83/83 PASS**；renderer typecheck、Node syntax、diff check 全通過。TEMP/TMP 指向獨立 repo-root disposable，finally 精確清除；前後 status／file set／ignored pyc-tmp path set 相同。先前 Node compile cache 殘留造成 wrapper integrity failure，已修正清理順序並重跑全套通過。

目前只證明 source 與 synthetic/offscreen 行為；正式單一 tray／OS 通知／mutex activation／owned child cleanup 仍待獨立桌面驗收。未 physical delete legacy、未改 Live2D 架構、未操作 Central Voice／ACL、未 commit/push。

以下保留各階段歷史紀錄；其中「未開始」只描述該 checkpoint 當時狀態。

日期：2026-10-07

## G1 checkpoint（2026-10-09，最新狀態）

**G1 source/backend contract ready；production adoption / UI cutover 未做；G2 未開始。** 詳細 contract、attention policy、dedup、timezone、source health、shadow privacy 與 reviewer boundary 見 `G1Checkpoint.md`。新增 pure `SourceEvidence -> TaskCandidate -> WorkItem -> AttentionDecision -> TodayView` pipeline；aggregate Mail/Study Observation 明確不能直接產 task；沒有 Today API/DB/Qt/Electron production wiring。G1 targeted **53/53 PASS**；foundation regression Mail 16/16、Mail adapter 13/13、Study 16/16、Core 121/121、Schedule 44/44、Node 4/4 PASS；diff check/integrity/temp cleanup通過。

## G0 checkpoint（2026-10-09，最新狀態）

**G0 source checkpoint ready；production runtime adoption 未驗收；G1 未開始。** 詳細 owner、修正、reverse-search 與 isolated regression 證據見 `G0Checkpoint.md`。本輪修正 P1 inherited `KURO_MAIL_STATUS_FILE` leak 與 Study/Mail timestamp overflow robustness；未發現 blocking parallel Core/Mail/Study path。Mail 16/16、Mail adapter 13/13、Study 16/16、Core 68/68、Schedule 44/44、Node 4/4 PASS；`git diff --check` PASS，validation temp/ignored artifact/file set 無新增副作用。沒有正式 runtime/provider/UI adoption、沒有 G1/Qt/Today 實作、沒有 commit/push。

## M0 結論

M0 已建立 source-based migration baseline。現況不是「Electron 只剩 UI」：Electron main process 仍持有 Today / Briefing / Mail / Study 的正式 legacy path，且 Qt chat 的送出路徑仍依賴 Electron renderer。因此不能先刪 Work Panel / Reader / Briefing，也不能只把 Qt 視窗改成 visible 就視為完成 cutover。

本輪未修改 production source behavior。

## Git baseline

- repo：`C:\project\desktop-agent-runtime`
- branch：`main`
- 開始盤點時 working tree clean。
- Codex 觀察到本機 `main...origin/main [ahead 3]`。
- M0 只允許新增本目錄的規劃／證據文件，不 commit、不 push。

## 2026-10-07 live baseline

約 09:58 Asia/Taipei 唯讀觀察：

| Port | 預期服務 | 本輪觀察 |
| --- | --- | --- |
| 1188 | Bridge | 無 listener |
| 18890 | Central Voice | listener 存在，PID 42060 |
| 23456 | Conversation runtime | 無 listener |
| 23567 | Pet control | 無 listener |
| 23568 | Launcher control | 無 listener |
| 23569 | Kuro Core | 無 listener |

Central Voice `/health` 本輪確認為 `voice-runtime`、protocol 1、status `available`。其 executable 位於外部中央語音工作區；本輪未停止或重啟。

### UNVERIFIED

本輪沒有啟動目前停著的 Kuro，原因不是啟動器未知，而是正常 startup 會啟動 Core materialization / notification worker，並可能啟動 Electron Mail poller，會產生正式 state side effect。依 M0 約束不為了 baseline 人為寫 production state。

因此下列狀態只能引用既有歷史驗收或 source，不能標成本輪 live PASS：
- 完整 Kuro boot
- Qt hidden + Electron Work Panel 真實視窗狀態
- Core Schedule runtime
- Mail poller runtime
- Reader / Work Panel / Briefing window runtime
- Conversation / Pet runtime adoption

CIM process lineage 查詢受環境限制，Central Voice 的完整 parent lineage亦未驗證。

## 已確認 source 邊界

### 啟動 / single-instance
`launcher_qt.py`：
- 取得 `Local\\KuroDesktopAgentLauncher` mutex。
- 第二次啟動目前送 `Local\\KuroDesktopAgentWorkPanelActivate`。
- 建立 `KuroQtLauncherWindow(..., open_work_panel_on_start=True)`。
- 啟動 `:23568` `WorkPanelControlServer`。
- startup 主動 `request_work_panel_activation("startup")`。
- 最後 `window.hide()`。

因此 M3 必須改 activation ownership，而不是只把 `hide()` 換成 `show()`。

### Qt chat 仍依賴 Electron send path
Qt 已有 `QtRuntimeChatClient`，以
`/client-ws?client_role=launcher-console`
連 conversation runtime，用來接收狀態／文字／history control。

但 `KuroQtLauncherWindow._send_chat_text()` 並沒有呼叫 `QtRuntimeChatClient.send_text()`，而是：
`Qt -> QtLauncherController.send_pet_text_for_chat() -> send_pet_text() -> Pet control send-text -> Electron main sendTextToFrontend() -> executeRenderer() -> window.__kuroPetSendTextInput()`。

所以目前 Electron renderer 是 Qt chat text-send 的 production dependency。Qt 的 launcher-console role 又被 runtime 明確排除於 controllable frontend session；M2 必須先設計正式 Qt frontend role / playback acknowledgement / hot-switch target semantics，再切除 Electron send ownership。

### Schedule / Core
- `kuro_core.schedule_api.ScheduleServer` 是 production Schedule owner。
- Core worker materialize recurrence 並執行 notification decision。
- `work.sqlite3` 是 Schedule persistence。
- Electron 目前只是 consumer + OS notification delivery。
- Observation / Decision `KuroCore` 仍是 shadow；沒有 production Task / Attention / Today API。

### Electron legacy primary
下列模組不是純 UI：
- `briefing-store.js`：snapshot normalization/persistence、study merge、Today projection、memory candidate persistence。
- `today-classifier.js`：priority classification、normalization、sort / dedup 等 Today 語意。
- `mail-briefing-service.js`：poller lifecycle、preferences/rules、refresh/message read、priority rules。
- `study-briefing.js`：讀 external study snapshot、normalize、merge、Today/source projection。

### Control surfaces
- `:23567` Pet control 現在混合 pet status/control、Work Panel status、Briefing、Mail、snapshot/memory-candidate mutation；最終需縮成 pet-only。
- `:23568` Launcher control 現在主要服務 Electron Work Panel 的 profile/history/memory/tool/runtime proxy；Work Panel 消失後需重新盤點是否仍有必要存在。
- `:23569` Core 必須保留 schedule contract；不得由 Qt 直接碰 DB。

## M0 新增的重要 blocking dependency

1. Qt chat send 尚未脫離 Electron renderer。
2. Today / Briefing / Mail / Study 沒有現成 production Core API 可以直接切。
3. Electron OS notification delivery 尚未移到 Qt。
4. single-instance activation target 仍是 Work Panel。
5. `:23567` contract 混入大量非 pet responsibility。
6. Work Panel / Reader / Briefing 的 window lifecycle 仍深度耦合 `pet-electron/src/main.js`。

## 下一個安全施工點

M1 不應直接刪 Electron，也不應立即把 Today classifier 複製到 Python/Qt。

建議先做：
1. 定義 integration observation / Today projection 的正式 backend contract。
2. 以 Study 這類 read-only source 做第一個 shadow adapter，驗證 freshness / status / projection parity。
3. 保持 Electron legacy primary，只比較結果；沒有 parity evidence 前不切 authoritative read。
4. 同時把 Qt chat direct-send 列為獨立 cutover track，在改前先補 protocol tests，避免 launcher-console/frontend role 產生雙 session 或播放 ack 問題。

## 驗收狀態

- Source inventory：完成。
- Live listener baseline：完成。
- Production live boot：UNVERIFIED（刻意不啟動）。
- Production behavior changes：無。
- Commit / push：無。


## M1a — Study shadow adapter

狀態：**完成 shadow foundation；尚未 production cutover。**

本階段新增：

- `kuro_core/study_adapter.py`
  - 將既有 Study snapshot schema 投影成既有 `Observation` contract。
  - 無檔案 I/O、無 DB write、無 Today priority ownership、無 production wiring。
  - `connection` 固定維持 `unknown`；local snapshot 存在不等於 external provider 連線。
  - `updatedAt` 只負責 data freshness；缺失時 freshness=`unknown`，不偽造 current。
  - 缺失/無效 count 不預設成 0；結構不完整會留下 limitation，必要時 availability=`partial`。
  - details 只保存 bounded aggregate counts / schema metadata，不保存單字、meaning、Today 私人內容。
- `tests/test_kuro_core_study_adapter.py`
  - valid snapshot
  - stale transition
  - missing snapshot
  - missing timestamp
  - malformed counts
  - malformed word items
  - unsupported schema
  - sanitized semantic idempotency
  - TTL validation

### Reviewer 發現與修正

第一版 adapter 對 `vocab.today.review/focus/new` 只取 array length；但 Electron `study-briefing.js::normalizeStudyWord()` 只有帶 `word_id / wordId / id` 的項目才保留。

這會造成 malformed word 在 Python shadow path 被多算、Electron legacy path 被丟棄的 divergence。

已修正為：
- Python 也只計入具有效 word id 的 item。
- invalid item 不計入 aggregate count。
- 若存在 invalid item，保留有效 count，但 availability 降為 `partial`，並加入 `study_today_<bucket>_invalid_items:<n>` limitation。

### 驗證證據

受控 disposable temp root 下執行，不碰正式 `local_state/core/work.sqlite3`：

- `test_kuro_core*.py`：**25 / 25 通過**。
- synthetic valid parity：
  - Electron `normalizeStudySnapshot()` 與 Python adapter 的 `updatedAt`、`vocabTotal`、`vocabDue`、`vocabWithMistakes`、`todayReview/focus/new` 一致。
  - Python availability=`available`、freshness=`current`、connection=`unknown`。
  - Python semantic payload 不含 synthetic kanji / meaning / Today 原文。
- synthetic malformed parity：
  - 兩邊有效 word count 一致。
  - Python 額外標記 availability=`partial` 與 invalid-items limitation，不把 malformed source 當完整正常資料。
- `git diff --check`：通過。
- disposable `.validation-temp-kuro-core-parity`：finally 完整刪除。
- 測試前後 Git status 與 Git-visible file set hash 完全一致。

### Ownership 判定

目前仍是：

`Study producer -> study_snapshot.json -> Electron study-briefing.js -> Briefing/Today`

為 production legacy primary。

M1a 新路徑：

`synthetic / future Study snapshot -> kuro_core.study_adapter -> Observation`

目前僅為 shadow backend foundation，沒有被 Launcher、Core service、Qt、Electron 或 production DB 採用。因此：

- 不得宣稱 Study 已搬出 Electron。
- 不得刪 `study-briefing.js`。
- 不得用 M1a Observation 取代 Today item。
- 下一步必須先建立 read-only integration ingestion / shadow comparison boundary，再談 authoritative read cutover。


## M1b — Study read-only integration boundary

狀態：**完成 backend read boundary；尚未 production wiring / authoritative cutover。**

在既有 `kuro_core/study_adapter.py` 內補上 `study_snapshot_file_observation()`，沒有新增 manager/service。

責任限定為：

`configured local handoff file -> bounded read -> sanitized Observation`

不負責：

- Core persistence / `KuroCoreStore.ingest()`
- Today priority / attention decision
- Electron/Qt UI
- provider connection health
- Study progress algorithm
- fallback to legacy Briefing snapshot

### Read boundary

- 預設最大 snapshot 大小：2 MiB。
- hard cap：16 MiB。
- 先 stat、再 bounded read；race 後實際 bytes 仍再次檢查大小。
- missing file -> availability=`missing`。
- read failure -> availability=`offline`，connection 仍為 `unknown`。
- invalid UTF-8 / invalid JSON / non-object JSON / oversize -> availability=`partial`。
- error observation 不保存 path、raw payload 或私人文字。
- valid file 直接沿用 M1a `study_snapshot_observation()`，保持 timestamp/freshness/count semantics 單一路徑。

### 驗證

受控 `.validation-temp-kuro-core-m1b` 下執行：

- `test_kuro_core*.py`：**31 / 31 通過**。
- valid file read：確認不修改原檔。
- missing / invalid JSON / invalid UTF-8 / invalid shape / oversize / invalid max_bytes：全部有對應測試。
- `git diff --check`：通過。
- 測試前後 Git status 完全一致。
- working-tree file set 前後一致。
- disposable temp root 在 finally 完整刪除。
- 未讀正式 `local_state/core/work.sqlite3` 或 private Study snapshot。
- 未啟動 Launcher / Core service / Electron / Conversation / Bridge / provider，也未操作 Central Voice。

### 目前 ownership

production 仍是：

`Study producer -> private study_snapshot.json -> Electron study-briefing.js -> Briefing/Today`

新 backend path 目前只有：

`explicit path -> study_snapshot_file_observation() -> Observation`

沒有 scheduler、service、Qt、Electron、Core DB consumer，因此仍屬 **shadow-capable but not adopted**。

下一步 M1c 應先提供 read-only shadow reporting / comparison entry，讓同一份 Study handoff 能在不寫 DB 的前提下和 legacy path 做持續比較；完成 parity evidence 後才討論 authoritative read cutover。


## M1c — Study shadow report + live handoff parity

狀態：**完成 read-only shadow reporting 與真實 handoff parity；尚未 production adoption。**

M1c 直接擴充既有 `kuro_core/shadow_probe.py`，沒有新增 service。

新增：

- `build_study_shadow_report()`
- CLI `--study-snapshot <path>`
- CLI `--study-max-bytes`
- contract：`kuro.core.shadow.study.v1`

輸出只允許：

- availability / freshness / status / connection
- observedAt / validUntil
- limitationCount
- whitelist aggregate metrics：
  - snapshotPresent
  - schemaVersion
  - studyType
  - vocabTotal
  - vocabDue
  - vocabWithMistakes
  - todayReview
  - todayFocus
  - todayNew

不輸出 raw Study JSON、word、meaning、Today title/summary，也不寫 DB。

### M1c regression

受控 disposable TEMP 下：

- `test_kuro_core*.py`：**34 / 34 通過**。
- CLI smoke：Pet / Briefing 未啟動時，`--study-snapshot` 仍可直接完成，證明沒有 silent fallback 到 `:23567/briefing`。
- `git diff --check`：通過。
- 測試前後 Git status 完全一致（7 筆既有 working changes）。
- working-tree file set：153,258 -> 153,258，新增/移除 0。
- `.validation-temp-kuro-core-m1c` finally 完整刪除。

### 2026-10-07 真實 Study handoff 唯讀 parity

目標：
`Open-LLM-VTuber/private/study/study_snapshot.json`

只讀 metadata：
- exists = true
- size = 10,207 bytes
- filesystem last-write = 2026-05-31T21:35:35.2479246+08:00
- 驗證前後 metadata 不變

新 Python shadow contract：
- availability = `available`
- freshness / status = `stale / stale`
- connection = `unknown`
- observedAt = `2026-05-31T13:35:35Z`
- validUntil = `2026-05-31T14:35:35Z`
- limitationCount = 0
- vocabTotal = 11098
- vocabDue = 0
- vocabWithMistakes = 9
- todayReview = 0
- todayFocus = 8
- todayNew = 10

Electron legacy `normalizeStudySnapshot()` 對同一檔案：
- updatedAt = `2026-05-31T21:35:35+08:00`
- total / due / withMistakes = `11098 / 0 / 9`
- review / focus / new = `0 / 8 / 10`

結論：
- timestamp 是同一時間點（Electron 保留 +08:00；Python normalize 成 UTC）。
- 六組 aggregate counts 全部一致。
- 新 contract 額外明確表達 freshness / connection / availability；這些不是 legacy Electron normalizer 的欄位，不屬 parity mismatch。
- 目前真實 Study handoff 已經約四個多月未更新；新 path 正確把它判成 stale，而不是因檔案存在就判 current。
- 全程未輸出任何私人 Study item 原文、未寫 DB、未啟動 runtime、Git status 前後不變。

### M1 Study checkpoint

目前已成立：

`Study file -> bounded backend adapter -> privacy-bounded Observation -> read-only shadow report`

而且：
- synthetic Electron parity：PASS
- real handoff aggregate parity：PASS
- stale semantics：已驗證
- missing/partial/malformed semantics：tests 覆蓋

但 production 仍然是 Electron legacy primary；尚未有正式 service / scheduler / Qt consumer 採用新 Study observation。

因此 M1 Study foundation 可以進下一個階段，但**不能刪 `study-briefing.js`、不能宣稱 Study owner 已 cutover**。


## M1d reviewer checkpoint — ScheduleServer endpoint experiment

狀態：**實驗已拒絕並回退；不列入正式 migration path。**

曾嘗試把 read-only Study status endpoint 掛到既有 `:23569` `ScheduleServer`，功能測試本身通過，但 reviewer 判定 boundary 不合理：

- `ScheduleServer`、`CoreRuntime.ready()`、`RuntimeServices.md` 的 identity contract 目前都明確是 `kuro.core.schedule.v1`。
- 在沒有重新定義 Core API host contract 的情況下新增 `/v1/integrations/study`，會讓 Schedule owner 同時變成 generic integration gateway。
- `kuro_core_service.py` / `CoreRuntime` 當時也沒有傳入 Study snapshot path，因此該 route 尚未 production adopted，回退成本最低。

已執行：
- 恢復 `kuro_core/schedule_api.py` 到 HEAD。
- 恢復 `tests/test_schedule_api.py` 到 HEAD。
- 刪除 M1d 驗證留下的單一 `kuro_core/__pycache__/study_adapter.cpython-310.pyc`。
- 保留 M1a–M1c 的 `study_adapter.py`、`shadow_probe.py`、測試、architecture docs 與 migration docs。

回退後驗證：
- `test_kuro_core*.py`：**34 / 34 通過**。
- `test_schedule*.py`：**39 / 39 通過**。
- `git diff --check`：通過。
- disposable `.validation-temp-kuro-core-review`：已刪除。
- ignored pyc 測試前後沒有新增。
- 最終 Git status 不再包含 `schedule_api.py` / `test_schedule_api.py`。

### Reviewer 結論

M1 Study 目前停在合理邊界：

`Study handoff -> bounded adapter -> privacy-bounded Observation -> explicit shadow report`

這條可以保留。

下一步若要讓 Qt/正式 runtime consume Study，不應再直接擴寫 `ScheduleServer`。應先定義 **Core process 的 general read API hosting contract**，或在既有正式 owner 中找到可擴充的非-Schedule gateway；在那之前，Study 保持 shadow-only。

## M1e — General Core API host + Study integration boundary

狀態：**source-level implementation 與 targeted regression 完成；Study UI/Today consumer 尚未 cutover。**

### 實作

- `:23569` 現由 `CoreApplication` 組裝 `CoreApiServer`、`ScheduleCapability` 與 `IntegrationRegistry`。
- `CoreApiServer` 只負責 loopback listener、bearer auth、request parsing、route registry、HTTP error mapping；不持有 Study / Schedule domain logic。
- `ScheduleCapability` 保留 DB lease、schema bootstrap、ScheduleStore、materialization、notification 與 `/v1/schedule/*`；contract 維持 `kuro.core.schedule.v1` / schema 3。
- `IntegrationRegistry` 的 Study wrapper 只委派既有 `study_adapter.build_study_status()`；不 refresh、不寫 DB、不產生 Today item。
- process `/status` 改為 `kuro.core.api.v1`；Launcher 與 Electron main 再驗 `capabilities.schedule` 的 Schedule contract/schema。
- Electron renderer 的 Schedule status 仍由 main process 投影 today/timezone；renderer 沒有 arbitrary Core route，也沒有 bearer token。

### Study config / fail-closed

- Launcher settings 已加入 `core.integrations.study` 的 enabled/path/TTL/max-bytes。
- `enabled=true` 且 path 缺失/空白、unresolved variable、TTL/max-bytes 非 bounded integer 都直接拒絕。
- path 必須配置，但 handoff file 不必在 startup 存在；不存在時是 runtime `availability=missing`。
- 預設 `enabled=false`，因 Electron Briefing/Today 尚未完成 reader cutover。

### Reviewer 修正

1. **Confirmed defect**：strict query parser 對空 query 造成正常 `GET /status` 回 400；已改為只有非空 query 才 strict parse。
2. **Test isolation defect**：Core host test 原本依賴 sibling test fixture 的 discovery side effect；已改成 test-local synthetic fixture。
3. Codex sandbox 無法覆寫部分既有 config/Electron/docs；未改 ACL，由 Project Workspace 以 guarded SHA patch 補齊。失敗施工檔 `kuro_launcher/config.py.m1e-edit` 與 validation temp 已精確清除。

### Boundary review

- `api_server.py` 不 import `study_adapter` / `schedule_store`。
- `schedule_api.py` 不 import Study integration。
- `integrations.py` 不依賴 ScheduleStore / Schedule API。
- tests 已無 `ScheduleServer` production construction。
- 沒有新增第二個 Core process/port，也沒有保留舊 ScheduleServer production fallback。

### 驗證

- Core host targeted：**20 / 20 PASS**。
- `test_kuro_core*.py`：**54 / 54 PASS**。
- `test_schedule*.py`：**40 / 40 PASS**。
- `node --test tests/core_client.test.cjs`：**4 / 4 PASS**。
- `git diff --check`：PASS（只有既有 line-ending warning）。
- disposable temp 已刪除；Git status/file set 測試前後一致；新增 ignored pyc/temp = **0**。
- 全部使用 synthetic / disposable DB 與 synthetic/missing Study handoff；未讀寫正式 Core DB、未啟動正式 Kuro stack、未操作 Central Voice。

### 結論與下一 gate

目前可確認 general Core host、Schedule capability boundary、read-only Study integration source path 已成立；但不能宣稱目前桌面常駐 process 已重新載入 working tree，也不能宣稱 Study 已取代 Electron Briefing/Today。

下一步應做 Study consumer cutover contract / parity：先讓 Qt 或 future Today consumer 讀 Core status，與 Electron legacy reader 比對 freshness/missing/timezone/user-visible semantics，再單次切 reader；consumer inventory 歸零後才刪 `study-briefing.js`。Mail / Today / Task / Attention 保持後續獨立 milestones。

## M1f adoption gap 修正與驗證（2026-10-08）

狀態：**source-level adoption 與 synthetic regression 通過；正式 runtime / Electron Mail / Today / Briefing / Qt consumer 未 cutover。**

- settings 新增 Mail block：預設 enabled=false、status_path=`${open_llm_vtuber_dir}/private/gmail/mail_status.json`、TTL 1800、max bytes 65536。
- CoreRuntime 驗證 explicit absolute path、bounded integer TTL/max 後傳入四個 Mail CLI flags；handoff file 不存在仍可啟動，route 回 missing。
- Electron child_environment 的 KURO_MAIL_STATUS_FILE 與 Core CLI 使用同一 resolved config path；disabled 不注入 env、不傳 Mail CLI、不註冊 Mail route。Registry configured 維持排序為 ["mail", "study"]。
- mail_update_briefing 的 provider MailAuthError 寫 auth_required，其他 failure 寫 provider_error；不寫 raw exception，保留 last-good counts/time，dashboard failure 不覆寫 provider success。
- Windows sharing/access/busy 衝突：writer atomic replace 與 domain-neutral reader 各有 0.5 秒 monotonic retry 上限；逾時仍 fail closed。保留同目錄 temp、writer lock/ordering，不 unlink target、不 truncate overwrite；reader 不寫檔。
- Concurrency test 使用 production read_json_handoff，要求每次成功讀取都是有效 dict/schema，且沒有 handoff error；deterministic tests 覆蓋 retry、timeout、nonretryable error。

驗證使用 `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p <pattern>`：

| Pattern / 命令 | 結果 |
| --- | --- |
| test_mail_status_handoff.py | 16/16 PASS |
| test_kuro_core_mail_adapter.py | 12/12 PASS |
| test_kuro_core_study_adapter.py | 15/15 PASS |
| test_schedule_runtime.py | 8/8 PASS |
| test_kuro_core*.py | 66/66 PASS |
| test_schedule*.py | 43/43 PASS |
| node --test tests/core_client.test.cjs | 4/4 PASS |
| in-memory Python compile | 7 files PASS |
| git diff --check | PASS |

Targeted adapter/runtime tests 已包含於對應 regression suite，不重複計入總數。所有 Python 測試使用 PYTHONDONTWRITEBYTECODE=1，TEMP/TMP 指向 disposable repo-local directory；測試前後 Git status 與 ignored pyc/tmp file set 一致，temp 已清除。

未讀真 Gmail、OAuth token、正式 handoff、briefing-store 或正式 Core DB，未啟動正式 stack，未改 ACL、commit/push。保留 M1e host 與既有 M1f producer/adapter/registry/CLI；Mail poller/preferences/rules/message detail/daily_brief live fallback 及 Today/Briefing/Qt ownership 不變，未新增第二個 provider client、poller、正式 process 或 port。

下一 gate 為獨立的正式 runtime adoption / consumer parity；本次證據不代表桌面常駐 process 已載入變更，也不代表 Mail/Today migration 完成。

