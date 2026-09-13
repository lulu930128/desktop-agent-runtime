# M0 驗收與驗證命令

本文件定義 M0 的驗收規格與重跑方式。測試已進入實作；實際命令、數量與適用範圍只看 [Progress.md](Progress.md)，不能把驗收條件數當成測試通過數。

## 1. 驗證環境與證據

- Source tests 使用 synthetic store、fake session/provider、隔離暫存目錄；不得讀寫真實 memory、登入 OAuth、連 paid API 或啟動正式 GUI。
- 單元測試可 mock 外部 I/O，不 mock 掉待驗證的 policy、identity、normalization／projection。用 side-effect call counter=0 驗證拒絕。
- Loopback fixture 使用 port=0 等隔離埠，不能佔用／清理正式 port owner。
- 每份 evidence 記錄 source/config digest、測試命令與數量、結果、UTC/Taipei 時間及適用範圍。敏感內容改用 sentinel，private evidence 不進 git。
- Test file 缺失、發現零個測試、必要案例 skipped 都不算 PASS。已存在測試只可為 identity 相容更新 expected value，不能刪掉原本的安全性斷言來讓測試通過。

## 2. Source 驗收矩陣

| 編號 | 必須成立的觀察 | 階段／測試組 |
| --- | --- | --- |
| BASE-01 | Source、dirty scope、Python／SDK／provider profile 與 checkpoint 可辨識；保留 Calendar/Core 變更 | A0／基線 |
| BASE-02 | Static 宣告與 runtime discovery 分開；大小及 deadline 預設不靜默破壞目前合法工具 | A0／基線 |
| MEM-01 | Assistant 只說完成，結果是 pending_confirmation、enabled=false，正常 prompt／index 不選取 | A1／memory |
| MEM-02 | Explicit「請記住」可經受控流程保存；一般陳述／肯定句不視為保存授權 | A1／memory |
| MEM-03 | Tool success、runtime Ready、模型偽造 verified/tool_call_id 不足以 active；證據範圍與保存授權分開 | A1／memory |
| MEM-04 | Unknown／unverified／malformed status 在 manager、retriever、index、UI 一致 fail-closed；legacy missing status 有明確處置 | A1／memory |
| MEM-05 | 同內容與衝突 claim 不改既有 source、history ref、evidence、授權、confidence、status，也不復活停用／刪除記憶 | A1／memory |
| MEM-06 | 候選核准綁定內容／scope／版本；修改、重啟、停用、刪除後 prompt 與 SQLite index 無舊副本 | A1／memory |
| MEM-07 | Legacy inventory／dry-run／副本 migration 可重跑；保留人工授權、ID、時間；backup/restore 與中斷恢復驗證，不寫真實資料 | A1／memory |
| POL-01 | Unknown、拼錯 mode、scoped_auto、未登記工具拒絕；外部 call counter=0 | A2／policy |
| POL-02 | Deny aliases、缺省 mode、malformed tool/rules、NaN／Infinity 的行為明確且 fail-closed | A2／policy |
| POL-03 | Runtime 與 Launcher 共用結果；configured 不冒充 effective；不同 digest 顯示尚未採用 | A2／policy＋launcher |
| POL-04 | Confirm 使用 blocked＋reason_code，沒有虛構 pending action；status／history consumer 相容 | A2／policy＋integration |
| POL-05 | Mail OAuth 兩項工具受限；已登入 reads／本機 snapshot 更新依原範圍運作，不擴權 | A2／policy |
| POL-06 | OMI write/report/超預算拒絕，bounded read 保留；direct stream／fallback 無 policy 時不放行 | A2／policy＋integration |
| PRIV-01 | 巢狀 object/list、JSON string、URL query/header 的 synthetic code/token/state 不進 operational log／status | A3／privacy |
| PRIV-02 | Parse error、malformed dict、transport exception、traceback、短 result／error reflection 不洩漏 sentinel | A3／privacy |
| PRIV-03 | Single/group conversation、OMI stream、history event、memory excerpt 不複製 OAuth／credential sentinel | A3／privacy＋integration |
| PRIV-04 | 真正送往 fake tool 的必要參數未被遮罩，模型／Reader 仍取得有界合法證據 | A3／privacy＋results |
| PRIV-05 | Log／status／history／模型各自取 projection；unknown metadata 不自動送模型；schema/result 文字不能改 policy | A3／privacy＋integration |
| PRIV-06 | 大小限制前先做 privacy projection；舊紀錄只有盤點，測試不碰使用者紀錄 | A3／privacy |
| ID-01 | 跨 server 同名工具均存在；同 server 重複身份拒絕，不覆蓋 | A4／identity |
| ID-02 | 正確 canonical ID 解析到指定 fake server，wire name 保持原名，policy/audit 不套到另一 server | A4／identity |
| ID-03 | Alias 在 discovery 順序、特殊字元、長度截斷與同形名稱下穩定唯一；所有 provider／Prompt 皆可反查 | A4／identity |
| ID-04 | Legacy mapping 固定 owner；canonical deny 優先；missing/disabled server 不改派同名工具 | A4／identity |
| ID-05 | Canonical 化後 catalog 排序、OMI autorun/direct stream/fallback、history evidence 語意不退步 | A4／identity＋integration |
| ID-06 | 一回合 alias map 固定；schema/config 更新與舊呼叫競爭不會重新綁定到別的能力 | A4／identity＋integration |
| SCH-01 | Nested、minimum/maximum、required、array、nullable、union、local refs 的原始語意保留；不原地修改 schema | A5／schema |
| SCH-02 | Unsupported profile 明確 reject／等價 transform；Strict 與非 Strict、不同已使用 provider 分開驗證 | A5／schema |
| SCH-03 | Invalid/unsupported tool 不進 Native、Prompt、catalog 提示；其他有效工具照常可用 | A5／schema＋integration |
| SCH-04 | Actual args 在補參數後按 raw schema 驗證；Native/Prompt/direct stream 的 malformed args 不呼叫 server | A5／schema＋integration |
| SCH-05 | Digest deterministic，constraint 變更可偵測；過深／循環 ref／過大 schema 有界失敗，不遠端 fetch | A5／schema |
| SCH-06 | OutputSchema 使用既有 SDK 可用驗證；不支援／結果不符時保留錯誤，不自行補造 domain 資料 | A5／schema＋results |
| RES-01 | 多 text、mixed image/audio/resource 的類型及順序可追溯，非只取第一項 | A5／results |
| RES-02 | 只有 structuredContent、空 content、resource_link URI、embedded resource、annotations 正確保留 | A5／results |
| RES-03 | isError、protocol error、cancel、unknown execution、空成功分開；不得靠 text 位置判斷 | A5／results |
| RES-04 | OMI partial/stale/missing／provider failure 經模型、Reader、history 投影仍可見，不變成 current | A5／results＋integration |
| RES-05 | Text/resource derived views 不分叉；_meta 等未知欄位不任意外傳；URI 不自動讀取／下載 | A5／results＋privacy |
| RES-06 | Result／模型／UI 大小上限明確；超限與 truncation 有狀態，保留限制；時間為 aware UTC／monotonic duration | A5／results |
| DISC-01 | 兩頁以上資料完整收集；只有結束游標後才 complete=true | A6／discovery |
| DISC-02 | 重複／循環 cursor、重複 identity、invalid page 停止且不覆蓋 | A6／discovery |
| DISC-03 | Pages/tools/bytes/deadline 超限、timeout、cancel 均有 complete=false 與原因 | A6／discovery |
| DISC-04 | 第二頁失敗不覆蓋 last complete cache；partial 僅診斷，不新開放工具／誤判移除 | A6／discovery |
| DISC-05 | Complete empty 與 failed/partial empty 不混淆；cached 顯示未驗證，不能當 live healthy | A6／discovery |
| DISC-06 | 一 server 失敗不拖垮其他 server；cancel/close 只清理 owner 資源，consumer 不遺失完整性欄位 | A6／discovery＋integration |
| INT-01 | 真實 policy/mapping/projection 加 fake IO，覆蓋 OpenAI、Claude、Prompt 及 OMI direct stream/fallback | A7／integration |
| INT-02 | 既有 20 項 baseline 與 memory lifecycle 不回歸；四個既有 server 的宣告／合法基本讀取路徑有 fixture regression | A7／既有＋integration |
| INT-03 | Source re-audit 覆蓋表列 consumers；無裸名稱授權 fallback、raw log 或錯誤 active 路徑 | A7／source review |
| INT-04 | Diff 只含本任務；沒有 private state、無關 dependency/HTTP/Domain Router/Core schema 改動 | A7／diff review |

