# 進度

狀態：**Source 修復與定點驗證 PASS；既有兩筆 Baseline Failure 保留；新 signed Frontend Release BLOCKED；Runtime UNVERIFIED_NOT_OPERATED；無關 WIP 全量 byte 核對 UNVERIFIED。**

## 修正與重現

- Repo `main`、HEAD `c2b3e64c27caaec8c2cba5b213444ddce0d79e03`，開始時 142 個 dirty 檔案。匿名 Display fixture 修正前 6/6 失敗；主因為 adapter 裁掉 chunk 換行、將重複詞當字幕重送、完整 snapshot 被附加至片段、Display 被截長。修正後 6/6 PASS，包含 scope／reconnect 與 CRLF、空白、重複詞。
- **先驗證 adapter-only**：未改 frontend 時，pin 對應的原始合併方法已能在 live→history 非同步重整後保持單一完整 AI row。另兩項 fixture 仍失敗：不同回合的相同問答被省略、舊 async history 覆蓋新 scope，因此依使用者授權補最小 frontend Source 修正。
- frontend 只在既有 renderer 內以觀察到的回合 prefix／timestamp／exact content 合併，無全域 whitespace collapse；讀取 generation 隔離晚回覆。涵蓋相同問答連續回合、rolling history、partial snapshot、out-of-order reads 與 reconnect。
- Reviewer 的直接 history 套用 gap 已獨立重現：完成 A 後直接 `applyHistoryPayload(B)` 會帶入 A 的 live rows。修正前 9/10；只在該方法清除舊 live turn／latest text、更新讀取與 scope generation，修正後 **10/10 PASS**，晚到的 A read 不能覆蓋 B。
- 主 response prompt 統一 v2，保留完整 Display，private footer 使用既有 `anchors`／`speech`。未修改 SpeechLaneParser 的既有 v2 validator，未更動 GPT-6 API／MCP／ToolPolicy／memory owner／實際 TTS engine。
- 長 inventory fixture 經真實 agent、parser、conversation、TTS queue，僅主 LLM／TTS／WS／storage 使用 mocks：一輪主 completion、v2 `ready`、`tts_chunks=1`、Bridge requests=0、短日文 TTS、完整 Display／History／Memory；沒有新增第二次翻譯／摘要 API。
- missing-only fallback 僅在 **完整回應、dual_lane、ja-JP、至少 800 字且 6 個條列**時使用既有固定句 `詳しい項目は画面に表示しています。`。這是詳情在畫面的 acknowledgment，**不是摘要**。保留 `lane_state=missing` 與 `delivery=display_acknowledgment`，WS status 保留 reason=missing。malformed／rejected／explicit empty speech、短回答、未完成 stream、非 ja-JP 仍無 TTS；不照讀原清單。

## 驗證結果

證據根目錄：`.tmp/kuro-display-speech-20261031/`。全部為 Source／隔離 fixture，無正式 Runtime acceptance。

| 範圍 | 基線 | 修正後 |
| --- | --- | --- |
| Qt speech settings＋candidate＋existing window＋transport | 77 tests：76 PASS、1 ERROR | 77 tests：75 PASS、1 原有 ERROR、1 Release boundary BLOCKED |
| 既有 semantic／multilingual／latency | 78/78 PASS | 78/78 PASS |
| 既有 pronunciation pipeline | 47/47 PASS | 47/47 PASS |
| 既有 frontend／history list | 29 tests：28 PASS、1 FAIL | 29 tests：28 PASS、同一原有 FAIL |
| 新 Display fixtures | 6/6 FAIL | 6/6 PASS |
| 新 frontend merge／lifecycle | 初始 4 tests：1 PASS、3 FAIL；adapter-only 2 PASS、2 FAIL | 10/10 PASS |
| 新 inventory Speech | 初始 6 tests：4 PASS、2 FAIL | 7/7 PASS |
| frontend typecheck | PASS | PASS |
| Python source syntax、UTF-8 讀回、task-only diff check | — | PASS |

兩筆原有 Baseline Failure，**不屬本輪新回歸**：

1. `test_qt_web_existing_window.RealOwnerIOTests.test_full_constructor_reads_keep_core_bytes_and_single_chat`，line 439：`KeyError: confirmation_available`，來源 `getTools` 既有回傳。
2. `tests/qt_web_frontend.test.cjs` line 156：`src/owner-presentation.ts` 與目前 pin 的 lineage hash 不同，基線已存在，未改動該檔案。

