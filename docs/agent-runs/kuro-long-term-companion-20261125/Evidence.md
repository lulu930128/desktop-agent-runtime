# 來源與隔離驗收證據

下文保留公開評測摘要與重現步驟。逐題評測輸出、正式來源計數快照及含本機環境的原始收據只留本機。[驗證清單](Verification.json) 同時記錄公開證據與本機收據的歷史雜湊。

原始基準為 main 的 c2b3e64c27caaec8c2cba5b213444ddce0d79e03。11/23 Speech、Tool Discovery、既有 Qt 與其他 WIP 保留在同一工作樹。完整起始 dirty patch 沒有另存；baseline 模型比較使用可由 Git 重建的記憶模組。SourceBaseline.json 記錄正式 owner 所見的 211 個歷史檔、2,047 則訊息，以及角色庫 2 筆 active、4 筆待審；正式模型和已載入的 source revision 未取得。

## 容量與成本

三種規模各含三種查詢、每題兩次。相同原始資料的 SHA、來源命中、同步呼叫及 SQLite 寫入計數位於 Baseline.json 與 Benchmark.json。容量測試使用 FTS；沒有呼叫 LLM 或 embedding。100k 樣本每個檔案 1,000 則，單一極長 JSON 歷史的整檔原子儲存仍有成本。

| 訊息數 | 舊／新冷建庫秒 | 舊／新熱查詢 P50 | 六次查詢舊／新訊息列寫入 |
| ---: | ---: | ---: | ---: |
| 1,000 | 0.039 / 0.169 | 35.6 / 2.72 ms | 6,000 / 0 |
| 10,000 | 0.263 / 1.722 | 304 / 2.80 ms | 60,000 / 0 |
| 100,000 | 7.000 / 47.214 | 9,570 / 5.78 ms | 600,000 / 0 |

100k 樣本新索引檔案 59,719,680 bytes，舊版 66,293,760 bytes。這些量測不涵蓋 100k 筆多語向量成本。可選本機 ONNX 模型 118,453,870 bytes，tokenizer 9,081,518 bytes。模型檔 SHA-256 為 98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f，tokenizer 為 2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8。權重版本取自 [模型專案](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/e8f8c211226b894fcb81acc59f3b34ba3efd5f42)。

本機同一短句 25 次 CPU 推論。ORT 預設、1、2、4 執行緒平均耗時各為 3.97、3.16、2.64、2.15 ms，每次 CPU 時間各約 73.1、3.13、5.00、10.0 ms。選用單執行緒以降低與語音、工具工作的 CPU 競爭，可用 KURO_MEMORY_ENCODER_THREADS 調整。這組量測與公開語料的初次建庫時間分開。

## 混合檢索的真實向量成本

同一個重複度高的繁中／日文／英文 corpus 逐段累加，兩則原文形成一個情節向量。索引包含原文、FTS、情節、向量及倒排資料。下表各列是該階段增加的工作量。單程序 CPU，沒有 GPU 推論、雲端模型或付費 API 呼叫。[SemanticScaleOptimized.json](SemanticScaleOptimized.json)

| 累計訊息／向量 | 本段新增訊息 | 建庫牆鐘／CPU 秒 | SQLite bytes | 程序尖峰 bytes |
| --- | ---: | ---: | ---: | ---: |
| 1,000 / 500 | 1,000 | 10.49 / 9.50 | 5,640,192 | 552,308,736 |
| 10,000 / 5,000 | 9,000 | 72.71 / 71.59 | 56,020,992 | 552,308,736 |
| 100,000 / 50,000 | 90,000 | 813.22 / 781.25 | 561,717,248 | 552,308,736 |

100k 完整初建階段合計 896.4 秒。相同 corpus 初版混合查詢 P50 為 5.746 秒，加權召回與批次編碼後為 3.201 秒，最終固定 SQLite posting key 查找順序、沿用同一已建投影後為 0.625 秒，八次最慢 1.623 秒。最終重放核對 corpus SHA、查詢計畫、0 次熱查詢重建、0 次 canonical 歷史檔讀取及 0 次 SQL 資料寫入。熱查詢仍需讀取與查詢相關的 posting，常見詞與重複語料會提高成本。日文與英文陶藝問題、精確識別字皆找回來源。庫存控制題兩次都未命中指定字串「盤點」。[初版量測](SemanticScale.json) · [最終查詢與計畫](HotPath.json)

可依本機資源選擇 FTS 或配置多語 encoder。FTS 的 5.78 ms 來自另一組精確詞 corpus；語意的 100k 量測包含 50k 個實際向量。未量測整機功耗、電費或其他程序的 GPU／VRAM。短期查詢成績無法外推數年真實的對話品質。

在 repo 根以全新隔離工作目錄重放：

```powershell
$state = Join-Path (Resolve-Path .) ('devtools/original-git-web-host-20261010/.runtime/companion-scale-' + [guid]::NewGuid())
& $python -B "$run/semantic_scale.py" "$run/recheck-scale.json" --keep-for-analysis $state
& $python -B "$run/hot_path_replay.py" $state "$run/recheck-scale.json" "$run/recheck-hot.json"
```

## 回答與來源定位

同一組八道合成題、資料與 qwen2.5:7b manifest 固定，seed 17、temperature 0、本機 CPU。每題的輸入、gold 來源、實際片段、答案、token 與耗時見 [ModelFinal.json](ModelFinal.json)。四題先導結果保留在 Quality.json。

