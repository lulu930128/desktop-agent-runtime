# Kuro 語意對齊雙輸出 v2 — 實作紀錄

狀態：**G0–G4 Source Ready／Targeted PASS；Runtime Pending；G5 真人語意與音質驗收 UNVERIFIED**。

本輪只改 Source、synthetic fixtures 與本紀錄。沒有正式 LLM／TTS 請求、Kuro／中央 TTS restart、release、部署、設定切換、commit 或 push。先前 v1／熱載 G5 的現場結果不算本輪 v2 的 runtime acceptance。

## 固定規格與工作識別

- 規格沿用本目錄 `Plan.md`，未改寫；SHA-256：`b35fa14dc07c9087e955bd2da08d5d40255afff7829c5531b4eae7f47a727b34`。
- Repo：`C:\project\desktop-agent-runtime`，branch `main`，baseline HEAD：`c2b3e64c27caaec8c2cba5b213444ddce0d79e03`。
- G0 收據時間：`2026-10-31T13:27:29.165643+08:00`；完整展開後共 **112** 個既有 dirty／untracked 檔案。沒有重置工作樹或變更 index。
- 本輪識別：`kuro-speech-semantic-alignment-20261031`。使用者指定 `gpt-6.1-sol / xhigh / Standard`；獨立 Reviewer `/root/speech_diff_review` 明確以 `gpt-6.1-sol / xhigh` 建立。主會話 host 未提供可稽核的實際 model／speed 欄位，不宣稱已驗證 Standard；本輪沒有操作 Fast 切換。
- 並行 MCP job：`fe723c86-9eef-4d65-b1d1-ccf09b94aac0`；本輪未修改 `mcpp/*`、tool policy、Tool Router、OMI 或外部 API。

## G0：基線與 WIP

工程收據位於 `.tmp/kuro-speech-semantic-alignment-20261031/`：

- `Baseline.json`：HEAD、branch、status、index SHA、112 份既有 WIP hash，以及 11 份具體 source／Plan 的 hash／bytes。
- `before/`：上述 11 份檔案的原始 bytes，包含原有 dirty v1 parser、queue、Agent、prompts、tests、Plan。
- `Baseline.diff`、`Baseline.cached.diff`：修改前工作樹／staged diff。
- 修改前 `test_multilingual_speech.py`：**30/30 PASS**，見 `BaselineTests.log`。
- 收尾 `FinalChecks.json`、`TaskDiff.patch`、`ConcurrentAgentDiff.patch`、`TaskFiles.json`：本輪允許範圍、原始 bytes hash、固定 Plan／index／HEAD 核對及並行差異分離。不要把整個 dirty HEAD diff 當成本輪 patch。

`basic_memory_agent.py` 的事實需特別區分：本輪曾短暫以最小 hunk 將 `display_lane_text` 呼叫增加 `strip_control_prefix` 參數，並非「整輪從未寫入」。後續並行寫入使該 hunk 消失；本輪沒有重套或還原該檔。目前既有 parser 在沒有 footer 時保留前綴，已不需要 Agent 接線。**最終本輪 patch 排除 Agent 核心**；當前 `_add_message` 仍是原本 `display_lane_text(text_content)`。並行新增的 `require_tool_evidence`／tool-result gating 等差異保留於原檔，另存 `ConcurrentAgentDiff.patch`，不屬本輪實作或驗收。

Agent baseline SHA：`af3d4cff6d935593e64a1da2b2e2b7473e61e3bda3c6cd2304f5d169d3573d82`；收尾核對 SHA：`808c8425bb20ab1a1dac3c2abcb1ea678f2b7e7a3672cb6f50a4eea75866d766`。本輪未用 baseline 覆蓋並行版本；這兩個 hash 不相等，不能宣稱整份 Agent byte-exact 未變。

## G1–G3：已完成行為與修改範圍

| 檔案 | 本輪內容 |
| --- | --- |
| `Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py` | 漸進擴充既有 `SpeechLaneParser`，同時接受 v1／v2 marker；v2 schema、來源、coverage、關鍵資訊檢查由既有 `SpeechPolicyEngine` 負責。 |
| `Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py` | 僅新增 contract／anchor count／semantic segment count 診斷；保留既有 queue、最多三段 TTS、有序群組 fail-stop、cancel 與 ack。 |
| `Open-LLM-VTuber/prompts/utils/speech_lanes_prompt.txt` | 同次主 LLM final response 生成完整 Display＋v2 anchors／speech segments／emotion；不新增翻譯、judge 或 repair request。 |
| `Open-LLM-VTuber/prompts/utils/live2d_expression_prompt.txt` | 舊 inline 表情規則限定 legacy；雙輸出使用私有 emotion，不要求 Display 前綴 `[neutral]`。 |
| `tests/test_speech_semantic_alignment.py` | 新增 30 個 synthetic parser／conversation tests；mock LLM、TTS、history、memory、工具執行及播放完成。 |
| 本 `Progress.md` | 基線、定點結果、並行檔案事實、盲點及 rollback／人工驗收交接。 |

