# G1～G3 實作與證據

日期：2026-10-26。Source/fixture gate PASS；Live、Runtime adoption、Product acceptance 為 UNVERIFIED。

## 基線與範圍

- Checkout：`C:\project\desktop-agent-runtime`，branch `main`。
- 起始 dirty/untracked：74 個實際檔案（`status --porcelain=v1 -uall -z`）。
- 原始 `web_tools_server.py`：35,876 bytes，SHA256 `a9d7a9ff80785f5a4bcf82a2ba8e162394db107d9d7515b2a66b24854526dc31`。
- 本次暫存基線：`%TEMP%\kuro-web-g123-wi18ismh`，包含 `baseline.json`、原始 server bytes、完整 `tools.before.json`；沒有複製私人資料。
- ToolCatalog、ToolPolicy、Settings、Router、ToolExecutor、ServerRegistry 與其他 WIP 僅讀取／測試，未編輯。

## G1 連線邊界

`web_fetch.py` 為既有 STDIO server 的內部 I/O helper，沒有 lifecycle/service/manager。

1. 僅標準 port 80/443 的 HTTP(S)，拒絕 userinfo、控制字元、scope ID、私有 hostname 與非 public IP。
2. `PublicNetworkBackend.connect_tcp` 在真正建立連線前 resolve；全部 DNS 回覆都須 public，mixed answer 直接拒絕；上限 32 answers。
3. 只取第一個通過驗證的 numeric IP 交給現有 `httpcore.AnyIOBackend`；沒有 hostname fallback 或 connect retry。已核對安裝版 AnyIO：numeric IP 不重新查 hostname。
4. 在 TLS 與 HTTP write 前檢查 socket peer IP/port；無 peer、非 public 或 mismatch 立即關閉。httpcore 保留原 hostname 作 Host/SNI，CA bundle 固定使用已安裝 certifi，保留 `check_hostname` 與 `CERT_REQUIRED`。
5. 每跳建立新 pool，再驗證 URL/DNS/peer；不復用舊 DNS，最多 3 redirects。拒絕 loop、HTTPS downgrade。Brave 帶憑證請求完全不跟隨 redirect。
6. 使用 httpcore 公開 API，不經會讀 proxy/auth 環境的 AsyncClient；沒有 cookies、netrc、HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 或 SSL_CERT_FILE/DIR 注入。
7. 只接收 HTML/XHTML；只有固定 Brave endpoint 可收 JSON。`Accept-Encoding: identity`，若伺服器仍回壓縮則拒絕，避免解壓炸彈。PDF/影像/未知 MIME 拒絕。

| 限制 | 上限 |
| --- | --- |
| 接受／累積 response body | 1,000,000 bytes；超量 chunk 不加入 body，立即關閉 |
| 每次 HTTP 操作，包含排隊與所有 redirects | 20 秒；正文 fetch 15 秒 |
| DNS/connect/TLS/read/write timeout | 各 8 秒，受上述總期限約束 |
| 每次工具研究總期限 | 60 秒 |
| 同時 I/O | 4 |
| 整個 server HTTP hops | rolling 60 秒內 60 次 |
| 每次工具 HTTP hops | 40（包括 redirects/provider/fetch） |
| 主搜尋 query fast/normal/deep | 最多 3/5/8 |
| 正文 fetch fast/normal/deep | 最多 0/2/4（參數可減少，不可突破） |
| 每次研究 Brave fallback | 最多 2 queries |
| 整個 server Brave API | rolling 60 秒內 2 次，失敗也計數，沒有 retry |
| query | 600 characters、75 words；每來源最多 10 results |

Quota 為目前 STDIO server process 的記憶體限制，重啟會重設；不是持久帳務／每日花費上限。OS DNS resolver 可能在取消後才結束底層 lookup，但已取消的 coroutine 不會接續連線。網路 receive 可預讀至下一個 bounded httpcore chunk；接受的 body 不超過表列 byte cap。

HTML 使用既有 BeautifulSoup，依 main/article/content 與文字／連結密度選擇正文，移除 script/navigation/hidden 等，保留 title、description、author、宣告 canonical、截斷旗標與正文 hash。沒有新增套件、登入、cookie、paywall 或 bot challenge 繞過。JS-only、登入頁、paywall 的內容完整性不受保證。

