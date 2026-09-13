# M0 計畫與修復進度

更新日期：2026-09-13 14:30 +08:00（06:30 UTC）。計畫基線盤點時間：12:34 +08:00。

## 目前狀態

| Gate | 狀態 | 證據範圍 |
| --- | --- | --- |
| 需求審查 | 已完成 | 使用者確認兩輪 findings 與修正定義成立 |
| 計畫文件 | 已完成文件驗證 | 五份文件及索引；UTF-8、28 個本機連結、55 項驗收 ID 與 diff 檢查通過 |
| M0 source | 已實作並通過本輪隔離回歸 | Runtime Python 88 項、Launcher 8 項；schema inventory、renderer check/build 通過 |
| Legacy 真實記憶處置 | 未執行 | 已實作及驗證 synthetic inventory、migration、backup/restore、索引重建；未讀寫使用者 store |
| project_reading 限定試點 | 通過 | 實際 STDIO discovery、僅開放 2 工具、Plan.md 讀取、明確路徑邊界拒絕 |
| 正式 runtime／provider／桌面驗收 | 尚未完成 A8 | 沒有重啟桌寵，沒有真實 LLM、web/mail/OMI provider 呼叫；試點不等於正式採用 |
| Git 發布 | 未執行 | 未 commit／push |

## 基線與範圍

- Repo：C:\project\desktop-agent-runtime。
- Branch：main；HEAD：9786ff9d4cef8643903f29547e1455e88764e0dd。
- 開始時 git status 有 36 筆項目，其中未追蹤目錄是壓縮顯示，不能解讀成 36 個檔案。
- 既有變更包含本機 schedule/Core/service、Launcher、Electron／Work Panel、mail calendar ownership 與 tests；其中 qt_controller.py、mail_tools_server.py 等可能與後續修復重疊。
- 計畫階段只新增計畫目錄及 docs/index.md；實作階段局部修改 MCP、memory、Launcher 與 Work Panel consumer。既有 Calendar/Core、README、Roadmap 變更保留。
- 實作 A0 重新確認：Python 3.10.12、MCP 1.15.0、jsonschema 4.25.1、httpx 0.28.1。預設 profile 為 openai_non_strict；另有 strict／Claude／Prompt 隔離案例。
- 已建立本機 private checkpoint（原始 dirty diff、status、source digests），未 commit。結尾以 git apply --reverse --check --ignore-space-change 比對原始 dirty patch 成功；只是檢查，未反向套用。

## 需求來源

附件原檔留在使用者 Downloads，不複製進 repo；以下名稱與 SHA-256 只用於辨識本次版本。施工所需內容已整合於本文件組。

| 來源 | SHA-256 |
| --- | --- |
| desktop-agent-runtime_MCP_Orchestration_Architecture_20260913.txt | 9DF0AEF271C348DB26C0FB5F89117D260AF493AAE3D911D917E794F39B9F824B |
| desktop-agent-runtime_MCP_Reliability_Security_Remediation_20260913.txt | E6292A4BC676A6EE167AA2C80B79ADC7BCD0EDC490D4FF34F81C25E685FFA89C |

使用者已接受對以上附件的兩輪 source review 修正；Contract.md 將歧義定案，不保留「pending_confirmation 或 unverified」等未選定分支。

## 既有檢查證據

以下均來自本任務同一對話的前兩輪檢查，不是本輪重跑後的新結果，也不是修復通過證據。

