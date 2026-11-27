# Kuro 工具分析與簡短口播進度

更新日期：2026-11-05（Asia/Taipei）。

## 目前狀態

- M1～M4 實作與相關回歸完成。
- 六類場景各兩輪的真實後端測試完成：12/12 產生實質語音，11/12 在 25 秒內；中位數 17.73 秒，最長 26.04 秒。
- OMI 候選修正後另驗一次：能力狀態與新鮮度兩個工具均實際執行，語音 18.90 秒。
- 新 Pet renderer 已建置、透過既有 reload 指令載入；一次真實 WAV 播放回報 completed，21.42 秒音檔於 21.656 秒完成，已恢復原 LLM 連線。
- 正式 Qt／LLM 程序仍為先前程序；新 Python 與 Qt signed pin 要由既有「重新啟動 Kuro」流程載入。未宣稱正式 Qt 的 12 回合播放或使用者聽感已驗收。
- 使用者接受純後端測試。累計 148 次受控請求（其中 LLM 54 次），未超過 150；不再追加真實測試。
- 沒有 commit／push、寫入長期記憶、刷新 OMI provider、生成持久化報告或停止共享中央語音服務。

## 找到並修正的問題

1. 原始 OMI 回合在語音驗證層拒播：2026-11-05 19:59:03 的日誌為 `anchor_status_mismatch`，8 anchors、3 segments、anchor index 4，沒有 TTS request。未保存原始 private speech，不能聲稱已證明那句翻譯正確。
2. 可重現的錯誤拒播：自然日文同義改述、否定句、完整 Display 的次要限制／選項，被有限詞彙檢查當成硬衝突。現在未知改述為 `semantic_unverified` 並發聲；確定的狀態反轉、錯價／正負號、無來源數字、非法引用、URL／路徑／code 仍拒絕或單次修復。
3. 長稿由 required anchors 過多與逐條列舉限制造成。主回應現在先選短結論，再保留對結論必要的限制；詳細證據不從 Display 刪除。
4. 缺稿／壞稿／過長短摘要允許一次 tool-free repair，20 秒 deadline，工具不重跑、不改 Display、不寫入記憶。修復失敗不把非法稿改成 ready；只有原本合法但冗長的稿可以保留。
5. 明確 busy／429 原本直接棄掉整組。現在至多兩次各 2 秒的等待，維持取消與 orphan WAV 清理；受理結果不明的 POST timeout 不重送。同步 public API 仍相容地回傳 None。
6. 嘴型分析失敗原本可讓有效音訊無法播放。現在音訊與包絡容錯分開；空音檔、全零及無法解碼仍回報錯誤。
7. Pet 播放 error／play rejection／無進度不再假報成功。首段已有 request identity；舊 callback 不干擾新回合。後端也拒絕未收齊音訊的晚加入 Pet 代替真正播放端回報 completed。
8. synth-complete 改由 finalizer 在 queue drain 後發出一次。Qt 與 Pet 消費 speech-status，Qt 文字不因空 audio payload 消失；失敗原因有明確狀態。
9. OMI 同時查能力與新鮮度時，能力工具被跨類候選排名擠掉，模型改用 freshness 工具詢問能力。新增明確意圖詞，保留已發現的直接命中工具；候選上限與原 tool policy 不變。

## 真實後端驗證

使用現有 `gpt-6-astra`、Kuro 角色、真實 read-only OMI／project-workspace、中央 voice `kuro`。測試經實際 conversation、speech parser／repair、TTS manager 與 WAV payload 路徑，略過正式 history 寫入。後端 harness 明確回傳 `not_played_probe`，不偽造播放器 ack。

| 場景 | 第一輪秒數 | 第二輪秒數 |
| --- | ---: | ---: |
| OMI 能力／新鮮度 | 14.22 | 17.70 |
| OMI 單一標的快取研究 | 16.94 | 24.70 |
| 不重查工具、簡短追問 | 26.04 | 22.62 |
| 唯讀啟動／語音服務程式 | 22.04 | 16.58 |
| 唯讀音訊處理程式分析 | 21.82 | 16.26 |
| 路徑／參考來源追問 | 17.76 | 15.56 |

- 11 次直接有可用短稿，1 次經單次修復成功；沒有把固定「請看畫面」或失敗提示算成內容成功。
- 12 份口播人工對照及技術內容過濾：未見路徑／URL／原始 code 朗讀，未見關鍵狀態反轉；保留資料不足、過期與尚未驗證的限制。這是小樣本，不是長期可靠率或跨語等價證明。
- 26.04 秒那次保留資料時效、缺漏與不能據此判定買點的限制，仍低於 35 秒上限。
- 表中兩次能力場景只取得 freshness，口播如實說能力清單未取得。它們只算語音管線成功，不能算雙工具目標成功。發現選工具缺口後修正，補驗的第 13 次確實完成 capability status + data freshness，產生 18.90 秒有內容回答。
- 校準階段曾出現整段拒播及 40.64 秒冗長稿；均保留本機證據，未併入最終 12 次假裝原本就通過。修正後以整批六場景兩輪重測。
- 額外播放器測試是把已合成 WAV 送到真 Pet；並非整個正式 Qt／LLM 對話。完成後已恢復原 backend，Pet 為 idle。