Source gate 要求以上全部有證據；適用性例外必須解釋並更新規格，不能默默 skipped。

## 3. Runtime／資料採用矩陣

| 編號 | 必須成立的觀察 |
| --- | --- |
| RUN-01 | Launcher root、PID/listener owner、source/config/policy digest、SDK/profile 證明載入本次修復；不只 HTTP 200 |
| RUN-02 | 真實 legacy memory 已核對／授權遷移，或經接受的檢索隔離可觀察；真實 backup/restore 範圍有紀錄 |
| RUN-03 | 桌寵與工作面板實際顯示工具執行／拒絕、安全理由、Reader／history 的來源與限制 |
| RUN-04 | Web/filesystem/mail/OMI 的有界 live read 各有結果；offline/auth_required 如實保留，未驗證的 provider 不算完成 |
| RUN-05 | 重啟／角色切換後權限一致，候選不升格、停用記憶不復活、資料不被重複寫入 |
| RUN-06 | 新 operational log/status/history 通過安全 sentinel／摘要檢查；未觸發 OAuth exchange、外部寫入、高成本刷新或重複 side effect |

受限／離線狀態可證明降級正確，但不能代替 RUN-04 的該 provider 成功讀取證據。長期離線時在 Progress 分開標記 provider 未驗證，不把 M0 整包說成完成。

