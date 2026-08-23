# Kuro OMI Briefing

## Goal

- 讓 Kuro 能穩定消費 OMI 的 `omi.ai.ask.v2` 結果，並轉成 Briefing、Reader、任務牆、對話與語音播報。
- Kuro 必須保留 OMI 的市場結論、data limits、freshness、warnings、tool evidence 與 target resolution，不重新做市場分析。
- 讓使用者可以透過 Kuro 問「今天市場要注意什麼」、「這檔股票怎麼看」、「自選股有什麼風險」，並得到可展示、可聽、可追蹤的工作助理輸出。

## Non-goals

- 不在 Kuro 實作股票技術分析、資料 freshness 判斷、外部市場 API orchestration 或交易決策邏輯。
- 不把 OMI 結果寫入 Kuro 長期記憶，除非經過 memory policy 與可審計流程。
- 不讓角色 prompt 補完 OMI 缺失、隱藏 stale/partial/provider failure，或把不完整資料講成確定結論。
- 不在本任務處理 mail/Gmail briefing 的功能擴張；mail 只作為 shared dashboard snapshot 的參考模式。
- 不改動 runtime code，直到 baseline contract 與測試面確認。

## Hard constraints

- Repo: `C:\project\kuro`
- OMI repo: `C:\project\Open Market Intelligence`
- Kuro 是 OMI 的下游 consumer；市場資料、freshness、tool orchestration、AI decision core 真相來源在 OMI backend。
- Kuro default OMI payload 必須保持 read-only:
  - `contract_version=omi.ai.ask.v2`
  - `target={type:auto}`
  - `caller_profile=kuro_readonly`
  - `allow_write=false`
  - bounded `tool_budget`
- Kuro 可允許 `allow_external_fetch=true`，但外部資料補齊必須由 OMI backend allowlisted tools 執行。
- Kuro 必須保留 OMI 回傳的 `missing`、`warnings`、`freshness`、`tool_plan`、`tool_runs`、`evidence_passport`。
- Briefing / Reader / spoken output 不得重組出與 OMI 相反的市場判斷。

## Context

- OMI preflight builder:
  - `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/market_preflight.py`
  - Builds `omi.ai.ask.v2` envelope with `allow_llm=true`, `allow_write=false`, `allow_external_fetch=true`, bounded `tool_budget`.
- OMI preflight caller:
  - `Open-LLM-VTuber/src/open_llm_vtuber/agent/agents/basic_memory_agent.py`
  - Uses `should_autorun_omi(route)`, streams `omi.ask_stream`, falls back to `omi.ask`, stores `_last_omi_resolution` for follow-up context.
- Tool routing / policy:
  - `Open-LLM-VTuber/tool_catalog.json`
  - `Open-LLM-VTuber/tool_policy.json`
  - `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_policy_manager.py`
- Briefing surface:
  - `pet-electron/src/main-process/briefing-store.js`
  - `pet-electron/src/briefing-window.html`
  - `pet-electron/src/briefing-preload.js`
- Reader surface:
  - `pet-electron/src/reader-window.html`
  - `pet-electron/src/reader-preload.js`
- Relevant tests:
  - `Open-LLM-VTuber/tests/test_market_preflight.py`
  - `Open-LLM-VTuber/tests/test_tool_policy_omi.py`
  - `Open-LLM-VTuber/tests/test_tool_catalog_market_routing.py`

## Deliverables

- A Kuro-side OMI briefing contract map that defines how OMI fields become:
  - conversation context
  - Briefing cards/modules
  - Reader long-form view
  - spoken summary
  - task-wall/action items
- A baseline gaps list covering Kuro OMI preflight, route selection, transport fallback, last resolution, and OMI backend URL config.
- Focused future implementation plan for:
  - OMI result normalization in Kuro
  - preservation of warnings/data limits
  - spoken rendering rules
  - Briefing snapshot integration
  - runtime smoke tests
- Updated `Progress.md` after each milestone.

## Done criteria

- Kuro can ask OMI for a market/stock/watchlist answer and display a concise briefing without losing OMI warnings or data limits.
- Kuro can speak a short, role-appropriate summary that does not read raw JSON or overstate confidence.
- Kuro can show OMI target, as-of date, data limits, and tool evidence in UI or debug surfaces.
- Follow-up turns reuse OMI resolution when appropriate without Kuro parsing stocks itself.
- OMI transport failure surfaces as a tool error/status update, not an endless thinking state.
- Default Kuro OMI connection points to the current OMI backend port strategy, not stale `8300`.

## Open questions / assumptions

- Assumption: Kuro should wait for OMI decision contract stabilization before implementing richer market briefing cards.
- Assumption: first Kuro pass should target local OMI on `127.0.0.1:8400`, but the code should remain env-driven.
- Open question: whether OMI market results should be stored only in short-term conversation/tool history or also as reviewable briefing snapshots.
