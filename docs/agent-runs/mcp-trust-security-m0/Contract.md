# M0 行為與相容性契約

以下定義目標行為，不表示程式已實作。驗收編號見 [Validation.md](Validation.md)。

## 1. 記憶：來源、有效性與保存授權

### Lifecycle 與 active 條件

M0 保留 `active`、`pending_confirmation`、`superseded`、`disabled`、`pending_delete`，不新增 `unverified` lifecycle，也不全面更名 legacy source。

新 `assistant_outcome` 語意統一為 assistant claim，使用 `pending_confirmation`、`enabled=false`；未驗證性記在 provenance。未知或 malformed status 不得因 enabled=true 回退為 active。舊版缺少 status 的資料走明確 legacy 判斷，含糊資料進待審核清單；manager、retriever、SQLite index、prompt builder 與 Launcher 要一致。

長期記憶成為 active 必須同時符合：

1. 內容是允許保存的穩定偏好、背景或長期決策，不是每日資料、一次工具結果或暫時完成狀態。
2. Provenance 可追溯，呈現可信度不超過證據。使用者回報不能標成 runtime 已驗證。
3. 有綁定內容、scope 與操作的保存授權：明確「請記住……」或既有受控核准操作。一般肯定句、tool success、服務 Ready 不構成授權。
4. 通過敏感內容、衝突與 lifecycle 規則。

M0 不開放 scoped_auto 記憶保存。使用者明確要求記住專案完成時，只能保存帶「使用者回報」來源的陳述；不得據此更改 Core 的正式完成／驗收狀態。

### Provenance 的最小契約

可沿用既有 evidence 容器，採版本化驗證，不建立新記憶服務。

| 資料 | 必須表達的意義 |
| --- | --- |
| 來源 | manual、explicit user、assistant claim、heuristic、tool evidence、runtime evidence |
| 證據引用 | 可核對的 producer、事件／執行 ID、時間及證明範圍 |
| 驗證狀態 | 未驗證、使用者回報、工具結果已核對、指定 runtime 驗收已核對 |
| 保存授權 | 授權方式、確認紀錄引用、時間、內容與 scope digest |
| Lifecycle | status、enabled、版本、supersedes／conflicts 關係 |

模型生成的 verified 欄位、字串 tool_call_id 或「測試通過」不是可信證據。Evidence 須由受信任的執行紀錄核對，綁定 canonical tool、target、參數／結果版本與時間。工具成功不能證明另一項部署、UI 或 domain 驗收。

內容改變後不可直接沿用舊保存授權。敏感證據只留在本機受控資料，通用 log 不存原文。

### 重複、衝突與停用

- 待確認 claim 不得覆寫有效記憶的 source、source_history_uid、evidence、授權、confidence、importance 或 status；同內容也適用。
- 重複候選保留為獨立候選或關聯事件，不污染已確認記憶。
- Claim 不得 supersede、重新啟用或取消使用者的停用／刪除決定。
- 核准綁定當時候選版本，修改候選後重新取得對應授權。
- 停用、刪除、遷移後刷新索引與已組合的 memory prompt，舊副本不能繼續參與正常檢索。

### Legacy 資料處置

先只讀盤點「保存授權可證」「assistant 自述且無授權證據」「資訊不足」。不能全面降級 active，也不能只修未來寫入後宣稱舊資料安全。

遷移方案包括版本、private backup、dry-run 差異、ID／時間／確認來源保留、冪等性、索引重建與 rollback。曾手動核准但仍標 legacy source 的資料要保留核准證據，不能只靠 source 字串判定。

Migration 工具與檢索防護在 source 階段使用隔離副本驗證。真實資料遷移須有具體範圍授權。Runtime 完成前，受影響資料必須已核對／遷移，或有經接受且可觀察的檢索隔離；未處置就保留 gate 未完成，不刪除原資料。

## 2. Policy：一致且預設拒絕

### 模式與相容語意

「可識別設定」與「允許執行」分開。保留外部 status=blocked，新增 reason_code，不以新 status 取代原有終止狀態。