## 4. 測試檔案規劃

實作階段的測試分組：

| 位置 | 驗收組 |
| --- | --- |
| Open-LLM-VTuber/tests/test_mcp_m0_memory.py | MEM |
| Open-LLM-VTuber/tests/test_mcp_m0_policy.py | POL |
| Open-LLM-VTuber/tests/test_mcp_m0_identity.py | ID |
| Open-LLM-VTuber/tests/test_mcp_m0_schema.py | SCH |
| Open-LLM-VTuber/tests/test_mcp_m0_results.py | RES |
| Open-LLM-VTuber/tests/test_mcp_m0_privacy.py | PRIV |
| Open-LLM-VTuber/tests/test_mcp_m0_discovery.py | DISC |
| Open-LLM-VTuber/tests/test_mcp_m0_integration.py | INT 與跨路徑 assertions |
| Open-LLM-VTuber/tests/test_mcp_m0_omi_path.py | 真實 BasicMemoryAgent direct stream／fallback 與 policy |
| Open-LLM-VTuber/tests/test_mcp_m0_consumers.py | Group broadcast、single history evidence、OMI worker failure |
| tests/test_mcp_m0_launcher_policy.py | 真實共用 policy helper／面板投影；不只測 FakeController |

同一組可有多項 tests；避免只驗證 helper 回傳字面值。每個高風險案例應檢查下游工具呼叫、檢索／索引或紀錄是否發生。

## 5. 命令：制定文件時只做 Tier 0

