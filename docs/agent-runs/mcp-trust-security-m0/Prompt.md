# MCP 可信度與安全修復規格

制定日期：2026-09-13。狀態：M0 source 已實作，限定 reader 試點通過；正式 runtime／資料採用待驗收。

## 目標與本輪授權

使用者已確認兩輪審查發現成立，並授權依此計畫開始實作。另已明確核准啟動 project_reading 的現有 STDIO reader，僅開放本計畫目錄、讀取 Plan.md 並驗證路徑逃逸拒絕；不呼叫 LLM、不修改預設啟動設定。真實記憶遷移、正式桌寵採用與 Git 發布仍未執行。

修復目標是讓 Kuro 長期使用 MCP 時，不因模型自述而誤記工作進度、不因未知政策或名稱歧義誤放行、不丟失工具契約與來源限制，也不將私人參數寫入通用診斷紀錄。

本次修復工作包限於 **M0：可信度與安全修復**。後續順序為：

1. M0：記憶與授權、policy、privacy、identity、schema、result、discovery 分頁。
2. M1：Capability Registry、health、Streamable HTTP、session、cache 與 reconciliation。
3. M2：沿用 category routing，擴充 domain/server 路由與容量驗證。
4. M3：一個真實來源接通 Core 工作流程，再逐項擴充整合。

以上是本工作包的階段命名。第一份附件的 M0–M8 不再作為本工作包的施工編號，避免兩套 M1 意義混用。

## 閱讀順序

| 文件 | 責任 |
| --- | --- |
| [Contract.md](Contract.md) | 確定採用的行為、資料與相容性契約 |
| [Plan.md](Plan.md) | 施工順序、檔案責任、checkpoint 與回復條件 |
| [Validation.md](Validation.md) | 驗收編號、測試入口、source 與 runtime gates |
| [Progress.md](Progress.md) | 目前證據、未完成項目與下一步 |

本文件組自足，不需要存取原附件才能實作。原附件是需求來源，使用者接受的審查修正已收斂到 Contract.md。較早的 [memory/tool policy 計畫](../kuro-memory-tool-policy/Prompt.md)保留為背景；本工作包範圍內以此文件組為準，不宣稱舊計畫的完整 confirmation／automation 已完成。

## 產品與 ownership

依循 [產品願景](../../product/ProductVision.md)、[運作模型](../../product/OperatingModel.md)、[品質門檻](../../product/QualityBar.md)與 [Roadmap](../../product/Roadmap.md)。

- OMI、Study、Memory Core 等外部專案持有自己的資料與 domain 判斷。
- Conversation runtime 持有 MCP 身分解析、政策判斷、執行與模型投影。
- Kuro Core 持有正式工作狀態、observation、task、attention 與 execution evidence；不另外建立第二套 Core。
- 記憶服務持有長期記憶 lifecycle、來源與保存授權；角色不能自行改寫共享工作事實。
- Launcher 提供 lifecycle、診斷與受控操作入口；policy 畫面消費共用判斷，不重寫 allow/deny。
- Electron／Live2D／Reader 呈現結果與收集操作，不持有 MCP session、secrets 或 domain truth。

## 修復範圍

1. Assistant claim 進待確認候選；驗證證據與保存授權分開。修正重複候選覆蓋 provenance、未知狀態回退與 legacy 記憶處置。
2. Policy 對未知或未實作模式拒絕執行；runtime、工作面板與事件狀態一致。
3. 所有路徑使用 server-aware 身分與受控 legacy mapping，包括 OMI direct stream/preflight、Prompt fallback、history evidence。
4. 原始 schema 保真，provider 投影明確；所有入口執行前驗證原始契約。
5. 結果保留 structuredContent、完整有序 content、resource URI、錯誤與 domain 限制，再分別投影到模型、UI 與紀錄。
6. 診斷採通用安全摘要，涵蓋 malformed input、exception、stream 與 history；不更動送給工具的真實參數。
7. Discovery 支援有界分頁，完整性可觀察，不將部分清單覆寫成完整 cache。

## 本次不做

- 不新增 HTTP／SSE transport、Domain Router、大型 Registry service 或新的整合設定頁。
- 不新增完整通用 confirmation queue、scoped_auto 或自動長期記憶寫入。
- 不新增外部 MCP，也不自動開放目前未登記的四個 OMI public tools。
- 不修改 OMI 市場語意、財務判斷、刷新 owner 或外部專案資料庫。
- 不重做 Calendar／本機時間表、Core schema、通知排程或 Live2D／TTS。
- 不安排無關 dependency upgrade、整體 UI 改版或大量檔案重構。
- 不在制定計畫時清理既有 log、history、memory、cache 或 dirty worktree。

## 不可破壞的條件

- 目前工作區有本機時間表變更，須保留並建立基線；不得 reset、stash、覆蓋或夾帶進本次修復。
- 正式狀態維持單一 owner。Canonical ID、wire tool name 與 provider alias 是同一工具的映射，不是三套授權來源。
- Connected、執行成功與 domain 資料 current 分開；未知不呈現為零、完整或健康。
- 未實作的確認能力回傳拒絕與原因，不能假裝已建立可核准的待執行操作。
- 不使用 persona／prompt 代替 runtime policy 或原始 schema 驗證。
- 保存授權、私人證據、OAuth 資料、generated config、索引、logs 與備份不進 git。
- 真實記憶遷移與 runtime 採用另依當時授權執行；已授權範圍內的例行驗證不重複要求確認。
- 未經要求，不啟動 subagents，不 commit 或 push。

## 完成定義

| 階段 | 完成條件 |
| --- | --- |
| 計畫交付 | 五份文件與驗收對照完整，UTF-8／連結／diff 檢查通過 |
| M0 source | 所有 source 必要項通過；migration 只在隔離副本驗證；有精確檔案與測試紀錄 |
| M0 runtime | 程序載入相符 source/config/policy；桌寵、工作面板、live 安全讀取與 legacy 記憶處置均有證據 |
| 發布 | 僅在另行要求後檢查 staged diff、commit／push 並驗證；不屬於 M0 自動完成條件 |

只有 source 與 runtime gates 都成立，才可稱「MCP 可信度與安全修復完成」。計畫完成、fixture 通過或 HTTP 200 不代替 runtime 採用證據。