| 路徑 | Strict exact | 輸入／輸出 token 合計 | 模型總耗時合計 |
| --- | ---: | ---: | ---: |
| Git baseline | 4/8 | 2,007 / 24 | 34.30 秒 |
| FTS | 5/8 | 960 / 27 | 21.87 秒 |
| 多語向量 | 7/8 | 1,227 / 31 | 16.57 秒 |
| 混合 | 6/8 | 1,200 / 32 | 9.89 秒 |

混合兩題答「37 歐元」「58 euros」，字串評分要求只回數字而計錯。兩題無來源皆回 UNKNOWN。這八題無法估計自然使用中的錯誤記憶率。模型暖機順序會影響上述累計耗時。另一次先暖機、每題交替先後的串流實測，baseline／混合的請求至首段非空文字 P50 為 3.285／1.773 秒，完成 P50 為 3.541／2.236 秒；這是模型端到客戶端時間，另計查詢與 Qt 呈現。[Streaming.json](Streaming.json)

公開 LoCoMo 固定 revision 3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376、PYTHONHASHSEED=0。10 組對話共 1,986 題，1,977 題可對到 gold 來源。每題最多 4 片段，可引用多個原始 turn。baseline／混合的平均來源 recall 為 9.52%／53.16%，precision 為 3.00%／10.70%，查詢 P95 為 104／52 ms。多跳 281 題的 recall 為 6.24%／19.65%，precision 為 4.80%／10.15%。低精確率與多跳漏失仍會影響實際回答。此測量只對來源評分；資料不含當事人的私人歷史。逐題結果與評分分母保存在 `PublicFinal.json`（僅本機）。[公開語料授權](https://github.com/snap-research/locomo)

Formation.json 有 6 個應保存的陳述與 6 個不應自動保存的輸入。人工模式 6 個語意陳述全部進入候選，選定類型且授權的模式形成 6 筆 active，6 個反例均無 active；引述他人偏好的反例仍會由原 heuristic 產生候選。三組各重送整套輸入一次，重複新增均為 0。樣本數不足以估計自然使用中的普遍誤存率。

## 實際傳輸與發布層級

QtReplay.json 在隔離環境使用 QtRuntimeChatClient、WebSocketHandler 的 conversation trigger、BasicMemoryAgent、process_single_conversation 與本機 qwen2.5:7b。第一個角色明示保存「無糖抹茶」，第二個角色在新對話答「無糖抹茶」，兩輪皆由 Qt 讀回並核對 canonical History。連線握手與 ServiceContext 使用 fixture，此案例沒有真人桌面、語音或 Live2D 裝置操作。正式 profile、正式版本更新、私人加工及正式桌面 E2E 為 Unverified。

QtModelSwap.json 使用兩個不同的程序。在第一個程序用 qwen2.5:7b 寫入後結束，第二個程序改用 qwen3.5:9b-q4_K_M、新角色及新對話，回答「無糖抹茶」。兩輪皆有 Qt 與 History 讀回。QtPanel.json 另以真實 KuroQtLauncherWindow 與 QWebEngineView 在 offscreen 平台載入 staging bundle，讀取第 95 筆記憶、實際輸入搜尋字串、檢查修訂輸入框及維護按鈕。這個面板的對話連線和環境是隔離 fixture。

候選面板 build 指紋 `85a8c575346ee9fd4d7582f261764d2bccafa53949b550c77f4f6161a619620e`，manifest SHA-256 `c2868781454da7c57ea2de18341ffcf7d10c33eb50b553c6bfdd90baae75fe27`，正式 pin `1fa9b1646a024b573fabe019e4fd940f0e34962f87db6b46cba52408290f3e2a`。隔離的 WebEngine 讀回同一候選指紋。[QtPanel.json](QtPanel.json)

額外執行歷史 W6／W8／W10 驗收時，W6 三項依賴已移除的 widget／建構方式，W8 一項固定早期工具來源 hash，W10 一項要求工作樹產物已等於正式 pin。保留這五項非通過結果。現行 22 個 Python 模組共 241 個案例通過，另有 70 個桌寵、語音傳送與 Core Work 邊界案例通過；Node 歷史、語音與桌寵呈現 29 個案例通過。程式、隔離傳輸及正式安裝的證據各有範圍。[Verification.json](Verification.json)

## 重放

從 repo 根執行，下列輸出路徑使用新的本機檔名。LoCoMo 會抓取上述固定版公開資料，其餘重放依賴已備妥的本機套件及模型。quality_replay 只啟動隔離的 loopback Ollama 並清理該次 server；需暫存一份約 4.7 GB 的本機模型。

```powershell
$run = 'docs/agent-runs/kuro-long-term-companion-20261125'
$python = (Resolve-Path '.\envs\kuro-llm310\python.exe').Path
& $python -B "$run/replay.py" "$run/recheck-baseline.json" --baseline
& $python -B "$run/replay.py" "$run/recheck-capacity.json"
& $python -B "$run/formation_replay.py" "$run/recheck-formation.json"
& $python -B "$run/quality_replay.py" "$run/recheck-quality.json"
& $python -B "$run/quality_replay.py" "$run/recheck-qt.json" --qt-only
& $python -B "$run/quality_replay.py" "$run/recheck-swap.json" --swap
& $python -B "$run/quality_replay.py" "$run/recheck-longitudinal.json" --longitudinal
& $python -B "$run/qt_panel_replay.py" "$run/recheck-panel.json"
& $python -B "$run/semantic_scale.py" "$run/recheck-semantic-scale.json"
& $python -B "$run/quality_replay.py" "$run/recheck-streaming.json" --longitudinal --stream-from "$run/recheck-longitudinal.json"
& $python -B "$run/migration_replay.py" "$run/recheck-migration.json"
$env:PYTHONHASHSEED = '0'
& $python -B "$run/locomo_replay.py" "$run/recheck-locomo.json"
```