| 設定 | 執行結果 | reason_code／限制 |
| --- | --- | --- |
| read_only | 條件式允許 | 工具綁定、參數、path／URL、預算與能力限制全數通過 |
| blocked、deny、disabled | 拒絕 | policy_disabled；後兩者保留為 legacy deny aliases |
| confirm、needs_confirmation | 拒絕 | confirmation_required；沒有通用確認執行佇列 |
| scoped_auto | 拒絕 | unsupported_policy_mode |
| 未知值／未登記工具／malformed 規則 | 拒絕 | unknown_policy_mode／unregistered_tool／invalid_policy_config |

allowed／auto 不自動映射成 read_only；若本機另有這些值，列為待審核設定。缺少 mode 只可使用經驗證的 default_mode，預設 blocked。

初始化驗證整體及逐工具設定，錯誤定位不得包含私人值。錯誤工具不拖累其他合法工具；整份設定讀取失敗則整體 fail-closed。數值規則拒絕 NaN／Infinity、非法型別；不略過 malformed path／URL／budget 規則。

### 單一判斷來源與生效狀態

Runtime 與 Launcher 畫面共用正規化及模式判斷。Launcher 不再以「不在 deny 名單就是 allowed」推定權限。重用純 policy 模組／helper，不為畫設定頁啟動 conversation runtime。

Configured policy 與 effective policy 分開，附安全的版本／digest。沒有 runtime effective 證據時只能顯示設定值，不能稱目前可執行。M0 不新增任意 hot reload；設定在明確重新載入／採用後生效。

一般呼叫、Prompt call、OMI direct stream／preflight 與 fallback 全部使用同一 canonical policy 決策；拿不到 policy 不能預設允許。拒絕不觸發外部呼叫，也不建立可自動重送的 action。

### 現有能力的副作用分類

- 已登入帳號的受限讀信保留；mail.auth_status 保留狀態讀取。
- mail.auth_start／mail.auth_finish 會改寫本機授權資料，M0 設為 confirm，一般 agent 工具路徑拒絕。這是明確行為變更；不新增 OAuth UI，不假稱已提供重新登入流程。既有使用者操作入口需個別核對，不能由模型繞過。
- mail.update_briefing 是有界本機呈現更新，保留既有範圍，不取得外部信箱或任意本機寫入權。
- OMI bounded refresh／非持久化 LLM 分析依現有 policy 保留；allow_write、report、超預算仍拒絕。read_only 不代表沒有 API 成本或可任意 retry。
- M0 不新增重試。既有 stream/fallback 維持政策及可解釋的預算；取消或結果未知不能被新機制自動重送。

## 3. 工具身分與遷移

### 唯一映射

`canonical_id = server_id::tool_name`。Server ID 由本機受控設定識別 owner，不採用模型或 description 自稱的身分。分隔字元須驗證或可逆編碼，不產生解析歧義。

| 欄位 | 用途 |
| --- | --- |
| canonical_id | catalog、routing、policy、execution、audit 的內部 key |
| server_id | 查找確定的 transport/session owner |
| tool_name | MCP wire tools/call.name，保留 server 原始名稱 |
| api_alias | 依 provider 限制產生，反查同一 canonical_id |

Alias 要 deterministic、處理長度及字元碰撞，涵蓋 OpenAI、Claude、Prompt。依完整 canonical ID 產生穩定映射，不按 discovery 順序加流水號。Alias 與裸名稱不使用含糊查找優先序。

已送給模型的 alias map 在該次 interaction 固定；更新後不能將未完成呼叫映射到別的 server。工具移除或版本失配要拒絕或重新規劃。

### Legacy 相容

目前 catalog／policy 以明確 server 綁定遷移至 canonical key。Legacy alias 只能使用預先受控的一對一映射，例如 omi.ask → omi-market::omi.ask；不能由「目前只有一個同名工具」推導授權。

Canonical deny 優先於 legacy allow。Canonical 不存在、server 缺失／停用、映射衝突時拒絕，不改派同名工具。舊 history 可保留顯示名稱，但不能提供新的執行授權。

