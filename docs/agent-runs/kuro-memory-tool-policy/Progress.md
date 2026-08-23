# Progress

## Status

- Current phase: planning scaffold
- Last updated: 2026-06-21 20:20 +08:00

## Completed

- Read Kuro repo-level `AGENTS.md`.
- Inspected current tool policy and catalog:
  - `Open-LLM-VTuber/tool_policy.json`
  - `Open-LLM-VTuber/tool_catalog.json`
  - `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_policy_manager.py`
- Inspected memory-related entries:
  - `Open-LLM-VTuber/src/open_llm_vtuber/character_memory_manager.py`
  - `kuro_launcher/memory_support.py`
  - `kuro_launcher/memory_panel.py`
- Inspected Briefing snapshot entry:
  - `pet-electron/src/main-process/briefing-store.js`
- Inspected representative tests:
  - `Open-LLM-VTuber/tests/test_tool_policy_omi.py`
  - `Open-LLM-VTuber/tests/test_character_memory_manager.py`
- Created task docs:
  - `docs/agent-runs/kuro-memory-tool-policy/Prompt.md`
  - `docs/agent-runs/kuro-memory-tool-policy/Plan.md`
  - `docs/agent-runs/kuro-memory-tool-policy/Progress.md`

## Validation evidence

- Static inspection confirms `ToolPolicy.check()` blocks unregistered tools, disabled tools, confirmation-required mode, denied args, denied values, nested numeric limits, denied paths, and private/internal URLs.
- Static inspection confirms current OMI policy blocks `allow_write=true`, blocks `mode=report`, and caps nested `tool_budget` values.
- Static inspection confirms character memory has explicit scope/type/status models including `pending_confirmation` and `pending_delete`.

## Decisions made

- Do not change runtime policy or memory behavior during this planning pass.
- Treat high-risk actions as confirmation-required until a real confirmation and audit flow exists.
- Keep tool result, briefing snapshot, and long-term memory as separate concepts.

## Known issues / risks

- There is no completed unified confirmation queue documented yet for memory candidates and tool actions.
- `tool_policy.json` can block execution, but user-facing confirmation UX still needs a product design pass.
- Memory DB and private runtime state must remain local and ignored; future validation must check git status before commit/push.

## Next step

- Begin Milestone 1 by running tool policy and character memory manager tests, then update this file with actual pass/fail results.