## G2 選用第二來源

主來源仍為 DDG HTML，成功時不呼叫 Brave。DDG 失敗或沒有可用結果，才考慮 Brave；兩者共用 `SearchQuery(text, limit)` 與結果正規化／既有 merge 路徑。

固定 endpoint 為 `https://api.search.brave.com/res/v1/web/search`，使用 `q`、`count` 與 `X-Subscription-Token`。不提供任意 endpoint、shell provider、Google/Bing fallback 或 LLM answers endpoint。依據：[Brave 官方 API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get)。

安全 opt-in 必須同時完成 registry 明確傳遞與啟動進程環境注入。只在父 Launcher 設變數不足：`MCPClient` 傳入 `StdioServerParameters(env=server.env)`，SDK 的 `get_default_environment()` 僅繼承基本 OS 變數，不會自動傳遞 Brave 兩個變數。

未來 operator 選擇啟用時，沿用以下既有 ownership 流程（本次未修改正式設定或啟用）：

1. 在實際使用的本機 ignored `Open-LLM-VTuber/mcp_servers.json`，只於既有 `mcp_servers.kuro-web` entry 加入以下 `env` 欄位，保留原本 command/args/cwd/timeout 等欄位；若已有 env，合併這兩個鍵，不覆蓋其他設定。JSON 中只有 placeholder，沒有明文 key。

   ```json
   "env": {
     "KURO_WEB_BRAVE_ENABLED": "%KURO_WEB_BRAVE_ENABLED%",
     "KURO_WEB_BRAVE_API_KEY": "%KURO_WEB_BRAVE_API_KEY%"
   }
   ```

2. 由既有安全啟動／secret 注入流程，在真正載入 `ServerRegistry` 並建立 `MCPClient` 的進程環境提供 `KURO_WEB_BRAVE_ENABLED=1` 與 `KURO_WEB_BRAVE_API_KEY`。若從 Launcher 啟動 conversation runtime，該環境也必須傳到 conversation runtime；只改另一個 terminal 或已啟動進程的父環境沒有作用。勿把 key 放入 registry、CLI arguments、命令歷史、log 或新的 secret file。
3. `ServerRegistry` 在載入設定時用既有 `os.path.expandvars` 展開 placeholder；`MCPClient`／SDK 再將明確的 `server.env` 交給 STDIO child。設定與環境變更須由後續獲授權的正常啟動載入，不代表目前進程已採用。
4. 原 server `__main__` 才呼叫 `BraveConfiguration.from_environment`。enabled 必須精確為 `1`，否則不讀取 key；缺 key、空白／控制字元、過長／非 ASCII，或殘留 `%NAME%`、`$NAME`、`${NAME}`（含嵌入／巢狀未展開值），均停用 Brave。不要把 `expandvars` 留下的 literal placeholder 當成有效憑證。結果為 `brave_api unavailable/not_configured`，DDG 保持可用。

本次沒有讀取目前 Brave key／`.env`、修改 ignored 正式 registry、建立 secret 管理器或明文 key 檔。測試只用 synthetic registry 與 synthetic env；模組 import 仍預設 disabled。

provider statuses 區分 ok、zero_results、unavailable 與 quota/error reason；錯誤只保留固定安全碼。canonical URL 移除 fragment／已知 tracking parameters，保留 www、尾斜線、ref/source 等可能改變語意的部分，不信任頁面 canonical 宣告做跳轉。相同 URL 跨 query/provider 的觀察保留來源與文字差異。

## G3 證據語意與相容性

五工具的名稱、description、inputSchema/outputSchema 與回傳 `str` 保持不變。搜尋／正文成功與部分失敗結果在既有可讀文字後附 `kuro.web.evidence.v1` JSON；不新增 MCP tool 或改為新的 MCP structuredContent contract。`Evidence` TypedDict 提供內部型別邊界。

