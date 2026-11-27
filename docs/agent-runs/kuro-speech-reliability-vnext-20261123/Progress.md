# Kuro 語音 VNext 實作與驗證

採用 M0 的 C 混合式。正常回合沿用同輪 Display 與 Speech，只有失去語意、缺少關鍵內容或不適合口述的部分需要修稿。詳細／全文朗讀依完成的 Display 順序取材。實體 Pet 已完成長篇播放，正式 Qt 輸入與 History 整條路徑仍待驗證。

## 修正與責任邊界

| 原因 | 既有 owner 的修正 |
|---|---|
| 中段 URL 或 code 令整份 footer 拒播 | SpeechLaneParser 保留通過 anchor 結構驗證的私人草稿。recover_speech_lane 略過只顯示的原始載荷，保留獨立且可歸屬的正常語句。含程式條件的句子由 render_speech_only 依原始來源重述，避免直接刪除條件使否定反轉。歸屬不明時回到完成的 Display。 |
| 短答漏關鍵限制，或修改讀音後改變數值 | 可用的原稿優先。價格、停損角色、數值及可辨識的否定／資料狀態與 Display 比對。遺漏的關鍵句可單獨補述；讀音替換若改變受保護資料，該單元使用原讀稿。 |
| 工具探索結果蓋過實際執行 | Conversation 依原工具事件及 call ID 取得終態。當讀稿漏報明確的 failure、unknown、cancelled，使用對應的日文補述。市場查詢和決策仍由工具 owner 負責。 |
| 全文被摘要、超長 footer／純漢字被拒 | 詳細模式按已完成的 Display 渲染，有欄名的表格列攜帶欄位語意，程式區塊只顯示。可直接朗讀的日文逐句保留。取消舊 footer／speech 字數和段數的內容上限，純漢字日文可進入 TTS。Settings 的預設策略與使用者當輪要求分別處理。 |
| 合成失敗拖掉獨立後段 | 依實際發音文字、中央 2,000 字與 16,384-byte JSON 契約分段，優先取自然句界。短且同來源的片段可保留一個 WAV。以共同的來源 anchor 表達依賴；後續獨立來源可繼續合成。 |
| 前綴播放成功卻回整輪 completed | TTSTaskManager 為每段分配 segment_id。Pet 依 playing、ended、failed 回報。PrimaryConversationOutput 比對必要音檔與 ended 回條，再由原 finalizer 併入渲染、合成缺段。畫面提示音使用 fallback 終態。 |
| 90 秒等待、取消、跨回合 | 依尚未結束的實際媒體長度和 Pet 既有無進度 watchdog 等待。舊 request 或音檔 callback 無法結束新回合。停播回報 interrupted，可列出仍缺的段落。 |
| History 的控制字串與字幕缺字 | 完成的 Display 在語音等待前交給原 History owner。launcher-interrupt 不再成為助理回覆，中斷系統事件保留。Pet 依 display_append 逐字附加，保留重複文字、換行與空白。 |

## 驗證紀錄

[validation.json](validation.json) 收錄 request ID、音檔秒數、逐段事件、缺段與恢復連線回條。實測使用真正的配置、模型、中央 Voice 及執行中的 Pet，透過隔離的 primary sender，並設 skip_history。History、Qt 的來源測試另列。

| 情境 | 觀測 |
|---|---|
| 長篇紅例 | 初次真實模型產生 710 字 Display，合計 22 次模型呼叫，0 段 WAV。 |
| 日文全文 | 修正後兩次收到 24/24、19/19 段 ended。WAV 合計 211.50、178.36 秒，含生成耗時 230.44、193.23 秒。兩次都含指定末句。第三次以封裝的重現腳本得到 16/16 段 ended、144.76 秒媒體、160.34 秒全程。後兩次的全文與口播輸入忽略排版空白後逐字相符。 |
| 正常短答 | 一次模型呼叫，8.30 秒 WAV，Pet 收到 playing 和 ended。 |
| 中段技術載荷 | 87 字 Display 保留原始網址與 retry = false。日文說明測試未成功、操作未確認及目前不能執行，1 段 13.14 秒播完。 |
| 中文全文轉日文 | 「まだ検証されていない」一度被列為缺段。修正後價格 100.5、停損 95、操作失敗、來源未驗證和隔日再查全部保留，3/3 ended。 |
| 無句號 | 129 字日文送中央合成，25.74 秒 WAV。原文和口播輸入逐字相符。Sherpa ONNX 回聽最後 9 秒，辨識出「最後に、家のあかりが見えました」。 |
| 中段合成故障 | 在原 TTS 呼叫邊界對第 2 段注入 unavailable，第 1、3 段仍走真實中央合成及實體 Pet。Pet 的 ended 為 [1,3]，Conversation 回 partial 並列缺段 [2]。 |
| 取消與下一輪 | 播放開始後由 Pet 原 stop-playback 停播，Conversation 回 interrupted，重測列出未完成的 [1,2,3]。另一段短答用新的 request ID 播完。快速跨回合、舊回條與回連在來源測試覆蓋。 |
| 工具結果 | 真實動態探索後執行唯讀 omi_read_data_freshness。外層 error，工具 owner 的 execution_status 為 unknown、reason_code 為 timeout。口述保留未確認，沒有宣稱成功。此次沒有可驗證的市場結果。 |
| 中央邊界 | 直接測試 12、47、96 字，各得到 2.82、14.64、28.64 秒有效 WAV。正式端對 2,001 字回 400 invalid_text，對 2,000 個非 BMP 字元形成的 24,068-byte JSON 回 400 invalid_json。 |
| 2,011 字連續日文 | 原切法 2,000 + 11 字。第一段連續兩次得到 503，其中一次保留碼 inference_unavailable；11 字尾段兩次都能合成。改以已驗過末句的 129 字作選擇句法斷點的參考，實際分成 111 至 139 字，共 16 段。相同原文 16/16 段都得到可解碼 WAV，音訊合計 582.72 秒，ASR 在末段辨認出黃色雨傘及記錄結束。這是中央服務與檔案回聽證據，該近十分鐘案例未送 Pet。 |
| 等待對照 | 以同一 WAV 重播四次耗時 115.016 秒，收到 4 個 ended。此案例只驗證傳輸及播放等待。 |

