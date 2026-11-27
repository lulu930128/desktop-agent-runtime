# Kuro TTS Phase1 獨立稽核工作報告

## 結果與範圍

**Phase1 Source Implemented、Targeted PASS；獨立 Reviewer PENDING；Runtime／Desktop E2E UNVERIFIED。**

依使用者固定的 [Plan.md](Plan.md) 僅修復「已有合法日文稿，被跨語 option uncertainty 錯誤靜音」及 Parser→queue 接線。Plan 原始 bytes 未改，SHA256 為 `ef72e19cf7fb90e67792936da39cbea787f7fcf338239064250d8eaf44560bad`。對齊產品 QualityBar 的完整文字、狀態誠實、單一 owner 及 Source／Runtime 分級。

沒有修改中央 `voice_service.py`、`tts_manager.py`、`single_conversation.py`、prompt、Qt／Electron／ReleasePin、Tool／MCP／Memory／DB。沒有翻譯或 judge request、固定稿、同義詞擴表、新 Parser／Queue／Manager、套件升級、服務重啟、部署、commit 或 push。驗證使用既有 `envs/kuro-llm310/python.exe`，LLM、TTS、History／Memory IO 均為 fixture；不使用真實付費 LLM／GPU。

## 基線與 WIP 保存

- Repo：`C:\project\desktop-agent-runtime`；branch `main`；HEAD `c2b3e64c27caaec8c2cba5b213444ddce0d79e03`。
- 基線時間：2026-11-03 21:22:31 +08:00。`git status --porcelain=v1 -uall` 展開後 **150 份**既有 dirty／untracked 檔案；逐檔原始 bytes、SHA256、大小與 status 存於本機收據。沒有 reset／checkout、staging 或改寫 index。
- 收尾：其中 3 份是本輪授權修改；其餘 **147 份 bytes 相同**。`unrelated_drift=[]`，HEAD／branch／index 相同。新增 1 份測試及本報告／Progress；既有 Plan 不變。
- 必須相對本輪 preimage 審核，不能把目前整份 HEAD diff 當成本輪修改。原有 speech、TTS、MCP、UI 等 WIP 均保留。

本機工程收據根目錄：[`../../../.tmp/kuro-tts-reliability-phase1-20261103/`](../../../.tmp/kuro-tts-reliability-phase1-20261103/)。它包含既有本機 WIP，不能整包加入 Git 或作公開附件。

| 收據 | 用途 |
| --- | --- |
| [Baseline.json](../../../.tmp/kuro-tts-reliability-phase1-20261103/Baseline.json)、`before/`、`index.before` | 完整 150 份原始 bytes、hash、HEAD／branch／status／index 基線。 |
| `Baseline.diff`、`Baseline.cached.diff` | 原有 working tree／staged diff；不是本輪 patch。 |
| [TaskDiff.patch](../../../.tmp/kuro-tts-reliability-phase1-20261103/TaskDiff.patch) | 相對 preimage 的 2 份 source 與 1 份既有測試局部修改；新增測試另直接閱讀。 |
| [FinalChecks.json](../../../.tmp/kuro-tts-reliability-phase1-20261103/FinalChecks.json)、`Syntax.json`、`DiffCheck.json` | WIP／HEAD／index／Plan、syntax、UTF-8／diff 核對。 |
| `audit.py`、`replay.py`、`check_source.py` | 可檢視的本機收據程式；replay 僅在獨立程序記憶體載入 preimage，完全不覆蓋工作樹。 |

`Baseline.json` SHA256：`252f4bcd93030657e82b7b676754885d4d68864d3ced0811dbd1ab962c20d4fd`。

`TaskDiff.patch` SHA256：`1cfd768860adad4bbf53adcedfcd76c1f3e33af47be319f03f3358c7528ef7d2`。

## 事件核對與修前重現

實際既有日誌：`launcher_logs/llm/2026_11/03/2026-11-03_01-24-46_kuro_01/llm.err.log`。

- 第 280 行、01:27:16：`route=dual_lane`、`lane_state=option_unverified`、`stage=required_anchor`、`anchor_index=1`、4 anchors／1 semantic segment、`bridge_requests=0`。
- 第 375–379 行、01:28:51–56：另一回合 `ready` → `tts_request` → `tts_complete available=True` → `websocket_audio_sent`。這只能證明舊回合曾送出音訊，不能證明新補丁載入或 Electron playing。
- [IncidentMetadata.json](../../../.tmp/kuro-tts-reliability-phase1-20261103/IncidentMetadata.json) 僅摘錄上述結構化 timing metadata，沒有複製私人對話、語音稿或工具 payload。

先於修改 production source 執行新 fixture 的失敗測試：`Reproduction.log`／`Reproduction.json` 保存 **2 個測試、6 個 subtest failure**，均為舊 `option_unverified` 不符合新的 soft-state 契約。修前既有 semantic suite 則為 **38/38 PASS**（`BaselineSemantic.*`）。

