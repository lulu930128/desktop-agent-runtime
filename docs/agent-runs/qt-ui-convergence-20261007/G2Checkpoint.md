# G2 — Backend owner cutover checkpoint

日期：2026-10-09
狀態：**G2 source/backend owner ready；production runtime/UI adoption 未驗收；G3 已完成 source-ready；G4 尚未開始。**

## 已完成

- Study concrete actionable evidence：`study_work_adapter.py` 從既有 Study snapshot 的 explicit today word/item ids 建立 bounded `SourceEvidence`；aggregate counts 不產 task。
- Mail concrete actionable evidence：既有 `mail_update_briefing()` 同一次 provider fetch 寫 status handoff + bounded `mail_work.json`，provider failure保留 last-good work；work handoff 不含 body/snippet/attachment content/token/OAuth。
- Core `mail_work_adapter.py` / `study_work_adapter.py` 只讀 bounded handoff，不呼叫 provider、不寫 DB。
- `TodayCapability` 成為 canonical backend Today composition，註冊 `GET /v1/today`，回 `kuro.core.today.v1`；GET pure read，不 refresh、不 persistence。
- Core `/status` 的 capabilities 包含 Today contract/configured sources，不綁 Schedule schema。
- Mail poller lifecycle owner 移到 Launcher `MailPollerRuntime`，spawn 既有 `mail_briefing_poller.py`；exact child handle/PID，disabled 不啟動。
- Electron `mail-briefing-service.js` 在 `KURO_MAIL_POLLER_OWNER=launcher` 時不再 start/restart long-running poller；manual refresh/detail/preferences/rules compatibility 暫時保留到 Qt cutover。
- Launcher config/runtime 使用單一 canonical Mail status/work paths，Core CLI與producer env共用 resolved paths；inherited handoff env先清除。

## Ownership

- Gmail/provider truth：既有 local_mcp / Gmail。
- Study truth：external Study system。
- Today backend truth：Core `TodayCapability`。
- Mail poller lifecycle：Launcher。
- Electron Today/Briefing/Work Panel：仍是 legacy display/compat consumer，尚未 physical delete。

## 驗證

G2 Codex full regression：
- Python **213/213 PASS**（15 suites）。
- Core **137**（含 G1 53、G2 16、Mail adapter 13、Study adapter 16）。
- Schedule **44**。
- Mail status **16**。
- Mail work handoff **7**。
- Mail poller **9**。
- Node core-client **4/4 PASS**。
- `git diff --check` PASS。
- integrity/temp cleanup PASS。

早期獨立 `mail_poller_owner` validator 曾因 Windows temp directory EPERM 而未進入 assertion；後續 G3 全 Node suite `tests/*.test.cjs` / `tests/*.test.mjs` **80/80 PASS**，包含現有 `mail_poller_owner.test.cjs`，且 G3 未回退 G2 owner source。現行 source亦明確有 `KURO_MAIL_POLLER_OWNER === "launcher"`、`pollerOwner` status 與 `canonicalOwner` no-spawn guard。

## 未做

- 未驗收正式常駐 Core/Launcher/Electron 採用 working tree。
- 未移除 legacy Briefing/Today JS。
- 未完成 Qt Today/Schedule/Settings feature parity。
- 未完成 desktop startup/tray/notification owner cutover。

**G2 可視為 source/backend owner DONE；G3 已另有 `G3Checkpoint.md`。下一 Gate = G4 Qt feature parity。**
