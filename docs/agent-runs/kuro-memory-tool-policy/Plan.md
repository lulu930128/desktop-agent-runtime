# Plan

## Milestones

1. Baseline current policy and memory surfaces
   - Scope: `tool_policy.json`, `tool_policy_manager.py`, `tool_catalog.json`, `character_memory_manager.py`, `kuro_launcher/memory_support.py`, `memory_panel.py`, `briefing-store.js`.
   - Acceptance: Document current allowed/blocked tools, memory types/scopes/statuses, and UI-visible review states.
   - Validation: `.\envs\kuro-llm310\python.exe -m unittest Open-LLM-VTuber.tests.test_tool_policy_omi Open-LLM-VTuber.tests.test_character_memory_manager`

2. Define confirmation-required action matrix
   - Scope: policy docs first; runtime confirmation flow later.
   - Acceptance: Every action category has one status: automatic, local snapshot, needs confirmation, or blocked.
   - Validation: Review against Kuro `AGENTS.md` Tool Policy section.

3. Design memory candidate lifecycle
   - Scope: memory manager/repository/launcher panel/Briefing candidate modules.
   - Acceptance: Memory writes move through candidate/review states unless explicitly approved.
   - Validation: Add tests or fixtures for `pending_confirmation`, `active`, `superseded`, `disabled`, and `pending_delete`.

4. Harden tool policy tests
   - Scope: `tool_policy_manager.py`, `tool_policy.json`, policy tests.
   - Acceptance: Tests cover deny truthy args, deny values, nested numeric max args, path/url blocking, unknown tools, and confirmation-required mode.
   - Validation: targeted unittest for policy manager and OMI policy.

5. Integrate confirmation UI / UX plan
   - Scope: launcher memory panel, Briefing candidate modules, possible future tool action queue.
   - Acceptance: User can inspect source, action type, risk, proposed write/delete, and approve/reject without digging into private files.
   - Validation: UI smoke or screenshot-backed check when implementation begins.

6. Runtime audit trail
   - Scope: local records/logs only; no private data in git.
   - Acceptance: High-risk attempts record blocked/confirmed status with enough context to debug, without leaking secrets.
   - Validation: local smoke with blocked tool attempt and memory candidate review.

## Stop-and-fix rules

- If a tool action can send, publish, delete, write outside a bounded local snapshot, or consume large quota without confirmation, stop and tighten policy.
- If a memory write can happen silently from a tool result or daily briefing, stop and route it to candidate review.
- If policy changes require adding secrets or private state to git, reject that approach.
- If frontend/launcher UI tries to bypass runtime policy, move the guard back to execution policy.
- If OMI market gaps are being patched by Kuro memory or prompt text, stop and route the fix to OMI.

## Decisions

- 2026-06-21: Keep tool policy conservative. Current allowed path is read-only/status/local presentation updates plus bounded OMI analysis; writes/deletes/sends/publishes/large quota need confirmation.
- 2026-06-21: Treat `tool_policy.json` as execution guard, not as natural-language refusal policy.
- 2026-06-21: Treat memory and briefing snapshots as separate surfaces; snapshots can be transient and source-backed, while long-term memory must be reviewable and editable.
