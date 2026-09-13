# M0 修復施工計畫

使用者已於 2026-09-13 授權開始 M0 實作，並另行核准 project_reading 的限定 STDIO 試點。每步結果更新於 [Progress.md](Progress.md)，契約以 [Contract.md](Contract.md)為準；A8 的正式 runtime／真實記憶採用另列驗收。

## 1. 檔案責任與範圍

單一主實作者整合修改，不自動啟動 subagents。下表是必要責任範圍，不要求每個檔案都改；若 existing helper 可解決，保持局部 diff。

| 邊界 | 主要檔案／consumer | 責任 |
| --- | --- | --- |
| 記憶寫入與遷移 | Open-LLM-VTuber/src/open_llm_vtuber/character_memory_manager.py、character_memory_repository.py | Claim lifecycle、immutable provenance、授權與 dry-run migration |
| 記憶讀取與 UI | 同目錄 character_memory_retriever.py、character_memory_sql_index.py；kuro_launcher/memory_support.py、memory_panel.py、qt_controller.py | 未知狀態、索引刷新、候選核准／停用一致 |
| Policy | mcpp/tool_policy_manager.py、Open-LLM-VTuber/tool_policy.json；kuro_launcher/qt_controller.py、work_panel_api.py | 共用判斷、effective/configured 區分、安全理由 |
| Identity／schema | mcpp/types.py、tool_adapter.py、tool_manager.py、tool_catalog_manager.py、tool_executor.py；tool_catalog.json、service_context.py | Canonical mapping、排序、provider 視圖與參數驗證 |
| MCP 結果與分頁 | mcpp/mcp_client.py、tool_adapter.py、tool_executor.py | Result／DiscoveryResult、cache 提交與錯誤分類 |
| OMI 實際路徑 | mcpp/market_preflight.py、agent/agents/basic_memory_agent.py | Autorun、direct stream、fallback 與 policy 身分一致 |
| 紀錄與模型 consumer | conversations/single_conversation.py、group_conversation.py、chat_history_manager.py；agent 與 Launcher history consumer | 安全摘要、OMI evidence 特例、Prompt fallback、事件相容 |
| 呈現 | pet-electron 既有 status／history／memory consumer，只在 contract 調整需要時修改 | 顯示拒絕原因與限制，不移入 policy 邏輯 |
| 驗證 | Open-LLM-VTuber/tests/test_mcp_m0_*.py、tests/test_mcp_m0_launcher_policy.py、既有相關 tests | 真實呼叫鏈的 isolated integration／regression |

表中 mcpp、agent、conversations 均位於 Open-LLM-VTuber/src/open_llm_vtuber。新增 helper 按現有 package 放置；不預先建立多層新架構目錄。

## 2. A0：建立基線與隔離施工範圍

**輸入：** source、設定宣告、目前 branch/status、Calendar/Core 既有變更及兩輪審查。

1. 重新讀取 AGENTS、產品文件與目前 source。記錄 base commit、實際工作目錄、Python／SDK identity。
2. 建立逐檔 ownership 清單，辨識 qt_controller.py、mail server 等重疊檔案。先讓同檔寫者完成或取得明確隔離基線，再開始 MCP 修改。
3. Checkpoint 記錄 source commit、受影響檔案 digest、既有 diff／untracked 清單、有效設定的安全摘要。Private diff／設定副本放本機受控位置，不貼進公開文件。
4. 不將 checkpoint 等同 commit／push。不擅自 stash、reset、複製私人設定進新 checkout 或清理別人的變更。
5. 把 4 server／25 source 宣告／21 catalog／21 policy 與實際 runtime 狀態分開。核對 OMI schema 的 backend/fallback 來源及本機 provider profile。
6. 核對 Contract.md 初始大小／deadline 上限對現有合法工具的相容性，鎖定測試 profile；有衝突就記錄有界調整，不取消上限。
7. 先執行既有 20 項 policy/routing/OMI baseline；確認新的測試 fixture 不會啟動真實 MCP、LLM、GUI 或碰真實記憶。

**出口：** BASE-01、BASE-02 通過，有可辨識 checkpoint 與相關檔案責任。沒有基線或重疊寫入未排除時，不開始 production 修改；仍可整理隔離 fixture／文件。

## 3. A1：記憶寫入、讀取與 legacy 修復