新增的 Release gate 阻塞是 `test_signed_bundle_bytes_are_frozen_and_wrong_pin_is_rejected` → builder `lineage()` 拒絕 `Immutable Git source mismatch: src/work-panel/main.ts`。不能當作新 frontend 已可發佈，也沒有改測試或 gate 讓它變綠。

精確命令以 repo root 為 cwd，使用既有 Python 環境與以下 env：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = 'C:\project\desktop-agent-runtime\tests;C:\project\desktop-agent-runtime\Open-LLM-VTuber\src;C:\project\desktop-agent-runtime\Open-LLM-VTuber;C:\project\desktop-agent-runtime'
& .\envs\kuro-llm310\python.exe -B -m unittest test_chat_speech_settings_qt test_qt_web_candidate test_qt_web_existing_window test_qt_web_transport -v
& .\envs\kuro-llm310\python.exe -B -m unittest test_speech_semantic_alignment test_multilingual_speech test_first_speech_latency -v
& .\envs\kuro-llm310\python.exe -B -m unittest discover -s Open-LLM-VTuber/tests -p test_tts_pronunciation_pipeline.py -v
& .\envs\kuro-llm310\python.exe -B -m unittest test_qt_display_stream -v
& .\envs\kuro-llm310\python.exe -B -m unittest discover -s Open-LLM-VTuber/tests -p test_speech_long_inventory.py -v
node --test tests/qt_web_frontend.test.cjs tests/history_list_frontend.test.cjs
node --test tests/qt_display_history_frontend.test.cjs
npm.cmd --prefix devtools/original-git-web-host-20261010/frontend run check
```

`Final-*.log` 保存 speech、Qt、Display 與 inventory；`DirectHistoryFinal-*.log` 為 reviewer 最後局部修正後的 frontend／merge／typecheck。`DirectHistoryRed-merge.log` 保存對應 red fixture。

## Release／Runtime

- 未執行新 signed build、未建立／尋找 signing key，未改 builder、immutable 檢查、ReleasePin 或 signed assets。正式 build 因 immutable source boundary **BLOCKED**，本輪只完成 typecheck／source tests，沒有可部署的新 frontend artifact。
- 目前 pin fingerprint：`1ae1327c3f02836510f5712e7783c03a6b3a883e9f0d8d15d165247a14ae9a9a`；manifest SHA-256：`d4837396ea4e6c79bd19c31573098978824ef04e1eb5b23ed6fdcfac17f92396`。
- `VerifiedOwnerBundle.load` 對目前 pin 的 5 個資產完成 Ed25519／manifest／asset 驗證，**PASS**。pin、builder 與 Speech parser 的 preimage bytes 均相同。詳見 `Release.json`、`Audit.json`。
- 正式 Runtime：**UNVERIFIED_NOT_OPERATED**。沒有 restart／stop／deploy、付費 LLM／實際中央 TTS call、stage／commit／push；由使用者自行走既有正式流程驗證。frontend Source lifecycle 修正尚不在目前 signed bundle 內。

## Task-only 變更與 WIP 證據限制

共 12 個 task files：6 個 Source（adapter、main.ts、兩個 speech prompts、conversation_utils、single_conversation）、3 個新 fixture tests、此目錄 3 個任務文件。`Task.diff` 是相對本輪 scoped preimages 的差異，排除繼承的 WIP；`Audit.json` 列出完整路徑與新增／刪除行數。

**收據錯誤已明列**：最初的 `Baseline.json` 含 142 個 dirty 檔案 hash，後被本輪臨時 validation runner 的同名結果覆寫。原始 status、9 份 scoped preimages、scoped baseline diff 與工具輸出中的初始 HEAD／index hash 仍在。現已將結果分名為 `*-Validation.json`，`Baseline.json` 明確記錄遺失欄位，沒有冒造原始 hash。

已確認 HEAD／index 不變、非 task 的 Git status entry 不變、保護檔案 preimage 相同、task-only diff 無跨界變更。本輪沒有寫入無關 WIP；但因原 hash 清單遺失，**137 個非 task dirty 檔案的全量 byte-preservation 證據為 UNVERIFIED**，不能把 status 相同當作逐檔 hash 通過。`Final-dirty-hashes.json` 僅為收尾快照，不能追認基線。