沒有新增 Manager、Parser、Queue、DB、UI 設定或 JSON Schema source of truth；沒有修改 `service_context.py`、`single_conversation.py`、`tts_manager.py`、實體 Pet／Qt UI／signed bundle 或中央 TTS。

v2 footer 上限維持 12,000 characters；最多 12 個 anchors、source 每個最多 400 characters、最多 8 個語意 segments、合併口播最多 4,000 characters。每個 source 必須精確出現在同次 final Display；required ID 必須引用、未知／重複 ID 拒絕。每段先通過 SpeechPolicyEngine 的技術載荷與語言檢查，整份驗證成功才進入既有 queue，不會先播放通過的前半段再補驗後半段。

guard 另外檢查可識別的失敗／阻擋／未驗證／stale／部分缺失／決策性否定、重要價格／停損／正負／百分比／錯誤代碼，以及各選項實際行動。required source_ids 全齊但日文只說 web 查詢、清單僅在畫面或不能確認，均拒絕；一般聊天可無錨點。`這部分可以直接改，沒有其他問題`、普通技術說明與 `I can't wait...` 不會被寬鬆「部分／不足／沒有」規則全面靜音。

完整 Display 有先失敗後成功時，允許同句保留轉折；Display 只有失敗而口播擅加成功仍拒絕。選項接受 `確認ができます` 與獨立 caveat，不把後面「結果不保證」誤當選項本身不可執行。

Markdown fenced／inline code、兩版 marker 字面、URL、path、JSON、log、table 保留在 Display／History／Memory；語音必須由同次 LLM 提供自然描述，不能靠刪字拼接技術原文。私有 footer 不進 WS／History／Memory／tool args，emotion 透過既有事件傳遞。absolute BOL footer 也會被私有化；沒有 Display 的 v2 為 `empty_display`，不生成聲音。

只有異常的 canonical leading emotion tag 會暫存最多 4,096 characters 的 Display context，等 real footer 後排除 Markdown reference definition 再剝除；正常無 tag 回應維持原本 progressive streaming。無 footer、bare token、reference link、inline／fenced literal 或超過暫存界線的歧義前綴保守保留，不為刪標籤破壞文字。

失敗／缺 footer／schema／來源／coverage／語言／technical payload／一致性 guard 不過，一律保留 Display、發 machine-readable reason、略過本輪 Speech，**不會自動切 Bridge、換模型或呼叫第二個 LLM**。v1 parser 與 `legacy_bridge` 仍可用。

## G4：定點驗證與獨立 review

使用既有環境 `envs/kuro-llm310/python.exe`，明確設定 repo root、`Open-LLM-VTuber`、`Open-LLM-VTuber/src` 為 PYTHONPATH；沒有安裝或更新套件。

| suite | 最後結果 |
| --- | --- |
| `tests/test_speech_semantic_alignment.py` | **30/30 PASS** |
| `tests/test_multilingual_speech.py` | **30/30 PASS** |
| `tests/test_first_speech_latency.py` | **10/10 PASS** |
| `Open-LLM-VTuber/tests/test_tts_pronunciation_pipeline.py` | **47/47 PASS** |
| 本輪 3 份 Python source／test 的內建 `compile()` | **PASS**；不寫 pyc。 |

合計 **117/117 PASS**。一輪 LLM、既有 tool continuation、正常路徑 bridge_requests=0、完整 Display／History／Memory、私有 emotion、無 Display／malformed／unknown ID／無來源、取消、三段順序、首段失敗 fail-stop 與最終 ack，均為 synthetic／mock 證據，不是正式 runtime acceptance。

精確 suite 命令模式：

```powershell
$env:PYTHONPATH = 'C:\project\desktop-agent-runtime\Open-LLM-VTuber\src;C:\project\desktop-agent-runtime\Open-LLM-VTuber;C:\project\desktop-agent-runtime'
& 'envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_speech_semantic_alignment.py -v
& 'envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_multilingual_speech.py -v
& 'envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_first_speech_latency.py -v
& 'envs\kuro-llm310\python.exe' -B -m unittest discover -s Open-LLM-VTuber/tests -p test_tts_pronunciation_pipeline.py -v
```

可重現 runner、原始 UTF-8 logs、`Validation.json`、`Syntax.json` 都在上述 `.tmp` 收據目錄。早期 CRLF prefix／HTTP code 字界／共享日文動詞結尾的測試失敗已修正，最終結果無未解測試失敗。PowerShell 首次 log／console encoding 問題已改以 Python subprocess bytes 保存 UTF-8，不把工具輸出編碼錯誤算成產品 PASS。

獨立 Reviewer 使用 before snapshots 相對本輪 diff，11 份 snapshot hash 全部吻合，未把 MCP dirty HEAD diff 當本輪；最終 **22/22 parser tests**、另 10 個反例與 2 個 legacy 無 footer 案例符合預期，無尚未修復的重要 finding。這些獨立重驗不重複加進 117。Reviewer 確認 source SHA：`e0783c0dfe6807296a63d840d278738a5265fe4c44233a0606c737bca54263e9`。

