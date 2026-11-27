# Kuro v2 靜音回歸 — 定點修復紀錄

狀態：**G0–G4 Source Ready／Targeted PASS（125/125）；Runtime Pending；G5 正式套版、Electron playing 與真人聽感 UNVERIFIED。**

唯一規格為本目錄 `Plan.md`。原 `kuro-speech-semantic-alignment-20261031/{Plan,Progress}.md` 保留原狀。本輪未重啟、停止、部署 Kuro 或中央服務，未呼叫真實 LLM／GPU service，未 commit／push，未更改全域速度／模型設定。Standard 為使用者要求；host 未提供可稽核的實際 speed/model 欄位，不宣稱已量測。

## G0：基線與可重現根因

- Repo：`C:\project\desktop-agent-runtime`，branch `main`，HEAD `c2b3e64c27caaec8c2cba5b213444ddce0d79e03`。
- 收據時間 `2026-10-31T14:07:37.839217+08:00`；121 個既有 dirty／untracked 檔案。收據 `.tmp/kuro-speech-v2-silent-regression-20261031/Baseline.json` 保存 status、index SHA、既有 dirty 檔案 hash、10 份受影響／保護檔案 hash；`before/` 保存原始 bytes，`Baseline.scoped.diff` 保存本輪候選檔案的既有 diff。未 reset／checkout／revert 其他 WIP。
- 新 Plan SHA-256：`e8764947dbdfa0320972d08920739f94738298a8472c072b4f5d17139c51a347`。
- 原 source `speech_presentation.py` SHA-256：`e0783c0dfe6807296a63d840d278738a5265fe4c44233a0606c737bca54263e9`。
- 原有 semantic suite：**30/30 PASS**。新增 synthetic reproducer、尚未改 source 時：35 tests，**5 failures、1 error**；2 個技術名稱（Node.js／Next.js）、3 個自然日文選項句式被錯殺；error 為預期尚不存在的診斷欄位。詳見 `Baseline-Validation.json`／`Red-Validation.json` 與各 UTF-8 log。
- technical 原因：副檔名 regex 在自然句內命中 Node.js／Next.js；並不需要實際路徑或 code。option 原因：`か、` 切斷共用肯定句尾，動詞表不認 `できる` 與 `チェックできます`。
- **正式兩輪的被拒原文未取得**；13:57:58 `technical_payload`、14:00:13 `option_unverified` 與未發 TTS request 為使用者提供的獨立證據。本輪只證明同類 validator 誤拒可重現，不能假稱正式模型當時輸出了完全相同的字串；模型若真的複製 raw payload，仍屬不合約並維持拒絕。

## G1–G3：修改與判斷

- `speech_presentation.py`：自然句內的技術名稱／單一檔名提及不再直接當路徑；獨立檔名、實際絕對／相對路徑、code／fence、URL、JSON、table、trace／log 保留拒絕。沒有刪字拼接，也沒有全域移除 technical check。
- 同 owner 的 options：保留日文名詞選項的共用肯定尾句，接受有限的普通形 potential 與 `チェック`；漏選項、只說畫面、否定／反轉仍拒絕。`_option_parts` 的既有切分與 anchor／coverage、數值／失敗檢查未取消。
- parser 留下去識別 `diagnostics`：收到／通過驗證的 anchor、segment 數分開，附 stage、index、rule_id；拒絕時不輸出被拒原文。queue 將未知的已驗證 count 記為 null，而非誤導的 0，並將診斷傳入既有 speech_timing／speech-status。
- 整合測試發現：拒絕語音時沒有 TTS task，silent Display 可能還在 sender queue，completion 即清除 sender。既有 `queue_generated_speech` 的拒絕分支等待同一 queue 排空，再發 unavailable／完成，不新增 queue／manager。
- v2 prompt 已明確要求同輪自然摘要、不複製 raw code／URL／path／JSON。本輪已有 validator 誤判證據，沒有正式原始 speech 可證明需改 prompt，因此 **prompt 不改**。

## G4：驗證進度

第一次修復後 semantic suite **35/35 PASS**。新增正式 conversation → parser → queue → TTSTaskManager → 真實 central adapter → 真實 WAV serializer → mock WS 測試後，38 tests 中 5 個 blocked subcases 因 Display 未送出的 queue 時序問題失敗；修正拒絕分支 queue drain 後 **38/38 PASS**。收尾審查另補 `調べられません／調べられない／できるのではありません` 負例，避免新增肯定詞形放過反轉；最終四個 suites 皆通過。