- 每筆保留 source/provider/canonical_url/domain/title/snippet/content、body URL、metadata、publication observations、缺漏與 conflicts。`search_observed_at` 是所保留 observations 中第一個有值的搜尋觀察時間，各 query/provider 的完整時間仍在 observations；不是正文時間。
- `body_fetched_at` 僅取成功頁面 fetch snapshot 的時間；沒有 fetch 或 fetch 失敗一律 null，即使錯誤 snapshot 帶有嘗試時間也不採用。舊 `fetched_at` 保留為 `body_fetched_at` 的相容別名，絕不 fallback 至搜尋時間。直接 fetch 沒有搜尋觀察時 `search_observed_at=null`。
- `published_time.original/validated` 的 validated 只代表可解析格式與時區，不代表實際查證；date-only 不補 timezone，naive/invalid/future 時間不當成 current。updated time 與不明 `<time>` 分開保存，不冒充發布時間。
- 發布日期不同回報 conflicting 並保留原文與來源；同 URL 的不同 search excerpt 回報字面差異，明示不等於語意矛盾。
- 相同正文或 snippet 可回報 `evidence/identical_excerpt_only`；不同網域／搜尋引擎、相同轉載都不證明獨立事件。
- 所有 claim-level corroboration 與語意內容衝突判定均為 `unsupported`。本功能沒有 LLM 結論產生器，也沒有自動事實查核。
- confidence、official-looking 與 source kind 為 heuristic ranking。`require_official` 維持既有排序偏好，不是官方身分認證。
- `recency_days` 是 query hint，`filter_enforced=false`；老資料／未知日期不能稱今日新聞。已移除「只要有日期就加 freshness 分」的行為。
- 正文失敗保留 search evidence 與 `body_fetch_failed`，無日期保留 unknown/missing。所有外部文字標為 untrusted evidence，不作指令。

## G1～G3 首輪驗證命令與結果