## 回歸與建置

- Python：216 項相關測試通過，涵蓋簡短口播、semantic、Phase1、multilingual、首聲時序、中央 client、G3 WS／Qt、history parity、Qt display、長清單、OMI routing／arguments／preflight／policy、workspace routing、PAOS routing。
- 擴大檢查共 218 項時，另兩項既有 workspace configuration assertion 失敗：角色 enabled servers 包含 Memory Core，registry 清單沒有；本次未改這兩份本機設定，檔案時間均早於任務 preimage。這兩項獨立列為未通過，不修改無關設定來讓測試綠燈。
- Node：`node --test tests/g3_presentation.test.cjs tests/multilingual_speech_frontend.test.cjs`，14 項通過；Qt／G2 frontend 27 項通過，共 41。
- `npm --prefix pet-electron run check:renderer` 與 `build:renderer` 通過；Python 20 個 touched source/test AST syntax checks 通過。
- Qt owner bundle 簽章、manifest、lineage、五個資產均驗證通過。新 fingerprint：`2813daee6633259de26c0fb6fdcc22322815dc4e15f801d50425c2fd12b398ab`。
- Scoped `git diff --check` 通過。原本的 history UI WIP 保留；Qt bundle 在 pinned base 的隔離 worktree 建立，沒有把原本未採用的 main.ts 修改混進這次資產。
- 回歸明細在本機 `regression-accepted.log`；兩項既有失敗保留在 `regression-complete.log`。最初誤列一個不存在的 test module 的命令不計通過，後續以實際測試清單重跑。

可從 repo root 重跑最接近的新增案例：

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_concise_tool_speech.py
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_g3_conversation.py
.\envs\kuro-llm310\python.exe -B -c "import sys,unittest; sys.path[:0]=['Open-LLM-VTuber/src','Open-LLM-VTuber/tests']; unittest.main(module='test_tool_catalog_market_routing')"
node --test tests/g3_presentation.test.cjs tests/multilingual_speech_frontend.test.cjs
npm --prefix pet-electron run check:renderer
```

OMI catalog 指令明確加入 runtime src／tests；本輪完整 unittest suite runner 亦加入 root tests 與 runtime root。一般回歸不呼叫外部 API。

## 正式採用與回退

- Task preimage、雜湊、task-only file list、renderer-dist 備份、API ledger、原始測試資料留在 ignored `.tmp/kuro-concise-tool-speech-20261105/`。原始語音、工具輸出及私人 log 不加入 Git。
- 已採用：Pet renderer build，透過既有 `/command` 的 reload-frontend；實際播放與恢復 backend 已確認。
- 待採用：Qt 與 LLM 的 Python 修改及新的 Qt bundle source pin。透過既有 tray「重新啟動 Kuro」流程完成，不 kill 全域 Python、不停止共享 TTS、不新建管理 listener。
- 若需回退，只逆轉本任務 preimage／diff，還原先前 Qt pin 與已保留 bundle；Pet 以 renderer-dist 備份恢復後 reload。不可以 git reset／checkout 清掉其他 WIP。
- 隔離 bundle worktree 的 dependency junction 已安全移除，原 repo node_modules 保留。App archive 工具以「primary checkout cannot be removed」拒絕封存，故保留該 managed worktree，不手動刪除 checkout。

## 限制與後續

- 正式 Qt 的新狀態提示有合約／前端測試與 signed build，尚無新程序的畫面驗收。使用者接受後端測試不等於正式採用已完成。
- 自然語意仍不能靠詞典完全證明；`semantic_unverified` 是不確定標記，不代表等價認證。明確反轉仍擋下，無法確認的自然改述不再直接整段消音。
- 短口播改善的是發聲內容與穩定性，沒有消除工具／主 LLM 取證延遲。本輪部分研究取證仍接近百秒。
- 90 秒播放完成等待尚未依長篇 detailed 音長動態擴張；本輪最長 26.04 秒摘要已涵蓋，長篇模式不能藉此宣稱驗收。
- 本輪沒有 subagents，也沒有改中央模型、音色或依賴版本。

## 參考實作

沿用審查時查閱的官方來源：[Pipecat TTS service](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/services/tts_service.py) 的每段音訊／失敗追蹤、[LiveKit fallback](https://docs.livekit.io/agents/logic/fallback-strategies/) 的有限恢復與已產生音訊後保護，以及 [GPT-SoVITS pipeline](https://github.com/RVC-Boss/GPT-SoVITS/blob/main/GPT_SoVITS/TTS_infer_pack/TTS.py) 的音訊邊界處理。這次採用設計原則，沒有複製上游程式或更新 dependency；未把 upstream main 當作固定 release 證據。
