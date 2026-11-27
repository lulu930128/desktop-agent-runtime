# Kuro 語意對齊雙輸出 v2 — 實作計畫（2026-10-31）

> 原則：先固定本計畫，後實作；以最小必要修改取代額外 LLM／平行 manager。  
> 專案：\`C:\project\desktop-agent-runtime\`  
> 狀態：本檔為本輪約定的規格，工程及 E2E 驗收分開記錄。  
> 前置成果：\`docs/agent-runs/kuro-multilingual-speech-20261031/{Plan,Progress,Evidence}.md/json\`（既有 frozen v1，不改寫）。  

## 0. 實際缺陷與範圍

2026-10-31 13:09 Kuro 對話已有單輪雙輸出 \`kuro.speech-lanes.v1\`；正常語音 Bridge 呼叫次數 0，日文稿直接到 GPT-SoVITS。

對照畫面與中央合成日文原稿發現：
- Display 說「取得市場資料遭阻擋」以及「公開網路查詢／先看檢查清單」兩種方案；Speech 以「無法直接取得」概括原因，僅口述公開網路查詢，漏掉另一選項。
- \`[neutral]\` 出現在 Display：目前 \`live2d_expression_prompt.txt\` 仍要求 LLM 內嵌 \`[neutral]\`，新私有 speech \`emotion\` 欄位已存在，兩種控制契約並存。
- 中央 GPT-SoVITS 對 \`S&P500\`、\`NASDAQ\`、\`VIX\` 等縮寫及 \`、。\` 標點正規化存在可見品質問題；此為獨立的 TTS 發音層，不代表語意對齊失敗。

**本輪只修復 Display／Speech 的語意對齊、技術內容摘要與新舊情緒契約衝突。** 不動其他對話正在修的 MCP、Tool Router、權限與金融資料；不重做模型預載／冷熱 TTS／分段聲學推論或 UI 排版。

## 1. 產品目標與非目標

### 必須達到
1. **一次主 LLM 任務仍產生 Display 與指定語言 Speech**，不額外呼叫第二輪 LLM 來翻譯、摘要、分類、語意審核或修稿。
2. Display 是完整資料：程式碼、URL、JSON、Log、Table、價格、錯誤、來源、缺口及詳細解釋按原串流顯示與儲存；History、Memory、tool args 不能出現私有 speech JSON 或控制 marker。
3. Speech 依現有 \`brief / summary / detailed\` 設定生成自然口播，預設日文；可省略非必要細節與原始技術 payload，但**不能反轉/遺失會改變決策的失敗、未驗證、否定、數值、前提、資料時效，以及使用者真正需要知道的不同選項**。
4. 應付 URL、inline/fenced code、Windows/Unix path、traceback、table 與混合文字：Display 原樣顯示；Speech 解釋意義或說「詳情在畫面上」，不可直接念長 URL、代碼、路徑或 raw JSON。
5. 情緒控制改為獨立 \`emotion\` 欄位；雙輸出模式**不要求並盡可能不出現**舊式 \`[neutral]\` 等標籤於 Display；保留可用的 Live2D 情緒事件與 legacy route。若模型仍輸出孤立情緒標記，需只剝離可信的控制標記而不破壞字面、程式碼示例及其他 Markdown。

### 非目標
- 不處理 MCP \`invalid_arguments\`、市場查詢、Tool Router、其他專案的設定；當工具結果是失敗，只在 Speech 裡忠實說明。
- 不宣稱僅用非 AI 規則就能驗證中日語意完全等價，不新增高成本 cross-language judge。
- 不改 GPT-SoVITS 中央模型、預載、讀音詞典、音訊傳輸、Live2D 視窗、Qt 前端 release pin；縮寫發音先留下獨立待辦（若要定點修讀音，須明確限於既有 pronunciation dictionary 且不能和本輪對齊混測）。
- 不重新啟動、部署、下真實付費 LLM/TTS 測試、commit 或 push；正式口播由使用者在下一輪實機驗證。

## 2. v2 雙輸出契約

僅在 **tool-free 最終回答**、完整 Display 內容之後輸出私有 footer；主 LLM 自己提供少量 \`anchors\` 與 \`speech\`，並保留原本的 \`emotion\` 欄位；既有 \`kuro.speech-lanes.v1\` 保留為 rollback/compatibility。

建議樣式（協定欄位可按既有 parser 需要作最小等價調整，但須保留語意）：

\`\`\`json
{
  "contract": "kuro.speech-lanes.v2",
  "locale": "ja-JP",
  "policy": "summary",
  "anchors": [
    {"id": "a1", "source": "執行失敗，尚未驗證修復", "importance": "required", "kind": "status"},
    {"id": "a2", "source": "可以重試或先查看診斷清單", "importance": "required", "kind": "options"},
    {"id": "a3", "source": "value = int(\"10\") + 5", "importance": "display_only", "kind": "code"}
  ],
  "speech": [
    {"source_ids": ["a1"], "text": "処理は失敗しており、修正の動作確認もまだ完了していません。"},
    {"source_ids": ["a2", "a3"], "text": "再試行するか、先に診断項目を確認できます。修正コードは画面にあります。"}
  ],
  "emotion": "neutral"
}
\`\`\`

- \`source\` 只可引用**同一次最終 Display 真正出現的短片段**（不得引用假資料、另一回合工具結果、想像中的內容）。ID 同回合唯一。主要 \`required\` 保持少量（一般聊天可為 0，技術回答依情況約 1–5 個；解析總量設有適當上限以避免延遲及濫用）。
- \`required\` 的每個 ID 必須被至少一個 Speech segment 引用，\`display_only\` 可以僅留畫面但不可當作重要失敗／否定等資訊的替代品。
- Speech segment 文字需是**可自然朗讀的目標語言**，不可含 URL、code fence、raw path、trace/table/JSON；應保留重要數字與條件，但不必念每個符號。
- 「完整答案」不再與 Speech 逐字等價；對齊目標是決策與必要資訊一致，而不是相同句數或長度。
- 盡可能重用現有 \`SpeechLaneParser\`、\`route_speech_lanes\`、\`SpeechPolicyEngine\`、\`queue_generated_speech\` 與 \`TTSTaskManager\`；**不要建立另一個 parser/manager/queue**。v2 marker 與 v1 marker 必須能識別、且在 fenced/inline code 的字面範例中保持 Display 不被吞掉。
- 任一 footer 缺失、JSON malformed、overlong、contract/locale/policy 不符、anchor 重複/找不到 Display、required 未覆蓋、未知引用、技術 payload 漏入、數值/狀態基本衝突 → 保留全部 Display、略過該 turn 的 Speech、留下簡短 machine-readable reason；不能自動重呼叫另一個模型或切回可能改變語意的 Bridge。若只是一般聊天沒有錨點，不因缺錨點本身失敗。

## 3. 一致性檢查的能力邊界

使用低成本 deterministic validator，**不假裝具有跨語種自然語意理解能力**：
1. 欄位版本／型別／長度／重複 key／anchor 數量、ID、引用完整性。
2. 每個 anchor 的 source 在同次 Display 有**真實可核對的文字位置**；避免只因模型給出 \`source_ids\` 就當作同義。
3. \`required\` coverage：所有 required anchor 至少有一段 Speech 對應；多方案回答應保留不同實際可選的行動（不要只說「有選擇，請看畫面」）。
4. 對可用 **精確字元或正規化數值** 比對的重要價位、停損、比率與錯誤代碼作結構性 guard；數字口語讀法、中文/日文失敗/未驗證詞彙需以有界且可測的規則處理，**無法可信判定就降級/標為未驗證，不宣稱必然正確**。不要用單純全文 digits 迫使摘要念所有表格數據。
5. URL／Code／JSON／Table／Log 保留顯示，但不可從長 code/log 純刪字元組出語意；Speech 用 LLM 直接寫好的自然摘要。
6. 不要讓 validator 變成另一個大型規則引擎。複雜誤判比漏掉枝節更糟；無法確認跨語義時留給實機／Fixture 評估，不因所有非重要內容而強制靜音。

## 4. 正式處理流程與 Ownership

\`\`\`text
User text / ASR transcript
       ↓
Existing conversation LLM and optional tool result (unchanged)
       ↓ same final generation, Display + v2 anchor/speech footer
Existing route_speech_lanes / SpeechLaneParser
       ├── Display deltas → Qt Chat / History / Memory（保留原樣）
       └── private v2 speech_lane event
                 ↓ Existing SpeechPolicyEngine: validate anchors / locale / technical payload
                 ↓ Existing queue_generated_speech (or minimal adaptation)
                 ↓ Existing TTSTaskManager → central GPT-SoVITS → Electron / Live2D
\`\`\`

- 保留原先 streaming flush、tool continuation、timeout/cancel、final ack、fail-stop chunks；v2 segmentation 轉接時最多仍使用既有三段語音任務而不是新增多個並發 TTS。
- 口播及 anchor JSON 僅短期隨本輪處理，不放入 long-term memory 或 Log 私人內容；診斷只記狀態 reason/count/latency 及來源版本。
- 設定 owner 沿用既有 Launcher \`chat_speech\`，\`locale/policy/route\` 不新增 Qt 控制項、不把 speech policy 寫進 character memory。
- 若原有 Live2D Expression Contract 仍強制模型輸出 \`[neutral]\`，應在雙輸出系統 prompt/source composition 最小範圍停用/覆蓋該規則；legacy 回退仍可沿用標記。不可無條件刪掉程式碼或 Markdown 字面 \`[neutral]\`。
- 当前另一 Codex 工作正處理同 repo 的 MCP／Tool Router，**絕不覆寫或回退**其變更；避免修改 \`mcpp/*\`、\`tool_*\`、市場層；若必要需讀改 \`basic_memory_agent.py\`，只精準 patch 語音相關範圍並先核對并行變動。

## 5. 實作步驟與 Gate

### G0：基線與衝突檢查
- 確認當下 Git branch/dirty diff、本輪 Plan SHA、MCP Codex work-in-progress 的重疊檔案；對會更動的 source 記錄精確 byte/hash 基線，不重置其他 dirty work。
- 對照 13:09 TTS 真實原稿與 Display 截圖，建立 fixture 但**不要使用真實私人歷史文字作測試資料**；改寫成等價 synthetic 中日句。

### G1：v2 Prompt／Footer 與 parser
- 一輪主 LLM 提示：完整 Display＋僅少量 required/display-only anchors＋自然口播 segments＋情緒；不重複翻譯。
- 將 parser 擴充識別 v2 並保留可切回 v1；支援任意 token boundaries、tool event 前 flush、fenced/inline marker literal、不洩漏 marker/JSON；malformed 始終保存 Display。
- 針對同一次 final Display 實際 source 與 anchors 進行驗證，不引用工具中的未顯示原始 payload；如果費用／延遲太高，以少量錨點為預設，不要求所有句子都加錨點。

### G2：Speech 驗證／TTS 轉接
- 只接受全部必要 required anchor 已覆蓋的語音。URL／code／stack／JSON／table 原文不進入 TTS；保留數字、錯誤與必要限制。可以用目前的有序、群組 fail-stop TTS；不新增翻譯 API 或播放系統。
- 失敗時 display-only／理由可觀測，不能把半段內容送去播放，也不能讓 TTS failure 卡住 conversation completion。
- 以相同設定 brief／summary／detailed，改變詳盡程度而不移除必要 anchors。

### G3：情緒協定收斂
- 修除雙輸出時強制模型在回答文字前輸出 \`[neutral]\` 的衝突 Prompt，保留私有 \`emotion\` → Live2D event。保留使用者真正要求字面 \`[neutral]\` 的技術/Markdown 例子。
- 不影響 legacy prompt 與 Live2D emotion/event test。

### G4：最小必要驗證及 Reviewer 驗收
- 定點 unit/fixture：
  - 一般中文、日文、英文／混合輸入 → 正常 Display＋日文 Speech。
  - 三種 speech policy；簡單聊天可無錨點。
  - 工具失敗／部分成功／未驗證／stale／否定；價格 100.5、停損 95；兩個可選方案完整保留。
  - code fence（含 v1/v2 marker 字面）、inline code、URL、Windows path、stack trace、JSON/table、escape、長回答與碎片化 Streaming。
  - required 缺漏、重複 ID／未知 ID、source 不在 Display、JSON malformed、語言不符、speech 裡直接塞 technical payload、取消／tool continuation／legacy v1 rollback。
  - \`[neutral]\` 不再污染正常 Display，表情事件仍發出且 literal code 文字無損。
- 靜態語法與相關現有 Python tests；無 UI/central changes 時不做 Qt/Electron 全套重建。Reviewer 獨立審核真實 Diff 與改動後行為，與並行 MCP 變動分離。
- 紀錄 Source Ready / Targeted PASS 與未驗證項目；當次不做有費用的真人 LLM／GPU 音訊推論，也不自行重啟服務。測試資料不等於真實跨語言語意保證。

### G5：使用者下輪正式實機驗收
- 用短問答、含 URL/code/log 的技術問題、兩種方案與有「失敗／未驗證」的工程問題各問一輪；對照 Qt Display、私有 v2 speech segment 與中央 TTS input；確認 Speech 不漏必要條件。
- 比較目前 13:09 回合「兩方案 → 漏掉一方案」的問題是否改善；錄音或實際聽感驗證日文標點／縮寫讀法仍屬獨立品質待辦。
- 對比主 LLM completion → speech ready → 首段 TTS → Electron playing；新增 anchors 有額外 tokens，若延遲惡化應按數據調小 anchors 而不是額外 AI call。
- 如有回歸，使用記錄的本輪精準 Diff 將新 v2 提示／解析／驗證回退到 v1，保留既有完整文字、設定、記憶和此前 TTS 熱路徑；不 reset 其他人的 WIP。

## 6. 完成定義／文件交付

- \`Plan.md\` 本輪固定，不因 Codex 需要交付而新建相互矛盾的 Plan。
- 同目錄建立 \`Progress.md\`，記錄真實 Job/Model/Effort、修改檔、測試命令與成績、Baseline、source/installed/runtime 的版本差異、Known limitations、Rollback/Next actions。
- **Targeted tests PASS 不等於真實語音對齊已改善**；只有使用者 G5 真實對話的 Display 和 TTS input／聽感比對後才可認定改善。
- 不自動做 git commit/push/restart/deploy；不額外引入 JSON Schema 平行 source of truth 或新 Service。