| 檢查 | 觀察 |
| --- | --- |
| 靜態 inventory | Kuro 角色設定 4 servers；source 宣告 web 5、filesystem 5、mail 9、OMI 6，合計 25；catalog/policy 各 21 |
| 四項未登記 OMI 工具 | read_refresh_status、read_taiwan_bars、read_taiwan_technical_series、read_taiwan_chart；本次不自動開放 |
| 既有 targeted tests | test_tool_policy_omi.py、test_tool_catalog_market_routing.py、test_market_preflight.py 合計 20 項通過；未涵蓋本次全部漏洞 |
| Synthetic policy | confirm 拒絕，但拼錯 mode、unknown、scoped_auto 目前可被放行 |
| Synthetic discovery | 兩 server 同名工具只保留一個；有 nextCursor 時只呼叫第一頁 |
| Synthetic schema/result | Nested/數值 constraints 遺失；structuredContent、resource URI 未保留，LLM text 只取第一塊 |
| Synthetic logging | Tool input 中合成 OAuth sentinel 進入 log；未使用真實 secret |
| Synthetic memory write plan | Assistant 自述完成產生 assistant_outcome/active/project 候選；未寫真實 store |
| Synthetic reader | unverified＋enabled=true 被 manager 與 retriever 判為 active |
| Synthetic duplicate upsert | Pending assistant_claim 改掉既有 active 記憶 source/history ref，原 evidence 仍留存，形成不一致 provenance |
| Synthetic OMI autorun | omi.ask 觸發 autorun；僅替換為 omi-market::omi.ask 時目前判斷失效 |

## 已定案

- 先 M0，再 M1 foundation／M2 routing／M3 domain adoption，避免與首份附件里程碑混用。
- 記憶沿用 pending_confirmation；驗證不等於保存授權；包含重複、檢索、索引與 legacy migration。
- Policy 畫面與 runtime 共用判斷，blocked＋reason_code 保持相容；OAuth 寫授權流程不再冒充一般 read-only。
- Canonical migration 包含 OMI direct stream、Prompt、history evidence 與 catalog 特例，不只改 mcpp 核心字典。
- Raw schema/result 保真，模型、顯示、紀錄各自投影；unknown metadata 不任意外傳。
- 分頁有明確 partial/cache commit 語意；M0 不提前建立整套 Registry。
- Source、真實資料、runtime/provider、桌面及發布分開記錄。

## 計畫階段驗證（歷史紀錄）

文件寫入時，既有 docs/agent-runs 父目錄在一般沙箱回報 Access denied。經有界權限提升建立本次子目錄後，以一般檔案工具繼續建立文件；不擴大為 production 修改。

五份新文件及 docs/index.md 均通過 strict UTF-8 讀回、替代字元／衝突標記／行尾空白檢查；28 個本機 Markdown 連結均存在。Validation.md 有 55 個不重複驗收 ID，其中 source 49 項、runtime 6 項；這是驗收條件盤點，不是測試通過數。

git diff --check 通過；每份新文件另以 git diff --no-index --check 對空檔檢查，沒有格式問題。依 Tier 0，本輪未跑 unit、build、GUI 或 runtime smoke。

## 本輪實作

- A1：共用 lifecycle；assistant claim 保持 pending_confirmation；未知狀態與無授權記憶不進 prompt。重複 claim 不改既有 provenance。UI 核准 digest 綁定整筆候選版本，JSON save 使用跨程序鎖、磁碟版本比對與唯一暫存檔原子替換。Malformed store 拒絕空資料覆寫。索引同步包含最後一筆刪除與 legacy 隔離。
- A2：只有明確 read_only 可通過；unknown、scoped_auto、confirm、malformed 規則均拒絕。Mail OAuth start/finish 改為 confirm。Launcher 使用相同 policy 判斷，標明 configured 與 effective 未驗證。
- A3：參數、credential reflection、SDK/provider log、JSON parse、single/group status、history、memory 使用安全投影；工具實際參數保持原值。STDIO server stderr 不進 launcher 通用 log，連線診斷保留安全錯誤類型與 errno。
- A4：canonical server::wire_name、穩定 provider alias、固定 legacy owner、catalog/policy 遷移；新 session 及每次執行前比對最新 discovery 的 input/output schema digest。移除或 schema 失配即拒絕。
- A5：保留原始 schema 與有序 result；支援 Draft 2020-12／Draft 7 的本機 refs，未知 dialect／遠端 refs 拒絕。補參數後驗證 raw schema；SDK output validation 失敗保留 received evidence，區分 failed／unknown／cancelled。模型與 UI 有 byte cap，保留來源 warnings/missing，binary resource 不自動讀取。
- A6：分頁、重複 cursor/identity、pages/tools/bytes/deadline 限制；只提交完整 cache，partial 不成為新可執行清單。M0 仍使用 STDIO，未引入 M1 HTTP Registry。
- A7：真實 OpenAI／Claude／Prompt executor、BasicMemoryAgent OMI direct stream/fallback、provider 及 conversation consumer 使用 fake IO 回歸。OMI 已派送串流失敗後不自動再呼叫 MCP，delta-only 明確標成 incomplete。