遷移包含 catalog 排序分支、OMI autorun／direct stream／fallback、內建呼叫、tool status、history 的 OMI evidence 特例與 provider 名稱解析。顯示名稱不另行決定工具身分。

## 4. Schema：原始契約與 provider 投影

- Raw input schema 是參數契約，不原地修改；保留 nested properties、限制、union、$defs／$ref 等語意。
- Provider schema 使用明確 profile；不推定所有 OpenAI-compatible endpoint／model 一致。Strict／非 strict 分開驗證，profile 選擇記入 evidence。
- $ref 僅做有界本機解析，不擅自連外或讀任意檔案。循環、過深、過大、無法表達都有錯誤分類。
- Transformation 要有文件化等價性，不靜默移除 constraint、改 required 或附加 additionalProperties=false。
- 區分 schema_invalid 與 provider_schema_unsupported；受影響工具在該 provider 不暴露，其他工具可用。原始契約不因 provider 不支援就被判為無效。
- 保存 raw/provider schema digest 與轉換版本，使用 deterministic serialization，不含 credentials。
- Native tools、Prompt fallback、catalog 提示與 executor 使用同一有效工具視圖。轉換失敗工具不留在完整 prompt；模型手寫名稱也不能繞過驗證。
- 執行前按 raw schema 驗證真正送出的參數，包括程式補參數後與 OMI direct stream；不只相信模型看到的 schema。失敗不呼叫 server。
- 有 outputSchema 時沿用可用 SDK 驗證並保留結果，不建立第二套 domain validator。

## 5. 結果：受控 canonical 資料與投影

### 最小結果契約

採 versioned 本機型別／helper，不建立新服務。至少包含：

- execution_id、canonical_tool_id、server_id、wire tool_name、policy decision 引用。
- Execution status：succeeded／failed／cancelled／unknown；protocol error 與 MCP isError 分開保存。
- 原始有序 content_items、頂層 structured_content、受控 metadata／annotations、schema validation 狀態。
- Structured error：類別與安全摘要、是否收到結果、是否可能已執行。
- UTC aware started_at／completed_at、monotonic duration、truncation／限制與安全 evidence reference。

text_blocks／resource_links 可為 derived views，不各自維護第二份真相。structuredContent 是頂層欄位，不插入 content_items 製造不存在的順序。

### 錯誤、domain 與使用邊界

不能靠第一個 content type 判定成功。isError=true、protocol exception、空結果、只有 structuredContent、後置 warning、多 text、mixed content 均需處理。

Execution success 不代表資料 current；stale／partial／missing／provider failure 按原 domain contract 保留。Normalizer 不從自然語言猜市場／學習結論；OMI adapter 繼續消費 OMI envelope。

模型投影、UI status、audit/history 分開。未知 metadata／_meta 不自動送模型。Resource URI 可保留，但不自動下載、讀 file URI 或執行；後續 IO 仍受政策管控。

完整保留指可接受輸入範圍內的語意保真，不代表無限制常駐／永久保存 raw payload。回合結束依生命周期釋放；private artifact 需要明確 owner、位置、保留期限與授權。

## 6. Privacy：執行、模型、顯示與紀錄分流

原始執行參數只在必要邊界使用，不就地遮罩。Log／status／history 使用另建的安全摘要；operational log 預設只保留 execution/canonical ID、argument names、政策原因、狀態、duration、錯誤類別及白名單診斷值。

通用 helper 支援巢狀 object/list、JSON arguments 字串、URL query／header 與 error message。非 JSON／解析失敗不退回 raw dump。Sensitive key pattern 是防線之一，不能取代值白名單；短文字或長度限制不代表安全。

中央規則可帶個別 capability 的 declarative 敏感欄位設定；不要求每個 tool 自寫遮罩，也不禁止必要的 auth／asset metadata。

### 必須覆蓋的路徑