日誌 metadata 不包含完整 private v2 原文，所以使用自行撰寫的「你好／我好餓／該不該吃宵夜」synthetic responses 重現同一分支；宵夜案例維持 **4 anchors、1 segment、index 1 首次 unknown**。不宣稱逐字重播原使用者回應。

保存的 preimage 在獨立程序內再次重播可得到：

| fixture | 修前 Parser／queue | 修前 TTS mock | 修後 Parser／queue | 修後 TTS mock |
| --- | --- | --- | --- | --- |
| 你好 | `option_unverified`，text 空 | 0 | `semantic_unverified`，原稿保留 | 1，完全相同日文 |
| 我好餓 | `option_unverified`，text 空 | 0 | `semantic_unverified`，原稿保留 | 1，完全相同日文 |
| 該不該吃宵夜 | `option_unverified`，text 空 | 0 | `semantic_unverified`，原稿保留 | 1，完全相同日文 |

原始收據：[BaselineReplay.json](../../../.tmp/kuro-tts-reliability-phase1-20261103/BaselineReplay.json)、[FixedReplay.json](../../../.tmp/kuro-tts-reliability-phase1-20261103/FixedReplay.json)。兩者每案例僅 1 次主 LLM fixture、0 Bridge。`Reproduction.log` SHA256：`22be7813c7d0535e97cd577ce0414ebf29b3bbacc9d3d09ca11f5f2375ec7f8e`。

## 根因與局部修復

1. `_option_supported` 原本只有 bool；有限 topic／verb 證據無法比對自然中日表述時，也回 false，與已知漏選項／否定混在一起。現在回 `True / False / None`：沿用既有已識別行動的保守檢查；未知跨語 evidence 回 None。沒有新增詞彙規則。
2. `validate_semantic_lane` 只把 None 收集為 `soft_failures`，保留 `rule_id=option_unverified`、stage 及 anchor index；不提前成功。所有 required anchor、關鍵數字／狀態、Display coverage 及最終文字 guard 跑完後，才回 `semantic_unverified`。已識別行動漏掉／否定仍沿用硬拒播 `option_unverified`，不把所有原 false 放行。
3. Parser 同時為 `ready`／`semantic_unverified` 保存合法 text。未知狀態仍維持 unknown，沒有改成 ready。
4. queue 接受兩種可播狀態，繼續檢查文字、locale、voice availability 及 pronunciation。文字檢查通過不會把 semantic state 升格 ready；送出不含 transcript 的 `speech-status: degraded / semantic_unverified` 與結構化 validation。保留 contract／lane_state／reason／counts／tts_chunks／bridge_requests。
5. 沿用既有 TTSTaskManager、最多三段、群組 fail-stop、cancel、終結 ack；沒有修 missing 的新旁路。

## 修改清單與精確身分

| 檔案 | 本輪修改 |
| --- | --- |
| `Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py` | option 三態、soft diagnostics、後續硬檢查、Parser text 保留。 |
| `Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py` | 可播狀態接線、pronunciation 後保留 unknown、degraded machine status／counts。 |
| `tests/test_tts_reliability_phase1.py` | 新增 12 個定點測試，含三自然聊天與完整 conversation→TTS mock、反例及生命週期。 |
| `tests/test_speech_semantic_alignment.py` | 只更新既有「未知日文→英文選項」那一個直接相關 assertion，另驗證 text 與 soft reason；其他原有拒播預期不變。 |
| `docs/agent-runs/kuro-tts-reliability-20261103/Progress.md`、本報告 | 進度與獨立可稽核交接。 |

| 檔案 | preimage SHA256 | 最終 SHA256 |
| --- | --- | --- |
| `speech_presentation.py` | `c4700057e1a1a094aeed2487eddd798c20ebaaf7441264e9892ca3f763b32e21` | `f0d4e5376d018b4b820e33e15e81d253b83b06c7e8a7ead31c4a226c42807bb0` |
| `conversation_utils.py` | `39a08036085f17bfb1ada1ad0ef4808b9505bc723086f838b8dbd381bf070a0b` | `ad746955b097fdefaf5f6b345fa19497d8e2b707e2f05776b5afbf57a179c55d` |
| `test_speech_semantic_alignment.py` | `edf71fa7006c2b9ce50caebaf8228edda2517a2652d13012af24c757a73272c8` | `aa4ca0a5400e255cf8712446dcbdae1bd2da8927eb903ce5f8dc9e7549a718eb` |
| `test_tts_reliability_phase1.py` | 新增，原不存在 | `eb89723bbf471132170666a11feffb9f9bdca4610d491a53f46df10900f4166a` |

## 驗證命令與結果

從 repo root 執行：

```powershell
$env:PYTHONPATH = "$PWD\tests;$PWD\Open-LLM-VTuber\src;$PWD\Open-LLM-VTuber;$PWD"
$env:PYTHONIOENCODING = 'utf-8'
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_tts_reliability_phase1.py -v
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_speech_semantic_alignment.py -v
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_multilingual_speech.py -v
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_first_speech_latency.py -v
```

