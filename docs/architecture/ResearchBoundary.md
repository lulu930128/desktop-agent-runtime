# 研究與正式 runtime 邊界

本規範供後續 Prompt Injection／MCP Security 研究使用。本輪只完成本 repo 的責任收斂與隔離規範；依使用者選擇，沒有建立外部研究集中區、experiment worktree 或執行攻擊實驗。

## 研究 target 與正式 owner

主要受測區為 `Open-LLM-VTuber/src/open_llm_vtuber/conversations/`、`agent/`、`mcpp/`；Observation／DecisionTrace 可作輔助紀錄。這些 MCP／agent 檔案也是 production source，修改實驗應在獨立 worktree／隔離 harness 中進行。

Launcher、Electron、Reader／Work Panel、Live2D、Bridge 與 Central Voice 是 interaction／harness 邊界，不是第一版防禦算法的 owner。不要新建平行 executor、把 defense 塞入 persona、讓 tool result 批准操作，或把外部 OMI／mail／study truth 複製到展示層。

## Worktree 不等於 runtime 隔離

正式 checkout 與 research branch 各有 source 目錄，但仍可能共用 env、absolute paths、使用者目錄、ports、帳號與外部服務。Junction 也不提供唯讀保護；透過 junction 編輯仍會改到目標，不能作為隔離方法。

目前 Launcher 還有固定 `Local\KuroDesktopAgentLauncher` mutex 與 `Local\KuroDesktopAgentWorkPanelActivate` event；另一個 worktree 直接啟動可能喚回正式面板。Electron 使用 `app.getPath("userData")`，也不隨 Git worktree 自動分離。本 repo 尚無完整可並行啟動的 research profile。

後續建立 research worktree 時，先記錄 production checkpoint SHA，再建立專用 branch（例如 `codex/research-r001-agent-injection`）；branch／路徑由當次任務決定，不覆用 main 的 dirty diff。預設先使用單元／replay harness＋fake tools，完成下表隔離前不要直接執行 `桌寵啟動器.vbs`、Launcher 或 `npm start`。

| 資源 | 啟動任何實驗前必須確認 |
| --- | --- |
| Source／imports | commit SHA、dirty patch digest、實際 interpreter／依賴版本與 module root 都指向 experiment checkout |
| Settings | Launcher 讀 repo 內 `kuro_launcher.settings.yaml`；展開 `${HERE}`／`${ROOT}` 並檢查 absolute values；不假設忽略的 `.local.yaml` 會自動載入 |
| Core DB | 使用 experiment 專屬空 DB 或 synthetic fixture；resolve／reparse 後不得等同正式 `local_state/core/work.sqlite3` 或其 hardlink／junction target |
| 其他 private state | Chat history、memory、index、logs、generated conf、Electron userData、mail preferences／rules、study snapshot 全部獨立；不複製正式私人內容作 dataset |
| Ports／IPC | 實驗 ports、mutex／activation event 與 app identity 獨立；確認 listener owner，不向正式 `23567/23568/23569` fallback |
| Tokens／credentials | 新 session tokens，只在隔離程序間傳遞；清除繼承的 production endpoints／credential env；只接 fake／synthetic tools |
| 外部 side effect | Mail poller、refresh、notification、TTS、LLM quota 等預設關閉或 fake；bounded live 研究需另外明確授權 scope／budget |
| Shared services | 不停止中央 Voice／其他 consumer-owned service；語音研究若需專屬 engine，先由中央 owner 定義隔離方案 |
| Cleanup | 只釋放實驗 owned handles／ports／DB；保存審查過的結果，不以全機 kill／reset／clean 清場 |

`KuroCoreStore` 接受任意 DB path，沒有內建 production-path deny guard；ScheduleServer lease 也不阻止直接 SQLite writer。此表是必須由研究 harness 落實並驗證的前置 contract，不能宣稱本輪已做自動 enforcement。[CorePersistence](CorePersistence.md)列出共享 migration 風險。

## 可重現的 baseline

來源 baseline 應保存已提交 checkpoint 的檔案 hash、policy version／configured digest 與驗證範圍。它不含 private config／資料，不代表 runtime discovery 或 A8 已完成。

本輪 [SourceBaseline.json](../agent-runs/architecture-convergence-20260921/SourceBaseline.json) 固定於架構 checkpoint `bde3444`：14 個 Git blob SHA-256、11 個 source／test／architecture tree OID 與 configured policy v1 digest。它是日期性來源快照；後續實驗需另記當次 runtime／effective config／discovery，不沿用為 live 結果。

每個實驗至少記錄下列欄位；未取得的 evidence 明確標 `not_observed`，不能填成空 inventory 或成功：

| 項目 | 要記錄的內容 |
| --- | --- |
| Runtime | source commit、dirty patch hash、entrypoint、interpreter／SDK／provider profile、實際 module root、開始／結束時間 |
| Config | 去 secrets 後的 effective config digest、模型與 sampling parameters、timezone、isolated state／port manifest |
| Policy | policy version、配置來源檔案 SHA-256、runtime effective policy digest；`ToolPolicy.digest` 與檔案 hash 分列 |
| Tool inventory | 每個 server 的 discovery completeness／failure／cache state、canonical tool ID、wire name／alias、raw input/output schema digest、provider projection profile |
| Dataset | corpus version／SHA-256、來源與使用權限、synthetic／redacted 分類、train/eval split、case ID、attack family |
| Defense | intervention version／commit、policy delta、處理位置、control arm；不能同時偷換模型或工具集合 |
| Execution | run ID／seed／repeat、case outcome、實際允許／拒絕／unknown tool call、side effects、timeout／cancel、耗時與 budget |
| Result | ASR 定義與分母、有效樣本／失敗／skipped、benign utility／false refusal、結果檔 hash、失敗分類與限制 |

Raw schema digest 應使用既有 `tool_schema.schema_digest` 語意；不能拿 `tool_schema.py` 的 source SHA-256 當作 runtime schema digest。記錄 discovery 完成狀態後才能比較工具 inventory；宣告的 `tool_catalog.json` 不代表真實 server 已提供全部工具。

最小可填寫紀錄範例（描述格式，尚無新 research runner 讀取）：

```json
{
  "record_version": 1,
  "run_id": null,
  "runtime_commit": null,
  "dirty_patch_sha256": null,
  "effective_config_digest": null,
  "effective_policy_digest": null,
  "tool_inventory": {"status": "not_observed", "manifest_sha256": null},
  "dataset": {"version": null, "sha256": null},
  "defense_commit": null,
  "isolation": {"verified": false, "evidence_ref": null},
  "results": {"status": "not_run", "artifact_sha256": null}
}
```

不能在 `isolation.verified=false` 時執行實驗。公開紀錄只存可分享的 metadata、hash 與去識別摘要；tokens、私人 prompt／mail／memory、模型／語音、raw attack responses 與正式 DB 不進本 repo。

## 驗證與回收研究結果

受影響的安全基線使用 [M0 Validation](../agent-runs/mcp-trust-security-m0/Validation.md)：identity、policy、schema／result、privacy、discovery、memory、OMI direct/fallback 與 consumers。依變更挑選 regression，移除安全斷言或只用 fake read 不能證明正式 provider／desktop gate。

完成研究後，先 review 具體 patch 與測試，再挑選可產品化的 bounded change 回 production；不直接 merge 整個實驗目錄、dataset 或弱化 policy 的設定。維持單一正式 executor、一次只切一個 owner，runtime adoption 另行驗收。
