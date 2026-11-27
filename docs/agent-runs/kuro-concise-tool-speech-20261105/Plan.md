# Kuro 工具分析與簡短口播實作計畫

日期：2026-11-05（Asia/Taipei）。狀態：M1～M4 已實作；M5 後端與單次桌寵播放已驗證，正式 Qt／LLM 採用待重啟。
需求與完成定義以 [Prompt.md](Prompt.md) 為準。各階段依序完成；產品終點是 M5 的正式桌面驗收。

## 執行校準（2026-11-05）

- 使用者允許純後端測試；實際執行六類場景各兩輪，保留 12 次真實模型／工具／中央 TTS 證據，再補一次 OMI 雙工具驗證。此證據不宣稱是正式 Qt 的 12 次播放。
- 摘要生成目標校準為日文 55～85 字、通常不超過 110 字；不剪音訊或硬截句子。過長摘要也可用一次 tool-free 修復；失敗保留原本合法稿，不為縮短而消音。`detailed` 不套用短摘要上限。
- 單次語音稿修復 deadline 為 20 秒；正常合法短稿不追加呼叫。忙碌至多三次嘗試、兩次各等 2 秒；網路逾時不盲目重送。
- Pet 播放使用 media clock 與既有 WAV 包絡做嘴型，不經嘴型 AudioContext 改接音訊；15 秒無進度視為播放失敗。後端完成等待目前為 90 秒，足以覆蓋本輪短摘要；長篇 `detailed` 的動態時間預算仍是後續限制。
- OMI 實測發現明確能力查詢被候選排名擠掉，因此額外保留匹配 intent 的已發現工具；既有候選上限及執行 policy 不變。
- 詳細結果、已知失敗隔離、正式採用範圍與回退位置見 [Progress.md](Progress.md)。

## 已確認的問題與證據限制

- 11 月 5 日 19:57:53～19:59:03 的 OMI 回合確實執行兩次工具呼叫；最終收到了 8 個 anchors、3 個 speech segments，在 `required_anchor` 的 `anchor_index=4` 命中 `anchor_status_mismatch`，沒有進入 TTS。
- 原始 speech／anchor 沒有保存在該回合日誌，不能還原第 5 個錨點的確切語意；已確認拒播階段，但不能聲稱已證明該回合的翻譯正確。
- 目前 source 可重現：同義日文被拒播、否定句被錯分狀態、`speech-status` 沒有 consumer、busy 導致整組跳過、播放 error 仍送 completion。
- 上一輪審查的 104 項既有測試全過，仍能重現上述漏洞。不能把測試原本的保守預期直接當成產品要求。
- 11 月 5 日診斷時中央服務仍為 10 月 28 日啟動的程序，health 不含新版預載 capability。這是當時的採用落差，不是本次合成前拒播的原因；M5 必須重新查核。
- 日誌檔名與檔案列表時間可能停在程序啟動日。找回合時要查內容時間與程序持有的檔案，不只看檔名／LastWriteTime。

## 設計決策

### 文字與語音分工

Display 保留完整證據與技術細節；Speech 產生能獨立理解的短回答。長分析不需要逐項朗讀所有數字、選項或整份能力清單。只要不造成誤導，次要細節留在畫面；直接影響口播結論的限制與數值必須保留。

預設 2～3 句，目標 10～25 秒；句數與時長是軟預算。應在生成時簡化表達，不在輸出後硬截字、刪否定句或剪掉音訊尾端。比較題若省略另一個選項會改變答案，需完整保留比較。

技術內容應整句改述，例如「設定檔缺少必要欄位」；不能把含路徑的條件句只刪掉路徑後直接朗讀。既有 `brief`／`summary`／`detailed` 保留相容性，`summary` 對齊短結論；使用者要求詳細時才增加內容。

### 驗證分為三種結果

| 結果 | 可採信依據 | 行為 |
| --- | --- | --- |
| 可用 | 結構、引用、語言、技術內容隔離與可檢查事實通過 | 送既有 TTS 路徑；不宣稱已證明完整跨語等價 |
| 語意未確認 | 同義詞／句型不在有限辨識能力內，沒有確定衝突 | 保留合法語音，標 `semantic_unverified` 並播放；不得再用同一字詞缺失規則改回拒播 |
| 明確不可用 | 缺少必要 segment／引用、malformed、路徑或 URL payload、可靠證據支持的錯價／正負號／狀態反轉等 | 一次有界修復；仍失敗則清楚降級並結束，不當成實質口播成功 |