## 本輪驗證證據

| 檢查 | 結果與適用範圍 |
| --- | --- |
| Validation.md Python runner：3 baseline + memory manager + 10 個 M0 test files | 88 tests，全部通過，0 skipped；包含原 20 項 baseline。均為隔離 IO，沒有 model/provider 實際呼叫 |
| test_mcp_m0_launcher_policy.py | 1 test 通過，執行真實 controller policy 投影方法 |
| test_work_panel_api.py | 7 tests 通過；loopback fake controller 驗證核准 digest contract |
| verify_mcp_source_inventory.py | 現有 source：web 5、filesystem 5、mail 9、OMI 6；25 schema 全部可投影，4 個 fake read dispatch 通過，不代表 live provider success |
| npm run check:renderer | 通過 |
| npm run build:renderer | 通過；一般沙箱先遇到 spawn EPERM，經有界提升重跑成功。Live2D legacy script 的 module bundling 警告仍存在，非本次改動 |
| verify_project_reading_pilot.py | 最終重跑於 14:27 +08:00 通過；未修改 default registry／角色／launcher settings |
| uv lock --check --offline --python ..\envs\kuro-llm310\python.exe | 通過，pyproject 與 uv.lock 一致 |
| Python syntax／Git diff | 工作區已變更的 61 個 Python 檔案 compile-only 通過；git diff --check 及本次 untracked UTF-8／空白檢查通過 |

試點 entry SHA-256：4947137d99ddc7064d2495f5131d820531d41c76cfce3595204a2f0a3e3ed16f。實際發現 25 個工具，只暴露 workspace_info、read_file。根目錄固定為本計畫目錄；讀 Plan.md 前 5 行。逃逸驗證要求回傳 outside the configured workspace root，不能以一般 missing-file error 代替。STDIO 子程序於 context 結束後關閉。

實作中發現並修正：重複 privacy projection 誤遮合法段落、reader Draft 7 output schema 相容性、restore 後 SQLite enabled 投影與 lifecycle 不一致。相關失敗已重跑通過；沒有把早期成功沿用為最終證據。

## 依賴、限制與回復

- pyproject 加入 jsonschema 並提高 MCP 最低版本；uv.lock 已解析且把必要相依套件鎖在本機已驗證版本。未安裝或升級正在使用的環境。MCP 1.15 所需 Pydantic／Typer／pywin32 及 JSON Schema dependencies 屬必要變更。
- Open-LLM-VTuber/pixi.lock 為既有上游環境快照，本次沒有可用 pixi，也未驗證其重建。這次的依賴重現證據限 pyproject／uv.lock 和既有 Python 環境；不宣稱全新機器或 Pixi 可完整重建。
- Work Panel 沿用 content_digest 欄位名稱，但值是整筆 review revision digest；舊頁面須重載，缺失／過期 digest 會拒絕核准。
- 真實 legacy store 沒有遷移。啟用 source 後，無保存授權的舊 claim 會被檢索隔離，須經使用者逐筆審核。Restore 同時驗證 current/backup digest；索引是衍生資料，採用時仍須明確重建。
- 完整 provider schema/工具語意仍由 server 擁有。執行前重新比對可偵測宣告變更；MCP 協定不提供 server 端 schema CAS，不能聲稱已消除 list/call 間所有外部競態。
- 本次不實作確認佇列、長期自動工作、M1 HTTP、M2 domain router 或 Core 新資料表。後續採用不能以目前 tests／限定讀取代替 RUN-01–RUN-06。
- 回復採精確檔案/hunk patch；不得 reset 整個 worktree。保留 private checkpoint，真實資料回復須另核對指定 store/backup。沒有 commit／push。

## 下一步

進入 A8 前，先核對使用者要採用的正式 profile／資料範圍，再透過既有 owner 啟動或重載。需要取得 runtime identity、真實 legacy memory 處置、桌寵拒絕／Reader/history 顯示及四個 provider 的有界讀取證據。M0 整體目前尚未完成，限定 reader 試點已完成。
