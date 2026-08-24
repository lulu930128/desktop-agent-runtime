# Plan

## Milestones

1. Baseline、Roadmap 與 shadow contract spine
   - Scope: `docs/product/Roadmap.md`、本任務文件、`kuro_core/` observation／freshness／SQLite／trace、targeted tests。
   - Acceptance: connection、availability、freshness 可分別表達；current 有 bounded validity；duplicate ingest exactly-once；decision trace 不保存 raw prompt。
   - Validation: `.\envs\kuro-llm310\python.exe -m unittest tests.test_kuro_core_contracts tests.test_kuro_core_store`

2. Legacy source-health shadow ingestion
   - Scope: Electron Briefing source status 的 read-only adapter、shadow runner、aggregate comparison report；不讀取或保存 message body。
   - Acceptance: mail／study 現有 source status 可轉為 Core observation；舊資料即使 connection connected 也能在 TTL 後顯示 stale。
   - Validation: synthetic fixture tests，加上一份不落盤的 live aggregate shadow probe。

3. Task 與 Attention authoritative contract
   - Scope: Task Store、Attention Event、dedup、cooldown、quiet hours、priority reason、materialized Today view。
   - Acceptance: Electron 不再擁有正式 Today priority；rule、domain severity、user override 與 AI suggestion 保留各自來源。
   - Validation: schema／migration／idempotency／concurrency tests，legacy-vs-Core shadow comparison。

4. AI Manager context compiler 與 replay lab
   - Scope: bounded Core context、model adapter input、decision trace、feedback event、offline replay runner。
   - Acceptance: 可在相同 observation set 比較 rule-only、現行模型、替代模型與 hybrid ranking，不觸發外部 side effect。
   - Validation: deterministic replay fixtures、repeat-run consistency 與 private-payload audit。

5. Action／Policy／Confirmation／Audit
   - Scope: action request、payload digest、policy decision、confirmation queue、execution state、audit、unknown-result reconciliation。
   - Acceptance: write／send／delete／publish／high quota 維持 confirm 或 disabled；確認只綁定同一 payload；重試不造成重複 side effect。
   - Validation: allow／deny／confirm／quota／cancel／timeout／duplicate／unknown result targeted tests。

6. Runtime adoption 與 Work Panel cutover
   - Scope: Launcher lifecycle、loopback API、Electron main consumer、Open-LLM-VTuber read/action-request client、legacy rollback。
   - Acceptance: Kuro Core 成為唯一 task／attention／policy／action truth；LLM、TTS 或 Live2D 失效時 Work Panel 仍可讀。
   - Validation: Q3 exact-runtime probes、restart／crash recovery、Q4 screenshot 與代表性使用流程。

7. Proactive assistance 與 embodied attention experiments
   - Scope: notification policy、channel selection、Pet／voice short overview、user feedback 與 longitudinal metrics。
   - Acceptance: 能量測 helpful intervention、dismissal、duplicate、missed critical event、time-to-action 與 interruption burden。
   - Validation: replay baseline、受控日常試用與可匯出的去敏 aggregate report。

## Stop-and-fix rules

- 若新 Core 隱藏 stale、partial、missing、offline、auth_required 或 unknown，先修正 contract，不進行 UI cutover。
- 若 observation 沒有 source time、bounded validity 或 idempotency key，不得標示 current 或寫入 authoritative store。
- 若 legacy 與 Core 結果不一致且無法解釋，維持 legacy primary，記錄差異並停止切換。
- 若 trace 或 audit 可能保存 token、完整 mail、private attachment、raw market/account payload、chat 或 memory，停止寫入並縮小 schema。
- 若 AI output 直接改寫 task、policy 或 action result，退回 candidate／request contract。
- 若 side effect 缺少 confirmation binding、idempotency、quota、audit 或 reconciliation，不得從 confirm 升級。
- 若 migration、concurrency、restart 或 recovery 測試失敗，先修正再進下一個 milestone。

## Decisions

- 2026-08-23：使用者確認把 Kuro 長期發展定位為正式長專案，研究主軸是可信長期狀態、主動注意力、安全行動與 model-agnostic 架構。
- 2026-08-23：第一版採 shadow-only logical Core，不立刻新增 live process 或切換 UI owner，以降低 runtime regression。
- 2026-08-23：availability、freshness、connection 採正交欄位；對外再投影為 current／stale／partial／missing／offline／auth_required／unknown。
- 2026-08-23：SQLite 是 v0 local persistence，不是永遠不可替換的產品介面；跨元件依賴 contract，不依賴 DB table。
- 2026-08-24：Milestone 2 前先處理使用者可見的桌寵 input safety 與角色交接可靠性；全螢幕透明 host 不得因關閉全穿透而攔截整個桌面，profile apply 必須可復原並顯示真實進度。
- 2026-08-24：桌寵模式的 focusability、topmost level、workspace visibility 與 show 後 Z-order 重申收斂為單一政策；多螢幕透明 host 不得在一般視窗取得焦點後掉到非 topmost 層。