以 UTF-8 strict 讀回本目錄五份 Markdown，檢查連結、不可見 replacement character、未完成模板與 diff。New untracked files 不會被一般 git diff --check 覆蓋，另做逐檔空白檢查／no-index 檢查。不要為文件變更跑 unit、build、GUI 或 runtime smoke。

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
git diff --check -- docs/index.md docs/agent-runs/mcp-trust-security-m0
```

## 6. 命令：實作階段的 Python tests

以下 runner 解決 runtime src import path，且缺檔／零測試會失敗。A0 先用 baseline 清單；後續按修改階段執行相關組，A7 才跑完整必要清單。

```powershell
Set-Location 'C:\project\desktop-agent-runtime\Open-LLM-VTuber'
@'
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
patterns = (
    "test_tool_policy_omi.py",
    "test_tool_catalog_market_routing.py",
    "test_market_preflight.py",
)
suite = unittest.TestSuite()
for pattern in patterns:
    if not Path("tests", pattern).is_file():
        raise SystemExit(f"Required test file missing: {pattern}")
    cases = unittest.defaultTestLoader.discover("tests", pattern=pattern)
    if cases.countTestCases() == 0:
        raise SystemExit(f"No tests discovered: {pattern}")
    suite.addTests(cases)
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
'@ | ..\envs\kuro-llm310\python.exe -B -
```

A7 使用同一 runner，將 patterns 換成上述三個 baseline 檔、test_character_memory_manager.py，以及第 4 節的十個 runtime test_mcp_m0_*.py 完整檔名。不要使用空 glob 結果判 PASS。Memory tests 必須維持既有暫存 KURO_MEMORY_ROOT 與隔離 cwd。

Launcher 驗證在相應新 test 實作後執行：

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
if (-not (Test-Path 'tests/test_mcp_m0_launcher_policy.py')) {
    throw 'Required M0 launcher tests have not been implemented.'
}
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_mcp_m0_launcher_policy.py
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_work_panel_api.py
```

以上 root test 結果仍要確認測試數大於零、必要案例沒有 skipped。test_work_panel_api.py 使用隔離 loopback fixture，不能單靠它的 FakeController 宣稱已驗證真實 policy 畫面邏輯。

Syntax checks 只列實際修改的 Python 檔案；以下為常見範圍示例，不是要求每次全跑：

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
.\envs\kuro-llm310\python.exe -m py_compile `
  .\Open-LLM-VTuber\src\open_llm_vtuber\mcpp\tool_policy_manager.py `
  .\Open-LLM-VTuber\src\open_llm_vtuber\mcpp\tool_adapter.py `
  .\Open-LLM-VTuber\src\open_llm_vtuber\mcpp\tool_executor.py `
  .\Open-LLM-VTuber\src\open_llm_vtuber\mcpp\mcp_client.py `
  .\kuro_launcher\qt_controller.py
```

## 7. UI 與 runtime 驗證限制

只有實際改到 renderer contract／顯示 consumer，才在 pet-electron 跑 npm run check:renderer／npm run build:renderer；有可見 UI 風險才加實際操作／截圖。

Runtime 使用既有 owner/controller 與當時有效設定；先核對身分再探測。現有 /status、/briefing 可作基礎存活證據，但目前並不提供全部 M0 policy/schema 證據，不能直接當完成驗收。新增必要診斷時保持窄 contract，不對 renderer 暴露 session token。

Blocked／高風險案例在 fake backend 驗證零 side effect；live 只做已授權的安全讀取。不得用「測試拒絕」為理由對真實外部系統送出交易、OAuth exchange、發信、刪除或 report generation。

## 8. 已授權的限定試點與 source inventory

以下兩支 opt-in 腳本不由 unit discovery 或桌寵啟動。Inventory 只讀 source 宣告並使用 fake IO；reader 腳本啟動既有 STDIO server，根目錄固定為本計畫資料夾，工具 allowlist 固定為 workspace_info／read_file。

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_mcp_source_inventory.py --omi-adapter 'C:\project\Open Market Intelligence\agents\omi_mcp_server\server.py'
.\envs\kuro-llm310\python.exe -B Open-LLM-VTuber/tests/verify_project_reading_pilot.py --reader-dir C:\GPT_MCPtool\project_reading
```

試點不呼叫 LLM，不修改持久 registry／角色／啟動設定，不啟動 HTTP server 或重啟 Control Center。首次沙箱阻擋子程序時須經有界提升，不能改成全域放寬權限。