`CentralPathRegressionTests` 沒有替換正式 parser、queue、TTSTaskManager、central TTSEngine 或 `prepare_audio_payload`。僅 mock 主 LLM、HTTP transport、History／Memory storage 與 WS，並封鎖未預期的實際 HTTP。正常技術與雙選項各驗：一輪主 LLM、Bridge requests=0、中央 POST 內容／voice／language、`tts_request → tts_complete → websocket_audio_sent`、可解碼的 1600-frame synthetic WAV／volumes、清空的音訊字幕、Display／History／Memory 完整、cache 清理、完成 ack。raw URL、漏選項、可執行性反轉、失敗／未驗證反轉均沒有中央 GET／POST 或音訊。**這些是隔離證據，不能視為 Electron playing。**

最終 log／JSON：`.tmp/kuro-speech-v2-silent-regression-20261031/Final-Validation.json` 與 `Final-*.log`。使用既有 Python 環境，沒有安裝／更新套件。精確命令（repo root）：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = 'C:\project\desktop-agent-runtime\tests;C:\project\desktop-agent-runtime\Open-LLM-VTuber\src;C:\project\desktop-agent-runtime\Open-LLM-VTuber;C:\project\desktop-agent-runtime'
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_speech_semantic_alignment.py -v
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_multilingual_speech.py -v
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s tests -p test_first_speech_latency.py -v
& '.\envs\kuro-llm310\python.exe' -B -m unittest discover -s Open-LLM-VTuber/tests -p test_tts_pronunciation_pipeline.py -v
```

| 驗證 | 最終實際結果 |
| --- | --- |
| `test_speech_semantic_alignment.py` | **38/38 PASS**，1.643s；原 30 項＋本輪 8 項（另含多個 subcases）。 |
| `test_multilingual_speech.py` | **30/30 PASS**，1.450s。 |
| `test_first_speech_latency.py` | **10/10 PASS**，0.319s；preload hooks 是 mock，未啟動服務。 |
| `test_tts_pronunciation_pipeline.py` | **47/47 PASS**，0.045s。 |
| 三份修改的 Python 檔案 `compile()` | **PASS**；以 `-B` 執行，不寫 pyc。 |
| source／test／Progress UTF-8 嚴格讀回 | **PASS**。 |
| scoped `git diff --check` | **PASS**，exit 0；既有 mixed LF／CRLF 警告不等於 whitespace failure。 |
| 本輪新增行尾空白 | **0**；包括原先 untracked 測試與新增 Progress。 |
| `git apply --check --reverse <TaskDiff.patch>` | **PASS**，exit 0；只有檢查，沒有實際反向套用。 |

驗證 runner 與 final check 的精確命令：

```powershell
& '.\envs\kuro-llm310\python.exe' -B .tmp/kuro-speech-v2-silent-regression-20261031/verify.py Final
& '.\envs\kuro-llm310\python.exe' -B .tmp/kuro-speech-v2-silent-regression-20261031/final_checks.py
git diff --check -- Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py tests/test_speech_semantic_alignment.py
git apply --check --reverse .tmp/kuro-speech-v2-silent-regression-20261031/TaskDiff.patch
```

原有與新增測試也涵蓋：malformed／duplicate keys／invalid anchors、required coverage、未知 ID、漏選項、錯誤及部分缺失、價格／停損／正負／百分比／error code、v1 compatibility、工具 continuation 與 tool args、取消、音訊序列／最多三段、fail-stop 與完成 ack。沒有把 fixture 通過寫成正式工具、金融資料或 native acceptance。

## 實際 Diff 與 WIP 保護

本輪獨立 patch：`.tmp/kuro-speech-v2-silent-regression-20261031/TaskDiff.patch`。它相對 **G0 保存的 dirty preimage** 產生，只包含下列三份既有檔案差異與本新增 Progress；不是整份 HEAD dirty diff。`FinalChecks.json` 記錄 before／after SHA、行數、protected bytes、syntax、diff／reverse check 與其他 WIP 漂移。

| 變更檔案 | 本輪 scoped diff | 最終 source SHA-256 |
| --- | --- | --- |
| `Open-LLM-VTuber/src/open_llm_vtuber/conversations/speech_presentation.py` | +42 / -13 | `c4700057e1a1a094aeed2487eddd798c20ebaaf7441264e9892ca3f763b32e21` |
| `Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py` | +10 / -3；僅 queue_generated_speech | `ea0de3431ff22ee50b49a52fdc0fcccd2fe047c32806590a85fc6c97c98d3e6b` |
| `tests/test_speech_semantic_alignment.py` | +159 / -1 | `edf71fa7006c2b9ce50caebaf8228edda2517a2652d13012af24c757a73272c8` |
| 本 `Progress.md` | 新增交付紀錄 | 最終 hash 見 `FinalChecks.json`，避免文件自我 hash 循環。 |

- HEAD、branch、index 與唯一新 Plan 原 bytes 均不變。原 v2 Plan／Progress、v2 prompt、Agent、single_conversation、TTSTaskManager 均與 G0 snapshot bytes 一致；沒有改中央 adapter／模型／preload、Qt、Memory／工具 owner 或 `mcpp/*`。
- `conversation_utils.py` 原本混合換行；CRLF 2584 → 2591，僅符合本輪新增 7 行，未全檔正規化。其他兩份修改 Python 原為 LF，仍為 LF。
- 偵測到 **`Open-LLM-VTuber/tool_catalog.json` 非本輪 WIP 漂移**。本輪未寫入／回退它，未放進 TaskDiff，也不對該並行變動作驗收結論。
- 工具錯誤如實保留：早期讀取命令使用了 PowerShell 不支援的 brace 路徑展開而 ParserError，已改成明確路徑；diff inspection 曾 cp950 `UnicodeEncodeError`，改成 UTF-8 後成功。這兩次失敗未被算成 PASS，沒有換模型或另建任務。

## 剩餘限制與未驗證項目

- 正式兩輪被拒原文缺失，無法回溯證明當時是非法模型 speech 或哪個 regex 誤判；本輪修正的是實際 source 上可重現的相同拒絕類型，後續需以新去識別診斷核對。
- deterministic 詞法檢查不是跨語語意 judge。只涵蓋有限選項動詞、肯定／否定尾句、source coverage 和數值形式；未知翻譯仍 `option_unverified`。可重現例：`折紙を折る → We can fold paper.` 仍無法驗證。複雜反諷、主詞、因果、否定範圍及同句行動歸屬不保證等價。
- 技術邊界仍是有限規則，沒有新增完整語法分析器：獨立檔名與 raw 標點／code keywords 仍保守拒絕。已實測的剩餘 blind spot：自然句 `const は定数を宣言します。` 因 leading keyword 仍為 `technical_payload`。這不應被隱藏成「所有合法技術日文都已放行」；可改用自然說法「定数の宣言について説明します。」供正式人工驗收。單一檔名／技術名稱在自然句內可提及，真正含分隔符的相對／絕對路徑仍拒絕。
- 日文／中文口語數字、單位換算、未識別數值角色可能被拒絕；數值／失敗／未驗證檢查沿用原 owner，沒有為避免靜音放寬。
- 沒有真實主 LLM 輸出分布、正式 source adoption、中央 GPU 推論、Electron 播放／嘴型、首聲延遲、音色與真人聽感證據。先前中央 HTTP 200／loaded=kuro／舊 PID 不證明本 patch 已採用；本輪也沒有重查正式 health 來冒充驗收。

## G5：待正式套版／驗收交接

本輪於 Source＋targeted verification 與文件核對完成後停止。獨立 Reviewer 與正式換版尚待後續授權，由原 lifecycle owner 執行，不自行重啟 Kuro／中央服務、不重建無關 Qt bundle。

1. Reviewer 先以 `before/`、`TaskDiff.patch`、`FinalChecks.json` 審查本輪 hunk，和並行 MCP／catalog WIP 分開；對照上列 Source SHA。
2. 正式套版需留下 installed release 身分、conversation PID／開始時間、實際載入 source hash。`Source Ready`／`Targeted PASS` 不等於 `Installed Release`／`Runtime`／`Desktop E2E`。
3. 同一主 LLM 雙 lane 各做：短問候、Node.js／API／JSON 自然技術說明（Display 保留 code／URL／path／trace）、自然日文雙方案、工具失敗＋未驗證、重要價格／停損。確認 Bridge requests=0，必要選項與語意限制沒漏。
4. 以新診斷追 `contract=v2, state=ready → tts_request → tts_complete → websocket_audio_sent → Electron playing`，最後由使用者確認真實有聲與日文自然度；保留取消、fail-stop、完成 ack 的驗收。
5. 如需退回本輪，先重新核對當時檔案 hash 與後續 WIP，僅逐 hunk 逆轉本輪 TaskDiff。不得以整檔 baseline／HEAD 覆蓋並行工作；不得默默啟用第二個模型或 Bridge。現有 v1 parser／設定退路仍在，本輪未執行切換。