實際由本機 `audit.py run <label> discover ...` 以 subprocess bytes 留存 UTF-8 stdout／stderr、exit code 與 log SHA；等價 suite 命令如上。

| 最終收據 | 結果 | 主要驗證 |
| --- | --- | --- |
| `FinalPhase1.log/json` | **12/12 PASS** | 三自然聊天、硬錯誤優先、unknown 不偽稱 ready、發音／voice guard、三段成功／fail-stop／ack、cancel。 |
| `FinalSemantic.log/json` | **38/38 PASS** | schema／來源／引用、價格／停損／負號／比例／錯誤碼、failure／blocked／unverified／否定、漏選項、technical payload、Display lossless 及 mock central WAV／WS。 |
| `FinalMultilingual.log/json` | **30/30 PASS** | v1、多語設定、正常路徑零 Bridge、Display／History／Memory、missing／異常與取消。 |
| `FinalLatency.log/json` | **10/10 PASS** | 既有切句、順序、失敗完成 ack；preload 只跑原有 mock，不呼叫正式服務。 |

**合計 90/90 PASS**；重播及重跑不重複加總。沒有未解的測試失敗。

中途 `SemanticAfter.*` 曾有 1 個直接契約變更造成的舊預期失敗：未知日文→英文選項原預期硬拒播。只將該相關 assertion 改為新 `semantic_unverified`，補 text／soft reason 檢查；後續 38/38 PASS。其餘 baseline tests 未為湊綠改寫。第一次 baseline wrapper 的 console 顯示遇 cp950 emoji 編碼錯誤；子程序早已正常 exit 0、38/38 PASS 並保存 UTF-8 原始 log。只修本機 wrapper 的 stdout encoding，沒有當作產品失敗或掩蓋測試。

另外執行：

```powershell
& '.\envs\kuro-llm310\python.exe' -B '.tmp\kuro-tts-reliability-phase1-20261103\check_source.py'
& '.\envs\kuro-llm310\python.exe' -B '.tmp\kuro-tts-reliability-phase1-20261103\replay.py' baseline
& '.\envs\kuro-llm310\python.exe' -B '.tmp\kuro-tts-reliability-phase1-20261103\replay.py' fixed
git diff --check -- Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py tests/test_speech_semantic_alignment.py
```

4 份 Python 使用內建 `compile()` 做 syntax，無 pyc 輸出；scoped Git diff、所有新檔 UTF-8／行尾空白及文件相對連結檢查 PASS。沒有為本任務跑全 repo、UI build 或 e2e。

## 限制與 Reviewer 交接

- **有限詞彙檢查不能證明完整跨語語意。** 未識別選項即使實際漏譯、換話題，可能仍可播，但必定是 `semantic_unverified`；新增反例明確覆蓋「只有問候、無法證明選項」仍是 unknown，不能叫 verified。未增加 LLM judge 或大型字面引擎。
- 已識別 topic 的行動若未通過原有 verb／negation 規則，保守維持硬拒播，包含部分規則無法辨認的自然同義表述。這是本輪窄範圍退化，未承諾消除所有 false reject。
- 維持原有 critical-value／status 規則，沒有宣稱支援所有數字口語、因果、主詞、引用或否定範圍；`ready` 也不是語意完全等價的數學證明。
- **missing 仍是獨立未解問題**。本輪不產生缺失的日文稿，不自動叫 Bridge；既有長清單畫面 acknowledgment 未變。
- 新 degraded event 為既有 WS machine 訊息；未修改 Qt／Electron，沒有宣稱 UI 已提供新徽章或驗收了顯示方式。
- 完成的是 Source 與 synthetic/mock 證據，沒有建立／選擇 release、驗證正式 process 載入或量測真實 TTFA。

主 agent 已對照 TaskDiff 與反例自行複查；**沒有啟動 subagent，也沒有宣稱完成獨立 Reviewer 驗收**。Reviewer 請先核對上列 hash 與 preimage，再審查「未知只降級、後續硬錯誤不得被蓋過、queue 不洗成 ready」及新增測試。可在獨立程序執行 replay 與四個 suite；不需重啟 runtime 或使用真實模型。

後續 Runtime／桌面驗收另待授權：先確認載入精確 source，再以一般聊天、錯價／失敗／未驗證、缺 footer 做真實對照；分別保存中央合成、WS、Electron playing、人工日文語意／音質／嘴型／取消與 TTFA 證據。獨立 Reviewer Reviewed、Runtime Adopted、Desktop E2E Verified 三個 gate 目前均未完成，不能由本報告自動升級。

## 局部回復方式（未執行）

先核對最終 SHA 與是否有後續 WIP，再逐 hunk 逆轉 TaskDiff 的本輪修改；新測試與報告可留作證據。遇後續並行變更，人工比對 hunk，不以 HEAD、整檔 preimage、reset 或 checkout 覆蓋現有工作。此說明不授權部署、重啟、commit 或其他階段。