使用指定 `envs/kuro-llm310/python.exe`，沒有正式進程啟動或對外爬蟲。已安裝依賴：httpx 0.28.1、httpcore 1.0.9、AnyIO 4.11.0、MCP 1.15.0、BeautifulSoup 4.14.2；沒有安裝或更新套件。network backend 依據：[httpcore 公開 network backend contract](https://www.encode.io/httpcore/network-backends/)。

```powershell
$env:PYTHONPATH = "$PWD\Open-LLM-VTuber\src;$PWD\Open-LLM-VTuber\local_mcp;$PWD\Open-LLM-VTuber\tests;$PWD\tests;$PWD"
.\envs\kuro-llm310\python.exe -m unittest test_web_research
.\envs\kuro-llm310\python.exe -m unittest test_mcp_m0_discovery test_mcp_m0_identity test_mcp_m0_schema test_mcp_m0_policy test_mcp_m0_results test_mcp_m0_integration test_tool_catalog_market_routing test_g2_tool_settings
.\envs\kuro-llm310\python.exe -m py_compile Open-LLM-VTuber/local_mcp/web_tools_server.py Open-LLM-VTuber/local_mcp/web_fetch.py Open-LLM-VTuber/local_mcp/web_evidence.py Open-LLM-VTuber/tests/test_web_research.py
.\envs\kuro-llm310\python.exe -m ruff check Open-LLM-VTuber/local_mcp/web_tools_server.py Open-LLM-VTuber/local_mcp/web_fetch.py Open-LLM-VTuber/local_mcp/web_evidence.py Open-LLM-VTuber/tests/test_web_research.py
& C:\work\Git\cmd\git.exe diff --check
```

- 修改前：Router 6/6、Settings 6/6 PASS。
- 現有 targeted MCP/Router/Policy/Settings regression：49/49 PASS。
- 最終新增 fixtures：40/40 PASS；包含五工具真實 FastMCP mock call、五 canonical identities 經既有 Adapter/Executor dispatch、thinking_power 路由、所有 HTTP 負向與證據語意案例。加上既有 regression 共 89/89 PASS。
- 初輪曾發現 fixture ssl-object 回傳錯誤、DDG fixture markup 不符與 timeout/cancellation cleanup 問題；已修正並改用 AnyIO cancellation scope，重跑沒有 orphan task 警告。
- 五工具完整 discovery metadata/schema 與修改前 snapshot 完全相同：PASS。
- syntax/ruff：PASS；`git diff --check` PASS。Git 提示部分既有 WIP 為 LF→CRLF，沒有 diff whitespace error；本次原 server 保持 CRLF。
- 最終 UTF-8／尾端空白／結尾換行讀回 PASS。全部 74 個原始 WIP 的 bytes/sha256 與 status rows 完整保留，Git index bytes/sha256 未變；81 個現有 dirty/untracked = 原始 74 + 本次 7。`final-verification.json` 存於上述暫存基線目錄。

本次改檔僅：`web_tools_server.py`、新增 `web_fetch.py`、`web_evidence.py`、`tests/test_web_research.py`，以及本資料夾的 Prompt/Plan/Progress 三份文件。沒有改動 catalog/policy/Settings、依賴清單、正式 runtime config 或其他服務。

## Reviewer 定點修正（同日續輪）

- P2 opt-in：補足 registry → MCPClient → SDK child env → 原 `__main__` 的實際傳遞流程；在既有 Brave 設定入口 fail-closed 拒絕未展開 placeholder。未改 ServerRegistry/MCPClient 的共用行為，也未讀取／修改正式 ignored registry。
- P2 時間：拆開 `search_observed_at` 與 `body_fetched_at`，相容 `fetched_at` 僅指正文取得時間。沒有把搜尋成功視為正文取得成功。
- 本輪僅改 server、evidence、原 targeted test、本文共 4 檔；原 `web_fetch.py`、Prompt/Plan 與所有先前 WIP 保留。
- 續輪基線：`%TEMP%\kuro-web-review-a2advssj`，保存 81 個既有 dirty/untracked 的 bytes/hash/status、index hash、修改前 server/evidence/test bytes 與五工具 discovery。已先對照上一輪基線確認原始 74 WIP 未變。
- 修正前先執行 4 個新 regression 方法：FAIL（placeholder 設定仍 enabled；三種證據狀態缺少獨立時間欄位），確認測試能抓住問題。修正後的 Web suite 46/46 PASS，含原 40 測試與新增 6 方法。
- 新增 STDIO fixture 經真實 ServerRegistry loader、MCPClient、SDK `stdio_client` 與原 server `__main__` 執行；5 個 disposable child 情境涵蓋父環境但無 registry env、完整 placeholder、缺 key、缺 enabled、enabled=0。provider fetch 全為 synthetic，TCP backend 明確拒絕網路；每個 child 的五工具 metadata/schema 均比對一致，並由 EOF 正常結束，assert 沒有呼叫強制終止。
- fixture 初次把 `ToolResult.model_text()` 的文字與既有 structuredContent 合併輸出當成單一 JSON，解析失敗；已改從原 `text_blocks[0]` 讀取 appendix，沒有修改 production ToolResult。
- 最終驗證：Web 46/46、既有 MCP/Router/Policy/Settings 49/49，合計 **95/95 PASS、0 FAIL**。原 89 測試全部保留通過；另外比對 AST 確認原 40 個 Web test methods 未被改寫。
- py_compile、ruff、UTF-8 讀回與本輪 4 檔 diff whitespace check 均 PASS。server 保持 CRLF，其餘三檔維持 LF。
- 本輪 81 個起始 dirty/untracked 中，僅授權 4 檔變更，其他 77 檔 bytes/hash 未變；原始 74 WIP bytes/hash、Git index bytes/hash、完整 Git status rows 均未變。五工具完整 discovery metadata/schema 與本輪開始快照完全一致。receipt：上述續輪基線目錄的 `final-verification.json`。

續輪使用上節同一組 unittest、py_compile、ruff 與 diff 命令，Web suite 現在另含隔離 STDIO child env fixtures；沒有啟動正式 Kuro 或其他 MCP，沒有真實 DDG／Brave API 呼叫。

## 驗證範圍限制

安全測試使用真正 httpcore pool/HTTP parser 與假 socket stream，DNS 與 numeric dial 被 fixture 攔截，檢查目的 IP、peer、Host、TLS hostname/check_hostname/CERT_REQUIRED、每跳與 cancellation。不是公網 TLS handshake、Windows 正式啟動或 live DNS 的驗收證據。

未實際查詢 DDG／Brave，也未檢查帳號 key、額度、供應商今日可用性或正式 Kuro 採用。G4 PDF/Playwright 延後。Live／Runtime adoption／Product acceptance 均為 UNVERIFIED。
