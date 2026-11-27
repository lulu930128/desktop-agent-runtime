# Kuro Speech VNext 正式桌面驗收

2026-11-23，台北時間。從 Windows 通知區的 Kuro 選單執行「重新啟動 Kuro」，由原 Launcher 接手服務。最終版本從同一個正式 Qt 普通對話視窗完成五個回合，中斷後的下一輪也已播完。測後 Pet 回到 idle。

## 採用身份

| 層級 | 可核對的證據 |
| --- | --- |
| Source | dirty main 的 HEAD 為 c2b3e64c27caaec8c2cba5b213444ddce0d79e03。前輪 24 檔語音後像在進場時全部相符。此輪五檔增量以前像工作檔為基準。 |
| Qt 原簽署發行 | 前輪的 immutable main.ts 與原 Git blob 不同。此次進場時既有 owner 已將工作面板變動納入其 patch，六個 immutable input 均可對回 995c23c7c8d1be62000229d58610d2214f3bb745。既有合法發行指紋為 1fa9b1646a024b573fabe019e4fd940f0e34962f87db6b46cba52408290f3e2a，manifest SHA-256 為 fc759d5a95cfa53b0997e3d57ca68dc1c9d40675be9419d10de7a38b0a38ae9d。原 builder 的 --verify 重新驗過簽章及五個資產。 |
| Running Qt 與 Frontend | PID 136684，17:47:14 啟動。Launcher 在已驗證的 prepare_owner_presentation 回傳後記錄相同 bundle 指紋及本身 PID。從該 PID 的真實 WebEngine 視窗送出對話與停止，經 Windows UI Automation 讀回訊息和狀態。 |
| LLM 與 Core | Launcher 的子程序 run_server.py PID 130300，17:47:19 啟動，監聽 23456。Core PID 138072。實際短答與長答產生 kuro.speech-lanes.v2、具 request ID 的 speech_timing、逐段 WS delivery 及 Pet 回條。取消後收到修正版本才會發送的同 ID Qt 中斷狀態。 |
| 中央 Voice | PID 34284，18890，voice-runtime protocol 1，已載入 kuro 1.0.0，package digest 29f7a0dfa2c8ce5d84758f17ce0dc7f4cfdc485fc54408808611d6a93f8784f0。沿用原服務。中央回報的模型與 voice package 可識別，執行中 Python 原始碼雜湊未知。 |
| 生效設定 | Launcher 的預設 ja-JP / summary / dual_lane。conf.launcher_runtime.yaml 選取 gpt_sovits_tts、日文、kuro、speed_factor 1.2、中央 18890/tts。全文要求在這份日常設定下獨立完成。 |
| Pet | Electron PID 124772，17:47:38 啟動，instance 32eb415bb859427da415726d6c721987，23567。連線角色 pet-presentation。實際 playing / ended 事件指向 pet-VPGChSYm.js，檔案 SHA-256 為 bb9e2b401ec4f5fc953406045f2ccdbe91453c8eef65abe99d1ac00eadb2159f。 |

## 正式 Qt 案例

下表的段數來自實際 Pet renderer 的電子播放事件。完整回合都逐一比對段序、中央成功 WAV 的大小、WS 音訊時長、Pet receipt、Conversation 終態、Qt speech status、Qt Display 原文雜湊及 History 對話。完整 UUID、每段秒數及證據路徑收在 [formal-validation.json](formal-validation.json)。

| 案例 | request ID | 實測 |
| --- | --- | --- |
| 日常短答 | 6b1c7ca380a54a52bd737a633d00e123 | 1/1 段 ended，7.50 秒，17:51:02 completed。 |
| URL、程式、失敗與未確認 | 9e04553193e6443988bfcb607033260b | Display 與重新打開的 History 均保留 URL、retry = false 與日文結論。唯一送播的 WAV 為 581,164 bytes、9.08 秒。離線 ASR 辨識為「テストは失敗し、結果はまだ確認できていないため、現在は実行できません。」1/1 ended。 |
| 全文朗讀 | f87e0a74c893492db927972d4d505f4b | 日文 Display 418 字元含空白換行。除空白外逐字等於要求朗讀的全文。13 個中央 WAV、13 個 WS 段、Pet 依序 playing 與 ended 各 13 次，合計 101.86 秒。17:54:32 Pet、Conversation、Qt 都是 completed，Qt missing 為空。 |
| 播放中停止 | 2f58efe0764d4a2e94a8197c428307ed | 規劃 10 段，第 1 段 ended，第 2 段 playing 時按正式 Qt 的「停止目前輸出」。17:59:03 Conversation 取消、Pet ack interrupted、Qt interrupted，視窗可見文字確為「語音已中斷。」。停止後未見此 ID 再開始播放。 |
| 停止後下一輪 | 34090b47e1964af89dc429e51cca40dd | 重新輸入、送出。單元修復產生 ready，以新的 ID 播放，1/1 段 ended，2.98 秒，17:59:25 completed。History 可重讀「次の散歩は明日です。」。 |