1. 新 assistant claim 沿用 pending_confirmation，明確 enabled=false；不以 tool/runtime success 代替保存授權。
2. 修正 manager／retriever 對未知 status 的 active fallback，統一 lifecycle 判斷。
3. 修正同內容 upsert／compact／merge，保護既有 provenance、確認及停用決定。
4. 保留 explicit/manual 的受控保存入口，確認綁定候選版本；核對來源、內容類型與資料 scope。
5. 建立只讀 legacy inventory 與可重跑的 dry-run migration。只在 synthetic store／隔離副本驗證備份、升版、索引重建與回復。
6. 測試正常關閉／重啟、刪停用後 prompt／SQLite index 不再引用舊副本。不在此步驟改寫真實資料。

**出口：** MEM-01–MEM-07。候選不得藉由重複內容或索引回退升格；legacy 真實處置另列 A8 gate。

## 4. A2：Policy 與工作面板一致

1. 建立可識別模式、legacy deny aliases、可執行模式及 reason_code 的共用正規化。
2. 驗證 malformed 設定／規則與非有限數值，未知值預設拒絕。
3. Launcher policy 列表重用該判斷；不依磁碟 JSON 推定 effective runtime。
4. 維持 blocked status，相容加入 reason_code；沒有確認佇列時不產生假的待執行 action。
5. 將 mail.auth_start／finish 設 confirm；保留已登入 mail reads、有限本機 briefing 更新與現有受限 OMI 能力。
6. 覆蓋 OMI direct stream／一般 executor，policy 不存在時拒絕；測試拒絕後外部呼叫計數為零。

**出口：** POL-01–POL-06、對應 Launcher targeted tests。來源讀取正常不等於重新登入工具被允許，變更須在交付摘要說明。

## 5. A3：所有紀錄出口的 privacy projection

1. 先盤點實際資料流：LLM arguments → executor／direct stream → MCP result → status／模型／history／memory／log。
2. 實作通用安全摘要與 declarative 敏感欄位規則，使用 copy/projection，不修改執行 payload。
3. 覆蓋 parse error、malformed dict、JSON string、URL query、transport error、traceback、short text result 與 stream failure。
4. 修正 single/group conversation 的直接記錄與 history 轉存，防止 OAuth callback 在到達 MCP 前已被寫入 log。
5. 以合成 sentinel 檢查每個持久化／顯示出口，並確認工具收到的原始必要參數保持正確。
6. 只盤點舊紀錄的類型與風險，不在本次 source 修復刪除舊 log／history 或輪替真實 credentials。

**出口：** PRIV-01–PRIV-06。一般有界證據仍可供模型與 Reader 使用，診斷沒有 raw 私人內容。

## 6. A4：Canonical identity 全路徑遷移

1. 在既有型別加入 canonical_id、server_id、wire name 與 provider alias，建立單一映射 owner。
2. 遷移 catalog／policy 的既有註冊項，對 legacy 裸名稱建立固定 server binding。
3. 同步 ToolManager、catalog scoring、executor、OpenAI／Claude／Prompt exposure 與 service_context。
4. 同步 OMI autorun、direct stream policy、fallback、內建呼叫及 history 的 OMI evidence 特例。
5. 驗證 alias 字元／長度／碰撞、發現順序變更、server 缺失與 canonical deny 優先。
6. 保持一回合 alias map 固定；舊回合或更新失配時不派到其他工具。

**出口：** ID-01–ID-06。兩個同名工具各到正確 fake server；OMI preflight 不因 canonical key 改名而失效。

## 7. A5：Schema 與 result 契約完整性

先完成 schema，再完成 result；每部分通過 targeted tests 後再整合。

1. 保存原始 schema，為已使用的 provider profiles 建 deterministic 轉換，保留 digest／版本。
2. 不支持／無效工具從 Native、Prompt、catalog 提示一致排除；其他工具繼續可用。
3. 補 raw schema 執行前驗證，包含程式修改參數後與 direct stream 路徑。
4. 將 MCPClient／ToolExecutor 改成 canonical result，保留多 content、有序 mixed items、structuredContent、resource URI、isError 與 protocol failure。
5. 分別投影模型、UI status、history／audit，保留 OMI domain 限制與現有外向 envelope 的相容讀取。
6. 驗證 outputSchema、空結果、只有 structured data、取消、unknown execution outcome 及 byte caps；不自動 fetch resource links。

**出口：** SCH-01–SCH-06、RES-01–RES-06。不能因 parser／projection 成功就把 domain missing 當 succeeded/current。

## 8. A6：有界 discovery 與 cache 提交

1. 新增最小 DiscoveryResult，保留必要的 legacy list consumer adapter，但不能把 complete=false 丟掉。
2. 依 opaque cursor 分頁，採整體 deadline、pages/tools/bytes 上限、重複 cursor／identity 偵測。
3. 只在完整成功後一次更新 cache；partial 結果不成為可執行的新清單，也不移除未出現工具。
4. 把 complete／reason／時間傳到 ToolAdapter 與最小診斷 consumer；last complete cache 清楚標示未驗證。
5. 驗證單 server 失敗不影響其他 server；只清理自己擁有的 session/process，不新增全量重試。