工具成功／失敗與 freshness 的來源，以原工具結果及既有 adapter contract 為準。不能從整段 Display 出現「拒絕」「失敗」就推定該事件發生；假設句、引述、歷史敘述與否定句要分開。無足夠證據時是 unknown，而不是 hard conflict。若既有 v2 無法表達必要資訊，先列出具體 contract 缺口與相容方案，再決定最小擴充；不預設重寫協定。

這個取捨承認自然語言驗證有限；品質以重要事實對照、反例回歸和真實聽感建立，不能靠增加詞典來宣稱語意安全。

### 恢復與播放結果

- 正常回合不增加模型呼叫。只有 missing、malformed、技術內容或明確衝突時，允許至多一次純語音稿修復：沿用目前模型／配置，提供已完成 Display、必要工具限制與具體失敗類型；停用工具，不重跑 OMI／本機查詢，不改寫 Display／History。
- 修復使用可取消的單次 deadline，候選值 10 秒；M1／M3 以模型實測校準並記錄最終設定。超時不背景無限續跑、不迴圈重試、不新增常駐服務。
- 修復仍不可用時，呈現可理解原因與重試入口。中央 TTS 可用時可播一句誠實的降級通知，但標為 degraded，不能計入內容成功率。
- busy／429 若 owner 明確尚未受理，保留原組與順序，短暫有界等待；建議 admission 總預算 5 秒、最多兩次重查，測試確認後固定。被取消或超時即丟棄。
- POST read timeout 的受理結果不明，不盲目重送。未具 request identity／查詢 receipt 時，維持 unknown outcome；恢復必須由 owner 支持，不以 consumer 猜測。
- 播放結果區分 completed、failed、interrupted；從排入第一段前建立 turn／utterance／sequence 關聯。舊協定相容性需查核，禁止把 error 封裝成成功 ack。
- 嘴型分析失敗不得阻止可播放音訊；AudioContext、decode／play failure 與 stalled 要有有界處理。允許正常句間靜音，不加入過度積極的 noise gate。

## M1：建立反例基線、狀態與驗收資料

**範圍**：相關 source、測試、runtime 診斷與最小狀態接線。

- 先保存本輪實作前 branch／HEAD／status、task-owned preimage，保護既有 WIP。
- 建立匿名語料：OMI capability／freshness／個股證據、本機狀態、程式分析；每個案例有預期結論、必要限制、禁止口播內容。
- 補修前可失敗的測試：自然改述、否定與假設、格式差異、缺 footer、混入 URL／路徑、已知錯價／反轉、busy、播放 error 與取消。
- 串接現有 `speech-status` 到 Qt；區分取得證據、語音準備、等待服務、播放、降級與失敗。Pet 只回報 presentation 結果，不接管分析。
- 記錄 turn／sequence、stage、reason、缺失 flag 類型、counts、修復次數與耗時；不寫入 raw prompt、語音稿、工具 payload 或私人路徑。

**驗收**：可從 UI 與非敏感診斷區分「工具失敗」「語音稿拒播」「合成失敗」「播放失敗」。相同 source 的 synthetic fixture 可穩定重現問題。

**驗證**：既有 semantic／multilingual／Qt transport／Pet adapter 測試加定點反例。若反例不能重現，先查 baseline，不直接改預期。

## M2：產生簡短、可獨立理解的語音稿

**範圍**：`speech_lanes_prompt.txt`、`speech_presentation.py`、`conversation_utils.py` 與相關 fixture；只有證據需要時才動 agent output 接線。

- 將通用呈現規則放在 speech contract／policy；角色 prompt 只保留語氣與人格，OMI 分析仍由 domain owner 提供。
- 同一主回應生成完整 Display 與 2～3 句摘要。減少「所有資訊皆 required」帶來的長口播，required 保留對所說結論必要的事實／限制；詳細數表與技術 payload 留在 Display。
- 修正 known-topic／同義動詞與狀態比對，實作上述三態。明確覆蓋「尚未驗證／まだ検証していません」「資料不完整／データはまだ揃っていません」「不是權限拒絕」等反例。
- 路徑、URL 與 code 不送 TTS；自然技術名稱可保留。不能把所有技術分析一律改成固定「請看畫面」。
- 重要否定與前提和其結論作同一語意單位；不只留下聽起來像成功的部分。