收尾另做 scoped `git diff --check`、新增檔／prompt／本紀錄 UTF-8 讀回與新增行尾空白檢查；結果及 SHA 以 `FinalChecks.json` 為準。不跑 Qt／Electron build、不擴測 MCP。

`2026-10-31 13:46 +08:00` 最後核對：**HEAD／branch／index 未變、Plan SHA 未變、既有 frozen v1 文件 bytes 未變、scoped diff check PASS、UTF-8 PASS、新增行尾空白 0**；正式 parser hash 與 Reviewer 檢查版本一致。相對 G0 偵測到的非本輪 WIP 漂移為 `basic_memory_agent.py`、`Open-LLM-VTuber/tests/test_no_tool_query_truth.py`、`Open-LLM-VTuber/tests/verify_shared_mcp_routing.py`，均未放入本輪 `TaskDiff.patch`；除前述曾短暫存在而已消失的 Agent speech hunk，本輪沒有對這三檔套回 baseline 或改寫並行內容。最終 Agent 呼叫沒有本輪 `strip_control_prefix` hunk。

## 已知限制

- **結構檢查與有限詞彙／數值檢查不等於日文語意等價。** `ready` 是可交給既有 TTS 的 source 結果，不是跨語語意已獲證明。
- guard 不理解完整因果、時間順序、主詞／工具身分、反諷、引用、複雜否定範圍與所有前提。完整 Display 的其他成功敘述可能放寬局部成功衝突；這是本輪有界方法的盲點，仍須人工對照。
- 選項 action 詞表只涵蓋少量常用動作；未知跨語選項可能 `option_unverified` 靜音。含詞彙／動詞也不能證明行動對象與含義完全相同，不能只因 ID／詞彙命中宣稱語意正確。
- 數值只比較阿拉伯數字／部分正規化及價格角色。日文／中文口語數字、單位換算、同義價格角色與複雜比率可能被拒絕或無法驗證；不強迫朗讀所有表格數字。
- technical／prose 邊界是有限 Markdown／payload 規則，並非完整 Markdown AST 或程式分析。無引號、無 code markup 的 leading `[neutral]` 與真正控制前綴仍可能有歧義；prompt 已要求 requested literal 使用 inline／fenced code。超過 4,096 characters 的異常前綴保留標籤，優先保存內容。
- locale 檢查只有字元／script guard，不能證明流暢日文。新增 anchors 帶來的真實 token／延遲成本、發音／標點／縮寫、音色、第一聲、播放與嘴型均未在本輪量測。

## Source、Runtime 與下一輪人工驗收

Source 已寫入正式 checkout 的既有 owners；**沒有建立／選擇 installed release、沒有重啟或驗證載入新 source**。Runtime Pending 不能寫成 runtime FAIL，也不能用 source、測試、既有 listener 或此前 v1 G5 結果宣稱 v2 已改善。

G5 留給使用者後續在正常載入本輪 source 的 Kuro 中進行：短聊天、URL/code/log 技術問題、工具失敗／未驗證、web／診斷清單兩選項、關鍵價格／停損、先失敗後成功各一輪。對照完整 Qt Display、既有安全觀測下的私有 v2 segments／中央 TTS input 與實際聽感，確認沒有漏掉第二選項或把失敗模糊化；另驗 `[neutral]`、emotion、取消／ack 與日文自然度。真實音質／語意改善及 runtime adoption 需這一步才可認定。

## Rollback（本輪未執行）

1. **最小 v1 rollback**：核對 `FinalChecks.json` 的當前 hash 與後續 WIP 後，只將 `speech_lanes_prompt.txt` 還原為 `before/Open-LLM-VTuber/prompts/utils/speech_lanes_prompt.txt` 的 frozen v1 bytes。現有 parser 仍接受 v1，queue／TTS／設定／History／Memory 不動；不需要新增 UI 控制或自動呼叫 Bridge。v1 不具備本輪 v2 semantic guard，需明示其語意限制。
2. **完整 Source rollback**：逐 hunk 逆轉 `TaskDiff.patch` 中本輪 4 份正式 source／prompt；新增 test／Progress 可保留為歷史證據。先確認檔案沒有後續更動，若有則人工比對 hunk。不要用 HEAD checkout、reset、整目錄覆蓋或 baseline 整份 Agent 覆蓋。
3. `basic_memory_agent.py`、所有 MCP 並行變動、原 frozen v1 Plan／Progress／Evidence、TTS manager／中央模型、Qt bundle、設定與私人資料均不在本輪 rollback 範圍。若要正式換版或 lifecycle 操作，需另循原有 owner；本紀錄不表示已授權或已執行。

本輪工程工作於文件與最後 WIP／diff 核對後結束；不繼續新增功能或測試範圍。