**出口：** DISC-01–DISC-06。M0 不做新 transport、bounded concurrent discovery 或完整 Registry；這些留 M1。

## 9. A7：整合、source re-audit 與 source 完成

1. 執行新的 M0 tests、既有 20 項 baseline、memory lifecycle 與 Launcher relevant tests。
2. 以 fake SDK/session/provider 重播 Native、Prompt、OMI direct stream／fallback；mock 外部 I/O，保留真實 policy／mapping／projection 邏輯。
3. 核對 source map：無新裸名稱授權 fallback、無未覆蓋 logging path、無 claim active 或 stale evidence 擴權。
4. 依實際修改執行 syntax／targeted check；只有改到 renderer consumer 才做其 check/build。
5. 更新變更清單、設定／資料 migration 差異、證據、未驗證 runtime 風險及回復程序。

**出口：** INT-01–INT-04 與所有 source 驗收通過，標記 M0 source 完成；runtime 仍可為未驗證。

## 10. A8：真實資料處置與 runtime 採用

本步在取得具體 runtime／資料授權後執行，不由制定計畫或 source tests 自動觸發。

1. 確认 launcher root、有效設定、程序／listener owner、source revision/digest、SDK、policy digest 與 provider profile；不能僅看 port 回應。
2. 完成已授權的 legacy 記憶核對／備份／migration，或已接受的檢索隔離；保留原檔與回復證據。
3. 透過現有 owner 啟停／重載必要元件；不 broad kill，不操作中央共用 TTS 的生命周期。
4. 實際桌寵完成受限工具讀取、拒絕操作、Reader／history 證據顯示、候選核准／停用與重啟承接。
5. Live read 個別驗證 web、filesystem、mail、OMI。未登入／offline 如實記錄，不用 fixture 替代該 provider 的完成證據；OMI 選不產生持久化／高成本工作的有界讀取。
6. 檢查新 log/status/history 無 synthetic sentinel 或真實 sensitive values；證據只保存安全摘要。確認角色切換不改工具權限，也不恢復停用記憶。

**出口：** RUN-01–RUN-06。尚缺 source、資料處置、provider 或桌面證據時，精確列出未完成的 gate。

## 11. 回復與停止條件

- 每個 A 階段都有 private checkpoint：baseline、局部 source/config diff、測試紀錄及必要資料快照。資料 snapshot 先驗證目標路徑與可讀性，不在公開 repo 保存。
- Schema／identity／policy 遷移以同一組相容變更採用，不能只回復其中一個檔案導致混合版本。
- 遷移前核對 baseline digest；其他寫者變更同檔、raw schema 更新或資料變更時停止該操作，重新盤點，不覆蓋較新內容。
- Source rollback 只回復本任務可辨識的變更，資料 restore 只操作明確授權的備份及目標；不 reset database／worktree。
- 回復舊版會重新開啟已知漏洞時，先停用受影響能力並保留診斷，不以不安全 rollback 宣稱修復成功。
- 發現錯誤放行、secret 進任一紀錄、claim 升格、跨 server 派錯、domain 限制丟失、partial 冒充 complete，停止後續里程碑並修正。
- 權限／環境阻擋要保留確切錯誤，使用有授權的有界重試；不把環境錯誤冒稱產品 failure。

## 12. M0 之後

| 階段 | 前置條件 | 後續驗收方向 |
| --- | --- | --- |
| M1 基礎能力 | M0 source 與 runtime 完成 | Registry 只管 capability truth；第一個 loopback Streamable HTTP 讀取；auth、identity、健康／資料 freshness 分離；session owner 與 schema cache invalidation |
| M2 路由與容量 | M1 的真實 HTTP/stdio coexistence 有證據 | 20 servers／200 tools fixture；一般候選不超過 6；Prompt 也不帶全量 schema；慢／離線 server 不拖累其他領域 |
| M3 真實工作流程 | M2 有界路由與 policy 證據 | 先選一個 Study／其他 read-only source 接 Core observation、Briefing、提醒；驗證 restart、dedup、stale、停用與跨角色承接 |

不按附件清單一次接入所有整合。Calendar 優先沿用現有本機 Core owner；Google Calendar 同步另立契約。Memory Core 不複製其 domain truth；Codex／Asset 的寫入或高成本能力等 Action／Confirmation／Audit 完備後再評估。
