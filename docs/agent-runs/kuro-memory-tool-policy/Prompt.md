# Kuro Memory And Tool Policy

## Goal

- 將 Kuro 的工具權限、記憶寫入、記憶刪改、Briefing snapshot、tool result 與使用者確認流程整理成可長期維護的政策與實作計畫。
- 讓 Kuro 可以更積極地協助工作，但不因角色 prompt 或臨時指令繞過安全邊界。
- 建立可審計、可修改、可刪除的 memory lifecycle，避免每日 briefing、工具結果或暫時市場狀態污染長期角色記憶。

## Non-goals

- 不在本任務放寬所有工具權限。
- 不把 tool policy 做成一般回答拒絕規則；它是 execution boundary。
- 不把 private runtime state、chat history、memory DB、secrets、tokens、voice references 或模型權重放進 git。
- 不在 planning pass 修改 runtime code、資料庫、記憶檔或工具執行邏輯。
- 不處理 OMI 市場分析本身；OMI market reasoning 屬於 OMI repo。

## Hard constraints

- Repo: `C:\project\kuro`
- Tool policy source:
  - `Open-LLM-VTuber/tool_policy.json`
  - `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_policy_manager.py`
- Tool routing source:
  - `Open-LLM-VTuber/tool_catalog.json`
  - `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_catalog_manager.py`
- Memory source:
  - `Open-LLM-VTuber/src/open_llm_vtuber/character_memory_manager.py`
  - `Open-LLM-VTuber/src/open_llm_vtuber/character_memory_repository.py`
  - `Open-LLM-VTuber/src/open_llm_vtuber/character_memory_retriever.py`
  - `kuro_launcher/memory_support.py`
  - `kuro_launcher/memory_panel.py`
- Briefing snapshot source:
  - `pet-electron/src/main-process/briefing-store.js`
- Current default:
  - Read/status operations may be automatic.
  - Write/delete/send/publish/repo changes/large quota must require confirmation.
  - OMI read-only analysis with bounded external refresh is allowed by policy; persisted report/write remains blocked.

## Policy Model

### Automatic by default

- Read-only local status checks.
- OMI read-only `omi.ask` / `omi.ask_stream` with bounded `tool_budget`.
- Dashboard / Briefing / Reader display updates that only modify local presentation state.
- Mail daily brief snapshot reads when Gmail auth is already configured and policy permits.
- Summaries, classifications, formatting, and transient conversation context.

### Requires confirmation

- Writing long-term memory.
- Deleting, disabling, superseding, or bulk-editing memory.
- Sending email/message/social content.
- Publishing content or external posts.
- Modifying repo, committing, pushing, changing startup shortcuts, or changing system settings.
- Long-running jobs, large external API refresh, paid quota, or persistent report generation.
- Any action that changes user data outside a clearly bounded local snapshot.

### Block by default

- Secrets/token/cookie reads or writes.
- Private browser profile/cookie access.
- Silent data deletion.
- Tool calls not registered in `tool_policy.json`.
- Internal/private URLs through public web fetch tools.
- `omi.ask` with `allow_write=true`.
- `omi.ask` with `mode=report`.
- OMI tool budgets above policy caps.

## Memory Model

Kuro memory should be split by purpose:

- `global_user`
  - Stable user preferences, identity, broad work habits.
- `character`
  - Character-specific tone/persona/interaction preferences.
- `project`
  - Project decisions and durable project state.
- `thread`
  - Conversation summaries and follow-up context.
- `runtime`
  - Temporary session/runtime state; should not become durable memory by default.

Memory types:

- `preference`
- `instruction`
- `boundary`
- `identity`
- `fact`
- `project_decision`
- `project_state`
- `thread_summary`

Memory statuses:

- `active`
- `superseded`
- `disabled`
- `pending_confirmation`
- `pending_delete`

Hard rule:

- Tool results, OMI market state, daily briefing, transient mail/news, and one-off summaries should become reviewable candidates or snapshots first, not automatic long-term character memory.

## Deliverables

- A baseline policy map for current tools and memory states.
- A future confirmation flow design for memory writes/deletes and higher-risk tool calls.
- A reviewable memory candidate lifecycle.
- Tests or smoke checks that verify:
  - blocked tool calls stay blocked
  - bounded OMI calls stay allowed
  - over-budget OMI calls are blocked
  - memory writes do not occur silently
  - pending delete/disable states are visible to UI
- Documentation updates only after code behavior exists.

## Done criteria

- Kuro can clearly tell which actions are read-only, local snapshot updates, confirmation-required, or blocked.
- Memory candidates can be reviewed, accepted, rejected, disabled, or marked pending delete without losing audit context.
- Tool policy blocks unregistered/high-risk/over-budget actions before execution.
- Character/persona prompt cannot override execution policy.
- Briefing and tool results do not silently become long-term memory.
- Tests cover OMI policy and representative memory lifecycle behavior.

## Open questions / assumptions

- Assumption: current policy should remain conservative until audit UI and confirmation flow are implemented.
- Assumption: local Briefing snapshot updates are lower risk than external writes, but still need provenance.
- Open question: whether Kuro should expose one unified confirmation queue for both memory candidates and tool actions, or keep separate queues.