**驗收**：短稿有實質結論；關鍵限制與證據一致；完整 Display 不變；同義改述不誤擋；已知關鍵矛盾仍有可追溯拒絕依據；正常路徑額外模型／Bridge 呼叫數為零。

**驗證**：semantic、Phase1、multilingual 與長清單 fixture。若縮短使失敗變成功、刪掉重要限制或數值角色錯置，先修正再進下一階段。

## M3：修復無稿／壞稿與暫時性失敗

**範圍**：既有 conversation lifecycle、TTS manager、中央 client，必要的單次模型呼叫接線。

- missing、malformed、技術 payload 與明確衝突走同一有界恢復入口；先檢查可復用的現有模型介面，不另建 translation service 或平行 queue。
- 修復只讀已完成證據，使用同一語音驗證政策；保留原始 failure reason 與最終 outcome。
- 將中央 client 的 `None` 型失敗收斂成可區別的內部結果，保留既有外部相容性。busy、離線、無效音訊與 unknown timeout 不混為同一件事。
- 首段暫時 busy 不立即讓整組永久失敗；先進行有界 admission 等待。真正失敗時維持語意完整性，不跳過必要前提後繼續播結論。
- 任一取消／新回合都能終止等待與修復；同步 GPU 請求若已開始，晚到結果只能清理，不能播到下一輪。

**驗收**：單回合最多一次語音稿修復、工具呼叫不重跑；busy→available 可恢復；永久故障能準時降級；取消無舊音訊洩漏；文字完成不被無限等待拖住。

**驗證**：mock 網路／模型／時間的故障矩陣與最接近的 client／queue 測試。故障注入在 fixture 中進行，不停止正式 OMI 或中央服務製造故障。

## M4：完成音訊與播放器的結果回報

**範圍**：`tts_manager.py`、`utils/stream_audio.py`（僅必要時）、Pet backend client／adapter／events、Qt owner 狀態 consumer。

- 保留完整 WAV 路徑，驗證 frame 完整性、sample format／rate、空音訊與不可解碼資料；不靠調大音量掩蓋無內容。
- 將嘴型包絡計算與發聲容錯分開；正常音訊不因嘴型處理例外整段消失。
- `playing`、`ended`、decode／play error、AudioContext 恢復失敗、stalled、interrupt 各有對應 outcome。等待時限依音訊長度加餘裕設計，不能用固定短 timeout 切掉合法長語音。
- completion 表示成功播放到尾端；失敗、取消有獨立結果。晚到 callback 不得清掉新回合音訊或 ack 新回合。
- 結構化序列化播放診斷，避免目前 `[object Object]` 無法追查；關聯 id 在首聲開始前即存在。

**驗收**：模擬 error 不再發成功完成；無音訊與中斷不計成功；取消後下輪可正常播放；Qt 顯示與真實結果一致。

**驗證**：Node VM 模擬 Audio／AudioContext、真 WAV fixture、Qt signal／adapter 回歸；有 UI 變更時驗正式介面。只有中央 owner 確有缺陷才進一步修改其 repo，不順手升級模型。

## M5：正式 runtime 採用與使用者驗收

**範圍**：可回退的 release／程序採用、真工具與中央語音、Qt／Pet 實際體驗。

- 先完成 source／targeted tests，再依現有 Launcher／release 流程建立並核對 candidate。Qt signed owner bundle 必須核對實際 pin、fingerprint 與載入資產；devtools preview 通過不能代表正式 UI 已採用。
- 採用前核對 session 中已有授權；需要正式啟停／換版時，提出具體 candidate、受影響服務、驗證與回退方式。Consumer 不自行停止共用 Voice Runtime。
- 記錄正式 process／port／source 或 release identity、有效 speech 設定、voice 與 health capability；先前程序時間與舊證據只作線索。
- 下列六類場景各執行兩輪，共 12 回合；OMI 只讀既有資料，不觸發 provider refresh／持久化報告。電腦／程式驗收使用授權且不含 secrets 的範例來源。

| 場景 | 必須成立的結果 |
| --- | --- |
| OMI 能力與 freshness | 實際工具呼叫；短述能力與限制，不念完整清單 |
| OMI 單一標的研究 | 引用當次 OMI 證據；保留關鍵數值／缺漏，不自行補市場結論 |
| OMI 回答後要求「簡短說重點」 | 使用正確既有證據，避免無必要的重查與變造；口播明顯精簡 |
| 本機程式／服務狀態 | 有授權讀取證據，清楚區分觀察與推測；不念機器路徑 |
| 程式錯誤分析 | 說出問題與影響，畫面提供檔案／行號／程式碼；口播不念 raw code |
| 帶文件 URL／路徑的技術追問 | 回答實質意義，完整連結與位置留在畫面 |