- ToolExecutor：正常、parse error、blocked、exception、短 result logging。
- MCPClient：error_text、transport exception／traceback、discovery failure。
- OMI direct stream、fallback、模型呼叫錯誤及所有 status 產生端。
- Single/group conversation：user input、assistant output、debug status、history event；Reader／Launcher 診斷 consumer。
- Memory candidate evidence excerpt 與診斷，不能因保存 claim 複製 secrets。

工具結果為不可信資料，不能將其中指令提升為 system／policy／保存授權。模型需要的證據透過有界內容投影提供，不把整份結果一律遮到無法使用。

### History 與 OAuth

History 與 operational log 目的不同。保留既有經允許的對話功能，但工具輸入、交換憑證與 raw error 不得因事件轉存而自動持久化。可辨識的 OAuth callback／token 交換內容，須在通用 log、history、memory、status 前防護，不回聲重述 secret。M0 不提供一般模型自動 OAuth exchange。

新紀錄符合此契約；舊 log/history 不自動刪除。先盤點類型／數量及暴露路徑；清理或 credential rotation 另提具體範圍，不在公開文件貼原文。

## 7. Discovery：分頁與完整性

M0 只增加最小 DiscoveryResult，完整 Registry 留至 M1。至少包含 server_id、tools、complete、reason、pages_read、observed_at、schema_digest、來源 live/cache 與 cache 時間。

- Cursor 是 opaque，逐頁傳回 SDK，不解析／記錄 raw cursor；偵測重複及循環。
- 同 server 重複 tool name 視為衝突，不最後寫入覆蓋；跨 server 同名由 canonical identity 保留。
- 失敗、cancel、頁數／工具數／bytes 超限、重複 identity／cursor 均停止，回傳 complete=false 與理由。
- 走完全部頁面後一次更新完整 cache；失敗不覆寫上一份完整快照。當次 partial tools 僅供診斷，M0 不將這批新資料開放執行。
- Last complete cache 可供顯示，但標 stale/unverified。受影響 server 的新呼叫須在目前 session 驗證與 policy 通過後恢復；其他 server 繼續使用。
- Partial inventory 不觸發 removed tool、policy 孤兒清理或 legacy alias 重綁。完整有效的空清單才表示該次沒有工具。
- 不新增廣域自動 retry；取消須傳遞，close 只操作本 client 擁有的資源。

## 8. 有界資源與用詞

以下是 M0 初始設計上限，不是已量測的 runtime 現況。A0 對照既有合法資料確認；如需調整，保留有限上限並記錄原因。

| 邊界 | 初始值 | 超限行為 |
| --- | --- | --- |
| 每 server discovery | 20 pages、1000 tools、8 MiB serialized schema | complete=false，不提交完整 cache |
| 單一 schema | 256 KiB、解析深度 32、有界本機 ref 展開 | 該工具 invalid/unsupported，不暴露 |
| Discovery deadline | 使用現有 server timeout 的整體上限，缺省 30 秒；不是逐頁累加 | 取消該次 discovery，保留部分診斷 |
| Normalized raw result | 8 MiB | 明確 result_too_large，不偽裝空成功 |
| 模型文字投影 | 128 KiB，既有 OMI 更小限制優先 | 顯示 truncation 並保留關鍵限制與安全引用 |
| UI status／單筆診斷摘要 | 2 KiB／512 字元，先做 privacy projection | 安全截斷，不裁掉錯誤類別 |

Byte cap 是應用層接受／投影界線，不宣稱 SDK 在接收前就有同等記憶體上限；需用測試記錄 SDK 的實際接受邊界。

Configured、discovered、cataloged、policy registered、routable、healthy、executable 分開，附 scope 與時間。Policy 對特定參數允許，不代表該工具對任何參數都可執行。

25 個 source 宣告與 21 個登記是審查基線，不硬編碼成 runtime 成功數；OAuth 修正使可允許工具數降低是預期行為。

協定參照：[MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)、[pagination](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/pagination)。實作以實際 SDK、provider profile 與測試鎖定相容行為，不以參照頁日期要求無關 upgrade。