### 重現方式

本輪 Python 169 項與 Node 25 項通過，Pet／Qt TypeScript 檢查通過，Pet renderer build 通過。以 repo 根目錄執行。Python 涵蓋 Speech Parser、語意、讀音、Queue、中央 client、History、Qt 與 Dynamic Tool。Node 涵蓋 Pet 的字幕、取消、跨回合及缺段回報。

~~~
$env:PYTHONPATH='tests;Open-LLM-VTuber/tests;Open-LLM-VTuber/src;Open-LLM-VTuber'
$env:PYTHONUTF8='1'
.\envs\kuro-llm310\python.exe -B -m unittest test_speech_vnext test_concise_tool_speech test_speech_semantic_alignment test_multilingual_speech test_first_speech_latency test_tts_reliability_phase1 test_g3_conversation test_qt_display_stream test_central_voice_client test_speech_long_inventory test_dynamic_tool_turn
node --test tests/g3_presentation.test.cjs tests/multilingual_speech_frontend.test.cjs tests/qt_display_history_frontend.test.cjs
npm --prefix pet-electron run check:renderer
npm --prefix devtools/original-git-web-host-20261010/frontend run check
~~~

[live_probe.py](live_probe.py) 可重跑 short、mixed、zh-detail、no-punctuation、long、tool、fault、cancel。每次分配獨立證據目錄。Pet 空閒時逐案執行，probe 會暫時切換 Pet 連線，並在 finally 恢復原 URL。tool 案例使用實際唯讀工具，fault 只注入中段合成故障。

~~~
.\envs\kuro-llm310\python.exe -B -X utf8 docs/agent-runs/kuro-speech-reliability-vnext-20261123/live_probe.py long
~~~

[capacity_probe.py](capacity_probe.py) 會依 Launcher 所選的中央 Voice 設定重跑 2,011 字無句號案例，逐段記錄 HTTP、WAV 與本機 ASR。實際會進行較長的合成運算。

## 正式採用範圍

以原桌寵啟動器啟動後確認 Qt、LLM、Pet 與 voice-runtime。Pet 由原 renderer build 與 reload-frontend 載入，實測回報新版 playing、ended 及 ended_segments。中央 health 有 service/protocol/voice，沒有執行中程式的來源雜湊。正式 Backend 啟動後本次仍有來源修正，因此其 PID 無法證明已載入最後版本。

Qt 仍選取 2813daee6633259de26c0fb6fdcc22322815dc4e15f801d50425c2fd12b398ab。VerifiedOwnerBundle.load 通過簽章、lineage 與 5 個資產校驗。原 builder 回報 Immutable Git source mismatch: src/work-panel/main.ts。新版缺段標籤通過 TypeScript 檢查，目前正式 bundle 未採用。測後另以 Pet 控制介面讀回 idle，連線已回到本機 23456 的 pet-presentation 角色。GUI 自動化此輪僅列出 Pet。正式 Qt 手勢送出、正式 History 回讀及喇叭聽感仍待驗證。

正式採用時，由原 Launcher 載入最終 Backend，核對已採用的 Qt bundle。從原 Qt 送出長篇，依同一 request ID 對照 Display 結尾、每段 TTS／WS、Pet ended、Conversation 終態和 History 回讀；再於播放途中停止並送出下一輪。採用缺段 UI 時需先處理原 Qt source lineage 分歧，再沿其簽署流程產出候選。

## 共用檔與回滾

[task.patch](task.patch) 含本次產品程式、測試與重現腳本。[changed-files.json](changed-files.json) 列出逐檔前後 SHA-256，前像是本次進場時的 dirty working bytes。patch 在隔離目錄做過正向、逆向逐檔還原。證據、音檔、Settings、模型、Qt pin 與建置輸出不在 patch 內。

Tool Discovery 交付的 task.patch 雜湊是 a1fe852615254ecdb5870acdc06aa98b1933c75692acf389dd70ae9714d5ede6。本次查詢時該 Job 容器仍是 running。交集為 kuro_launcher/qt_web_adapter.py 和 frontend/src/owner-presentation.ts，兩者的語音前像都等於 Tool Discovery 的交付後像。交付後其他人再動過的檔案列於 manifest 的 independent_changes_since_delivery。

回滾前核對 manifest 的 after_sha256，再執行 git -c core.autocrlf=false apply --reverse --check docs/agent-runs/kuro-speech-reliability-vnext-20261123/task.patch。內容匹配時可逆向套用；已交疊其他 WIP 的檔案只回退語音 hunk。Pet 從回退後的來源 rebuild，再由原 reload-frontend 載入；本輪前產物也留於 .tmp/speech-vnext-20261123/pet-renderer-before。Backend 由 Launcher 載入回退版本。既有 Qt 簽章選擇器未變更。未 commit 或 push。

## 2026-11-23 正式採用更新

17:47 修正版已由原 Launcher 採用。正式 Qt 五輪驗證完成，含 101.86 秒全文、播放中斷提示、下一輪及 History 重開。最新狀態見 [正式桌面驗收](FormalAdoption.md)、[逐輪收據](formal-validation.json) 與[本輪修復增量](formal-task.patch)。