全文末句在 Qt 收到的 Display 和重開的 History 都是「家の明かりが見えました。」。第 13 段 WAV 為 165,164 bytes、2.58 秒，Pet 已播至 ended。本機 ASR 辨識成「家の居のかりが見えました。」，「明かり」的實際發音與真人聽感仍待確認。

## History 重開

試驗使用獨立新建的對話 2026-11-23_17-50-34_9878ff5afc744c728324da07ec679a48。五輪結束後以 Qt 開啟另一個空白對話，確認畫面上的全文末句消失。從 History 清單點回測試標題後，持久 metadata.last_opened_at 更新為 17:59:52。從重建的 Qt 文字節點核對五則使用者訊息及五則 AI 回答，移除尾端空白後 10/10 完整相符。五次 Qt 終態的完整 Display SHA-256（含尾端換行）也分別等於持久 AI 訊息。History 另有一筆 system 事件，AI 訊息未混入 launcher-interrupt。逐輪播放狀態留在 Runtime 收據。

## 中斷修復與回歸

17:38 版本的正式 UI 重現了問題。request 8ea7662afb49408ea0ca229c1c4ae4ca 在播放中被停止，Backend 已取消，但 Qt 沒收到可呈現的 speech-status interrupted。停止路徑原先移除了 primary output 並只送 control。修正沿用該 output 傳送帶範圍的語音終態，留到下一輪或斷線，以便接收原輪 Pet 回條。在已結束的 task 上重複停止會直接返回。Qt 與 backend 的關聯紀錄只保存身份、終態、缺段及 Display 雜湊。

回歸通過 170 個 Python 測試、25 個 Node 測試，另加 2 個 Qt 簽章、lineage、錯誤 pin 與資產完整性測試。前輪的 24/24、19/19、16/16 實體 Pet 長篇仍保留在原 validation.json。此輪五案皆使用正式 Qt。這五案沒有呼叫 Domain tool，也沒有在正式服務上強制造成某一段 TTS 故障，因此正式 Qt 顯示 partial 的故障注入及真實工具失敗口述仍未驗證。真人音質、外部喇叭輸出亦未驗證。

## 變更與回滾

[formal-task.patch](formal-task.patch) 包含 launcher_qt.py、kuro_launcher/qt_web_adapter.py、websocket_handler.py、single_conversation.py、tests/test_g3_conversation.py 五檔的增量。[formal-changed-files.json](formal-changed-files.json) 保存基於 dirty 工作檔的前後 SHA-256，已在隔離目錄逐 byte 驗證正向及逆向套用。前輪的 [task.patch](task.patch) 與 [changed-files.json](changed-files.json) 仍分開保留。Tool Discovery Job fe1482ef-535a-4ae9-ad7d-ad88acd5d6c4 結案時查得 completed，本輪未更動它的 owner bundle、source pin 或 tool 流程。

回滾本輪時，先比對五檔後像，再執行以下唯讀檢查。工作檔仍相符時移除 --check 以回退本輪增量，再使用原 Launcher 的「重新啟動 Kuro」。若之後已有其他修改，只移除本輪的相應 hunk。要連前輪語音實作一起回退，接著依原 Progress 的說明檢查前輪 patch 並重建、重載 Pet。保留目前簽署的 Qt 發行與其他工具改動。

~~~powershell
git -c core.autocrlf=false apply --reverse --check docs/agent-runs/kuro-speech-reliability-vnext-20261123/formal-task.patch
~~~