**強制驗收**：服務正常且應發聲的 12 回合，12/12 實際播出有內容的回答；路徑／URL／code 洩漏為零；已發現關鍵事實反轉為零；至少 10/12 在 25 秒內，超過者需確認是必要資訊，普通摘要不得超過 35 秒。若門檻與必要限制衝突，先改寫再測，不能刪警告或默默放寬門檻。

**故障驗收**：獨立 synthetic 場景涵蓋 OMI 不可用／partial／stale、missing footer、合成 busy／timeout、播放 error／stalled、使用者中斷。真實 unavailable 不標成功；若 live 工具拿不到證據，記外部限制並保留該場景未驗收，不能用假資料替代。

**量測**：分開報告首次內容成功、一次修復後成功、固定降級、failed、interrupted；工具耗時、主 LLM 耗時、speech ready→playing、總首聲時間、實際口播秒數、repair 次數。使用共同 id 關聯；不同 process 的 monotonic clock 不直接相減。小樣本列原始數值與中位數，不假稱長期成功率／可靠 P95。

**完成**：12 回合證據、故障矩陣、正式 UI 狀態與使用者聽感確認全部成立。Source PASS 或偶爾說出一句話不能封版。

## 驗證入口與預算

文件階段已完成；實作階段依下列入口及 Progress 的實際測試清單驗證。

實作時從 repo root 按變更挑選，先執行最近的 tests，通過後不無故重複全套：

```powershell
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_speech_semantic_alignment.py
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_tts_reliability_phase1.py
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_multilingual_speech.py
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_first_speech_latency.py
.\envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p test_central_voice_client.py
node --test tests/g3_presentation.test.cjs
node --test tests/multilingual_speech_frontend.test.cjs
npm --prefix pet-electron run check:renderer
```

依 M1～M4 的實際 touched files 補 Python syntax、Qt transport／state 與新增反例。若改動 OMI routing／tool evidence contract，才加入 `Open-LLM-VTuber/tests/test_omi_effective_arguments.py`、`test_market_preflight.py`、`test_tool_policy_omi.py` 與既有 conversation mock；不呼叫外部 refresh 當一般測試。

Pet build 與 Qt bundle 建置可能影響正式資產，採用前先確認既有 isolated output／candidate builder 參數與 owner，將精確命令記入 Progress；不直接執行會覆寫正式輸出的預設 build。M5 啟動／採用命令亦在核對實際候選後記錄，不在計畫中猜參數。

## 停下修正與回退

- 已知錯價、否定反轉、工具假成功、私人資料洩漏、舊回合音訊重播，任何一項失敗都先修正，不以整體通過率掩蓋。
- 為讓測試綠燈而刪掉故障案例、把所有狀態改成 ready、保留整段靜音當預期，均不接受。
- 因縮短而無內容，或只剩「請看畫面」，不算達成目標。
- 每階段保存 task-only diff 與 preimage；回退只逆轉本任務變更，保留其他 WIP。Release 沿既有完整性驗證與先前 pin 回退，不繞過簽章。
- 中央／外部 provider 狀態不符預期，先分層定位；不得廣泛 kill processes、清 DB、改權限、繞過 tool policy 或私自增加服務。

## 參考做法

以下為 2026-11-05 審查時讀到的官方實作，main 會變動；實作採用前固定當時 revision。不直接整套移植，也不據此升級 dependency。

- [Pipecat TTS service](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/services/tts_service.py)：逐 context 記錄是否有音訊、零音訊報錯、連續失敗與中斷分流。採用其失敗可觀測性。
- [LiveKit fallback](https://docs.livekit.io/agents/logic/fallback-strategies/) 與 [TTS adapter](https://github.com/livekit/agents/blob/main/livekit-agents/livekit/agents/tts/fallback_adapter.py)：有限重試、統一音訊格式、已輸出音訊後的保護。Kuro 保留同角色／同中央 owner，不自行跨供應商切音色。
- [GPT-SoVITS TTS pipeline](https://github.com/RVC-Boss/GPT-SoVITS/blob/main/GPT_SoVITS/TTS_infer_pack/TTS.py)：峰值處理、句間靜音、支援模型的重疊銜接。真正串流另行處理，不作為修復語意拒播的替代。
