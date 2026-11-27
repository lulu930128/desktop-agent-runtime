# Phase 1 — Reviewer 獨立 Source 驗收（2026-11-03）

## Gate 判斷

**Reviewer Source/Diff：PASS（保留已知限制）；正式 Runtime／中央音訊／Electron playing／真人聽感：UNVERIFIED。整體產品暫不封版。**

此處的 PASS 僅代表原始「有日文 Speech 卻被 unknown option 誤靜音」的 Source 修復，其效果經 mock replay、既有測試收據與 Reviewer 獨立 Source/Diff 核對支持；不代表所有 TTS 靜音狀況已解，也不代表正式程式已載入。

## 獨立查核動作與證據

1. 透過 Project Workspace 唯讀閱讀 `speech_presentation.py` 的 `SpeechLaneParser.result`、`_option_supported`、`validate_semantic_lane`，以及 `conversation_utils.py` 的 `queue_generated_speech`。確認：
   - 可播狀態新增 `semantic_unverified`，Parser 保存合法 speech text，queue 送往既有 `TTSTaskManager`。
   - option helper 改為 `True/False/None`；未知跨語詞義只留下 soft failure，不早退；仍執行 required anchor、數值/狀態/否定、Display 與文字/locale guard；已識別的選項不一致仍拒播。
   - pronunciation 再驗後不將 unverified 洗成 ready；新增 `speech-status: degraded` 僅回傳 metadata，不把私有語音稿送回 Chat。
2. 唯讀檢查 Codex Bridge `6a814809-42ff-4a0d-a7f0-9332e10f1e81` 的本輪 Diff Artifact，相較 pre-existing WIP 僅涉及兩份 production source、兩份測試、階段文件及 repo-local 測試收據；未見中央 service／Pet／Qt／Tool/MCP／DB 路徑變更。
3. 唯讀讀取 `tests/test_tts_reliability_phase1.py`、`test_speech_semantic_alignment.py`，確認涵蓋 synthetic 日常聊天 3 組、錯價／狀態衝突、已知選項缺漏、schema/locale/technical payload、正式 conversation/mock TTS 順序、cancel/fail-stop/ack 及資料隔離。
4. 透過 Project Workspace 對四份修改 source/test 做 raw bytes SHA-256 獨立讀取，與 `Phase1Report.md` 精確一致：
   - `speech_presentation.py`：`f0d4e5376d018b4b820e33e15e81d253b83b06c7e8a7ead31c4a226c42807bb0`
   - `conversation_utils.py`：`ad746955b097fdefaf5f6b345fa19497d8e2b707e2f05776b5afbf57a179c55d`
   - `test_speech_semantic_alignment.py`：`aa4ca0a5400e255cf8712446dcbdae1bd2da8927eb903ce5f8dc9e7549a718eb`
   - `test_tts_reliability_phase1.py`：`eb89723bbf471132170666a11feffb9f9bdca4610d491a53f46df10900f4166a`
5. Codex 執行的修前 red fixture：2 tests、6 個 subtest failure；修前各 0 次 TTS mock，修後各 1 次且保留相同日文稿。最終 Suite 收據：12 + 38 + 30 + 10 = **90/90 PASS**；syntax／UTF-8／scoped diff check PASS；Codex 收據顯示 HEAD/index/Plan 不變，147 份非本輪既有 WIP bytes 不變。**Reviewer 未獨立再執行這 90 項測試**，因此測試執行證據仍標示 Codex runner，非第二次獨立 execution。

## 已知限制與下階段

- 真正 `missing` 的日文稿依舊不會憑空出現；不自動加第二輪 LLM／Bridge，也不假裝原始 01:25 case 已解決。
- 有限詞彙的 option helper 仍可能誤擋「已知主題但使用不同自然日文動詞」；未知選項 soft accept 也可能包含真正漏譯，必須保留 `semantic_unverified`，不能說通過了跨語意的完整等價檢驗。
- `speech-status: degraded` 已從後端發送，但未變更／驗證 Electron 顯示；不保證 UI 呈現新的狀態。
- 本次沒有以真實主 LLM + 中央 GPT-SoVITS + Electron 的 Production Path 做 E2E，也沒有重新啟動／部署、量測 TTFA 或確認實際音質。
- **下一步只需正式 Runtime 採用與定點實測**（需要使用者明確另行授權）：確認 Process 載入新版 → 日常對話與一個工具失敗案例 → TTS response → WS audio → Electron playing／人耳品質。Phase 2/3 繼續維持 Plan-only。
- 回滾：只在核對當前 preimage/final hash 後精準逆轉本輪 patch；不可整檔 reset／checkout 破壞原先 WIP。

## Reviewer 結論

- **Source Gate：可以繼續開發；不需要為這項缺陷再次擴大 Source 重構。**
- **Runtime Gate：Unverified，不可宣稱正式桌寵已修好。**
- **產品封版：證據不足，無法判定；等正式 Runtime E2E 與真人口播品質收據。**
