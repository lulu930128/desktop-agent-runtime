# Plan

## Milestones

1. Baseline current Kuro OMI flow
   - Scope: `market_preflight.py`, `basic_memory_agent.py`, `tool_catalog.json`, `tool_policy.json`, OMI-related tests.
   - Acceptance: Document how OMI route selection, payload generation, streaming, fallback, final formatting, and `_last_omi_resolution` work today.
   - Validation: `.\envs\kuro-llm310\python.exe -m unittest Open-LLM-VTuber.tests.test_market_preflight Open-LLM-VTuber.tests.test_tool_policy_omi`

2. Define Kuro OMI briefing contract
   - Scope: planning/documentation only first; no runtime code changes.
   - Acceptance: Map OMI response fields to Kuro surfaces: conversation, Briefing, Reader, spoken output, task-wall.
   - Validation: Review against OMI `ContractMap.md` in `C:\project\Open Market Intelligence`.

3. Align OMI runtime configuration
   - Scope: `market_preflight.py`, launcher/runtime config, README/docs.
   - Acceptance: Kuro OMI default no longer relies on stale `8300`; connection remains env-driven and compatible with local trust token setup.
   - Validation: Unit test for default/fallback URL plus runtime smoke when OMI is running.

4. Preserve warnings and data limits in presentation
   - Scope: Kuro formatting helpers, Briefing store integration, spoken rendering rules.
   - Acceptance: `missing`, `warnings`, `freshness`, `tool_runs`, and `evidence_passport` survive transformation into Kuro surfaces.
   - Validation: Add fixtures to `test_market_preflight.py` and future Briefing formatter tests.

5. Add display/spoken output rules
   - Scope: Reader/Briefing/spoken transformation layer, not OMI analysis.
   - Acceptance: Short spoken output names conclusion, confidence/data limits, and one action; Reader/Briefing can show details.
   - Validation: Syntax checks and focused snapshot/string tests.

6. Runtime smoke
   - Scope: local Kuro + local OMI.
   - Acceptance: A stock/market question triggers OMI, returns a final result or visible tool error, and does not strand the conversation.
   - Validation:
     - `Invoke-RestMethod http://127.0.0.1:23567/status`
     - OMI backend health on `127.0.0.1:8400`
     - One Kuro conversation-level smoke test or captured tool event trace.

## Stop-and-fix rules

- If OMI response lacks freshness/data-limit metadata, stop and fix OMI contract first instead of patching Kuro wording.
- If Kuro starts parsing stock symbols or producing market conclusions locally, revert to OMI-owned logic.
- If OMI transport fails, convert it to a visible tool status/error and continue the conversation; do not leave the assistant thinking indefinitely.
- If presentation hides stale/partial/provider failure, the milestone is not complete.
- If implementation would write memory, send content, publish, or exceed bounded quota, stop and require confirmation.

## Decisions

- 2026-06-21: Kuro OMI briefing is downstream of OMI AI decision core. Kuro task starts as planning only until OMI contract map and baseline tests are ready.
- 2026-06-21: Kuro should keep `target={type:auto}` and pass context/resolution to OMI rather than parsing market targets locally.
- 2026-06-21: Current `market_preflight.py` fallback `8300` is a known gap to fix later, not changed in this documentation-only pass.
