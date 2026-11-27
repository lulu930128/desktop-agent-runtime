# Kuro 多語理解與單輪雙 lane 語音 — 執行進度

2026-10-31，本次 Codex 同一任務完成 G0–G4 source 實作與定點驗證。**Source Ready／Targeted PASS；正式 Runtime、Desktop E2E 與發聲品質 UNVERIFIED。** 未啟動正式 Kuro、未呼叫 cloud LLM／中央 TTS 推論、未操作中央模型／正式資料、未 commit／push。

凍結 `Plan.md` 完全未改：SHA-256 `b1f2441d1791417275e71f126ed2f3040350fc118ea5cb59a17284b4477b04ef`。

## 已完成（Completed／Changed）

| Gate | 完成內容 |
| --- | --- |
| G0 | 以現有 `main` dirty worktree 建立 source 基線及 SHA-256；本次相對基線 diff 另存 `.tmp/kuro-multilingual-speech-20261031/TaskDiff.patch`，不把其他 WIP 當成本次修改。 |
| G1 | 主 LLM 在同一 conversation API sequence 生成完整 display 與 `kuro.speech-lanes.v1` 私有 speech footer；工具 loop 仍按需 continuation，只有工具結束後的最終有效 footer 可發聲。串流分流先於顯示與語音處理，History、agent memory、角色記憶只收到 display。正常路徑不呼叫 Bridge／`render_spoken`／第二輪 OpenAI。 |
| G2 | 使用既有 `SpeechPolicyEngine`、pronunciation、emotion 與 `TTSTaskManager`；非 AI 驗證拒絕 code／URL／path／JSON／table／log／trace 等技術口播，不做可能改變否定或條件的片段裁切。價格、停損、stale／unknown／未驗證 fixture 保留原數字與否定。朗讀策略由同輪 LLM 按語意產生，沒有事後 AI 摘要／翻譯。文字與 ASR 原始轉錄直接進主 LLM，沒有輸入語言選單或必經語言分類 API。 |
| G3 | 正式 Qt「設定 → 語音與感知」加入一般聊天「朗讀策略：極簡／摘要／詳細」及「朗讀語言」。單一持久化 owner 為既有 Launcher YAML 的版本化 `chat_speech` 區段，具版本檢查、atomic write、readback；runtime 每回合開始讀取一次。Core `proactiveVoice` 與 OMI 設定維持獨立。 |
| G3 source 採用 | 以未改動的既有 builder 建立新 immutable signed owner bundle，`qt_web_release.py` 僅更新四個 pin 欄位。下次正常 Launcher 啟動可載入新控制項；本輪沒有重啟或 live deployment。 |
| G4 | 最後 Python fixtures、Qt Port／Chat delta、Node、語音回歸、syntax、typecheck／build、signed bundle／source lineage、WIP hash 與 diff check 均 PASS。精確結果見下表及 `Evidence.json`。 |

主要變更檔案：

- Conversation：`basic_memory_agent.py`、`agent/output_types.py`、`conversation_utils.py`、`single_conversation.py`、`speech_presentation.py`、`tts_manager.py`。
- Prompt：既有 `response_contract_prompt.txt` 與新增 `speech_lanes_prompt.txt`。
- Launcher／Qt：`config.py`、`services.py`、`qt_controller.py`、`qt_web_protocol.py`、`qt_web_adapter.py`、`qt_chat_client.py`、`qt_web_release.py`。
- 正式 Web adapter：`devtools/original-git-web-host-20261010/frontend/src/owner-presentation.ts`。原 `work-panel/main.ts` 保持 immutable。
- Pet：`pet-electron/renderer/src/backend/backend-client.ts` 僅增加 `playing` 時間埋點，不改播放、嘴型或 ack ownership。
- 新增測試：`tests/test_multilingual_speech.py`、`test_chat_speech_settings_qt.py`、`multilingual_speech_frontend.test.cjs`、`multilingual_speech_surface.py`。

## 已驗證（Verified）

| 範圍／命令 | 最後結果 |
| --- | --- |
| `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p test_multilingual_speech.py -v` | **28/28 PASS**。涵蓋四種文字語系與 ASR 原文、多種 chunk 切點、literal marker、malformed／missing／oversize、三策略、工具結果後才發聲、錯誤／取消、無語音、設定下一輪、日文讀音、舊路徑回退。 |
| `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p test_chat_speech_settings_qt.py -v` | **4/4 PASS**。實際 Qt owner Port → Controller → 暫存 Launcher YAML → readback／新 Controller 重讀；錯誤寫入不自動重送；版本化 Chat delta 保留空白、換行及重複文字。無正式 GUI／服務啟動。 |
| `node --test tests/multilingual_speech_frontend.test.cjs tests/qt_web_frontend.test.cjs` | **26/26 PASS**，包含既有 owner transport、正式 source pin 與 bundle lineage 回歸。 |
| `envs/kuro-llm310/python.exe -B -m unittest discover -s Open-LLM-VTuber/tests -p test_tts_pronunciation_pipeline.py -v` | **47/47 PASS**，使用既有 `Open-LLM-VTuber/src`／`Open-LLM-VTuber` PYTHONPATH；沒有真實 TTS。 |
| `QT_QPA_PLATFORM=offscreen`，`envs/kuro-llm310/python.exe -B tests/multilingual_speech_surface.py` | **11/11 隔離 DOM 檢查 PASS**。使用正式 source pin／簽章驗證後的 bundle，真正點擊設定、儲存、重讀、換頁及 polling；Core offline 不阻擋一般聊天朗讀設定。只寫 fixture YAML。 |
| 長 token fixture | **13,500 個單字元 display chunks → 85 個 display WS payload**，完整文字一致、持續分批顯示、正常路徑 Bridge 請求 **0**。以 160 字元／80ms／句界或事件前 flush coalesce，無逐 token silent WS 洪流。這是事件數證據，不是正式延遲量測。 |
| 正式 `start_llm` 子程序 import probe | 攔截正式 spawn，使用其實際 Python、`cwd=Open-LLM-VTuber` 與產生的 PYTHONPATH 執行獨立 `python -B -c`；成功 import repo 的 `kuro_launcher.config`。沒有執行 `run_server.py`。 |
| `npm run check`（正式前端目錄） | PASS。 |
| `npm run check:renderer`／`npm run build:renderer`（Pet 目錄） | PASS。build 保留上游 non-module Cubism script 警告；沒有啟動 Electron。 |
| 既有 `build_owner_bundle.py --output …/.runtime/kuro-multilingual-speech-20261031-build.json` | `STAGING_VERIFIED`；新舊 bundle 均通過 `VerifiedOwnerBundle.load()`；新 bundle 與當前 source／toolchain lineage 一致，編譯 JS 確認包含兩個控制項及其真實讀寫方法。 |
| Source 靜態驗證 | **16 份 Python syntax PASS**；正常語音 queue AST 不含 translate／chat_completion／Bridge IO；52 份基線檔中 **16 份為本次 allowlist 修改、36 份 byte-exact 不變**。`qt_app.py` 與 builder 的既有 WIP 完全不變。HEAD 不變、staged diff 為空。`git diff --check` PASS。 |

詳細收據：本目錄 `Evidence.json`；原始本機 source 基線、最後測試 logs、`FinalChecks.json`、`SourceValidation.json`、`TaskDiff.patch` 及隔離 DOM `surface/Result.json` 位於 `.tmp/kuro-multilingual-speech-20261031/`。既有 untracked WIP 未編輯；不將這些私人工作區快照納入 Git。

本輪依 Reviewer 定點回饋完成：literal marker 語境保護、WS batching、正式子程序 import，以及 signed Qt bundle／source pin 接線。另修正雙 lane display 被舊 `strip()`／Qt cumulative-caption 去重邏輯破壞的風險，使用版本化 ordered display delta 保留內容；legacy caption 行為不變。最後 diff 由實作者相對基線檢查；未宣稱取得獨立 Reviewer 的完整 final sign-off。

## 新 bundle 與邊界

- Fingerprint：`1ae1327c3f02836510f5712e7783c03a6b3a883e9f0d8d15d165247a14ae9a9a`。
- Manifest SHA-256：`d4837396ea4e6c79bd19c31573098978824ef04e1eb5b23ed6fdcfac17f92396`。
- 舊 source pin `1cf2b5951a7a27ee508b185bcfa3d08e353b8e4cae86d76e9b7e6ad3de576ea0` 及舊 assets 保留並驗簽；不覆寫舊 immutable bundle。
- 沒有修改中央 GPT-SoVITS、Bridge service 原始碼、Core assistant settings、Memory Core、OMI／Mail／工具 policy 或正式 Launcher YAML。
- 埋點包含 LLM 完成、speech ready／路由／Bridge request count、TTS request／complete、WS audio send 與 Electron `playing`。最後一項仍待 G5 真實播放；跨程序時間須以 log wall time／`at_ms` 對齊，不能直接相減不同程序的 monotonic clock。

## 已知限制與未驗證（Unverified）

- **G5 Pending，正式 Runtime／Desktop E2E UNVERIFIED**。沒有正式主 LLM、真人對話、實際 ASR 聲學辨識、中央模型自然發聲、嘴型／音訊 ack 或冷熱載入延遲驗收；不宣稱更快。
- 日文為現有中央角色模型預設。`zh-Hant`／`en-US` 可真實持久化並影響下一輪口播稿語言，UI 明示「語音未驗證」；目前這兩種 locale **不送中央合成**，不偷偷改唸日文。
- footer 缺少、結構錯誤、語系不符、危險技術 payload 或 stream 失敗時，保留 display、略過語音；沒有自動多輪 repair。非 AI hard filter 選擇整段拒絕，避免局部刪除造成條件／否定反轉。
- Markdown fenced／inline code 內的 literal marker 與被反斜線 escape 的 prose 保留。**未 escape、位於 literal 外的獨立 `<<<KURO_SPEECH_V1>>>` 行是協定保留字**，無法同時當一般文字與 footer；prompt 已要求技術示例以 fenced／inline code 或 escape 呈現，fixture 覆蓋此限制。未閉合 code fence 時保持 display，speech 可靜默降級。
- 主 LLM 的跨語語意一致性靠同輪輸出 contract 與工具證據約束；fixtures 證明 wiring，不等同真實模型永不漏寫限制。G5 須聽取價格、否定、freshness 與不確定性的實際表達。
- 隔離 Qt offscreen 發生 D3D context-lost 警告；DOM／讀寫通過，沒有把它當視覺、實體螢幕或正式 Qt runtime acceptance。

## 切回舊語音路徑（Rollback）

保留舊 Bridge 路徑供明確 rollback；不因缺失 footer 自動進入付費備援。需要切換時，由操作者在 repo root 執行以下命令；**本輪未執行**：

```powershell
.\envs\kuro-llm310\python.exe -B -c "from pathlib import Path; from kuro_launcher.config import read_chat_speech_settings, update_chat_speech_settings; p=Path('kuro_launcher.settings.yaml'); s=read_chat_speech_settings(p); update_chat_speech_settings(p, {**s['settings'], 'locale':'ja-JP', 'route':'legacy_bridge'}, s['revision'])"
```

已載入本次 source 的 runtime 從下一 turn 讀取；不動 History／Memory／中央模型。舊路徑只使用日文與原有 spoken-short 策略，新策略偏好仍保存。每回合 Kuro 最多呼叫一次 `/render_spoken`，renderer 本身既有 repair／fallback 仍遵守 Bridge 原規則，不能將 rollback 當成正常零第二輪 API 路徑。fixture 已驗證實際舊 renderer 接線與單次請求 budget。

回到新版時，使用同一 helper 將 `route` 改為 `dual_lane`；無須覆寫整份設定。若要連 UI 一併退回，需成組回復本次 owner adapter／四個 source pin 欄位並驗證舊 bundle；不要使用 `git checkout --` 覆蓋基線 WIP。

## 使用者下一步（G5／Pending）

1. 使用者自行正常啟動新版 Kuro；確認「設定 → 語音與感知」可見兩個一般聊天朗讀控制，與主動通知分開。切換策略、儲存、換頁／重開後讀回；下一 turn 測試差異。
2. 以繁中、英文、日文、混合文字及麥克風各試一輪；確認 Qt Chat／History 文字完整，工具狀態與 Memory 正常，沒有私有 footer 或口播內容污染畫面。
3. 日文模式測簡單聊天、code＋trace、table＋URL、工具失敗，以及價格／停損／stale／unknown；確認關鍵限制與角色語氣保留，沒有逐字唸技術 payload，也不在工具結果前宣稱成功。
4. 測取消、TTS unavailable、播放完成 ack、Live2D emotion／嘴型；中文／英文選項目前應明示未驗證並保持無語音，不得偷偷換成日文。
5. 由上述埋點記錄首次冷載及後續熱載的「LLM 完成 → speech ready → TTS 完成 → 第一聲」；完成後才評估延遲及正式 adoption。需要時按上節切回舊語音，無須改中央 owner 或清空資料。

## 2026-10-31 G5 實測觀察與首句冷載定點修復

本節附加於原進度；原 Plan／前輪 Evidence.json 保持不變。狀態：**Source Ready、Targeted PASS；Installed／Runtime adoption Pending；首句加速與完整 Desktop E2E UNVERIFIED**。

### G5 已有實測證據

使用者已在正式 Kuro 對話；本輪唯讀核對 `launcher_logs/llm/2026_10/31/2026-10-31_12-39-37_kuro_01/llm.combined.log` 的既有紀錄：

| 回合 | LLM／tool | TTS | Bridge 次數 | 已見證據 |
| --- | --- | --- | --- | --- |
| 第一輪 | 12:41:01 → 12:41:26，約 25.45s | 12:41:26 → 12:42:30，64.359s | 0 | WAV 1,464,364 bytes，TTS complete，WS audio sent |
| 第二輪 | 12:43:06 → 12:43:26，約 20.45s | 12:43:26 → 12:43:40，13.406s | 0 | WAV 1,849,644 bytes，TTS complete，WS audio sent |

成功路徑沒有舊第二輪翻譯，不能把這兩輪延遲歸因於 Bridge。兩次稿長不同，不能將 64.359−13.406 當成純模型載入耗時。原 Engine 在 voice 改變時才建立 GPT-SoVITS pipeline，首次 cold load 與生成原本同在 `/tts`。本輪沒有重新呼叫真 LLM／GPU，也沒有取得新版首聲量測；WS sent 不能代替 Electron playing 或真人聽到第一聲。

### 修復範圍與 Reviewer 定點修正

- 中央 `Engine.load_voice()` 抽出既有真正 pipeline 建立流程；`synthesize()` 與 `/preload` 共用，沒有第二份模型、假合成或新 service。來源 TTS constructor 會執行 `_init_models()`；測試以替身 constructor 確認只建立模型、從不呼叫 `run`。
- POST `/preload` 只收 voice，HTTP 202 表示受理。同 voice 進行中共用 request_id；已 loaded 回 200 no-op。單一模型鎖涵蓋預載／切換／推論；同 voice 首句有一個保留等待位置，最多等 150 秒，失敗／逾時回明確 503，不自動重送。額外並發及其他 voice 忙碌維持 429。舊 `/health`、`/tts`、`/voices` 與 protocol 1 保留。
- 中央 `/health` 新增 `service_version=1.1.0-preload.1`、import 時固定的 `source_sha256`、`capabilities=["model_preload_v1"]` 與 preload state／耗時／錯誤；中央 log 記錄 start／complete。HTTP accepted 與 source 檔案版本都不能冒充 loaded runtime。
- Kuro 每次 fresh Profile start／成功 hot switch 各最多非阻塞請求一次，readiness／UI polling 不發預載。TTS client 碰到同 voice loading 會送出唯一一次首句 POST 交由中央等待；不因 busy discovery 直接遺失。預載錯誤不阻擋文字啟動，舊服務沒有 capability 時不假稱 warming、不重試。
- Reviewer readiness 修正：`model_loaded==voice`、`last_inference=not_run` 且沒有 failure 時仍沿用 `available`，reason 明示「目前角色模型預載已完成，首次合成尚未驗證」；`lastInference` 保持 not_run，不宣稱推論／音色聽感通過。原 cold／busy／failure／passed 判斷保留。
- 日誌回呼沿用正式 `_append_log_threadsafe → log_signal.emit → Qt owner slot`；隔離 QObject 測試確認背景 thread 返回後由 owner thread 收到。沒有修改 Qt app、控制項或前端版面。
- 長日文已驗證 lane 在自然句邊界最多分三組；六句以上或至少 240 字且有三句時，第一句先合成，其餘分成兩組。引號／括號、價格小數與完整文字保留；不硬切單一句、不增加 LLM。純數字首句留在整段，避免既有 list-marker silent filter 吞掉價格。完整 Chat／History 不放入 speech transcript、不重複保存。
- 既有 TTS manager 的 async lock 串行生成，原 ordered WS／Electron audio queue 與完成 ack 保留。每個實際發聲事件記錄 seq、queue_s、request／complete／duration_s；首段可在後續生成未完成時送出。
- Reviewer fail-stop 修正：僅同一次 dual-lane 分段群組任一段不可用／例外後，剩餘段落不再合成、不發聲，以有序 silent payload 完成序號與 final ack，避免只唸後半段。legacy 單段不套用群組失敗。取消會清除待排段落，已在執行而無法強停的 HTTP／thread 工作返回後丟棄音訊並清除 cache，不送入下一 turn。

### 基線、實際檔案與驗證

- Kuro：branch `main`，HEAD `c2b3e64c27caaec8c2cba5b213444ddce0d79e03`。修改前保存 HEAD／branch／完整 status／index bytes／既有 diff 及 raw file hashes，收據於 `.tmp/kuro-first-speech-20261031/Baseline.json`。中央目錄實際 `git rev-parse` 回「not a git repository」，所以 **Git baseline=N/A**，沒有宣稱 clean；四份中央來源／測試／README raw 基線已保存。
- 中央本輪修改：`scripts/voice_service.py`、`tests/test_voice_service.py`、`README.md`。`scripts/voice_supervisor.py` byte-exact 保留，沒有加 reload／process 操作。
- Kuro 本輪修改：`kuro_launcher/voice_client.py`、`kuro_launcher/qt_controller.py`、`Open-LLM-VTuber/src/open_llm_vtuber/conversations/conversation_utils.py`、`tts_manager.py`、`../tts/gpt_sovits_tts.py`；既有 `tests/test_central_voice.py`、`test_central_voice_client.py`、`test_multilingual_speech.py`，新增 `tests/test_first_speech_latency.py`；`docs/central-voice-runtime.md` 與本 Progress。
- 基線比對另發現 `Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_executor.py` 在本輪期間被外部流程修改；本 agent 沒有寫入／回退／修復該檔，也沒有納入本輪 patch。其他現有 WIP 保留；完整核對見 `FinalChecks.json`。不擴大到 MCP routing／invalid_arguments。

以 `envs/kuro-llm310/python.exe -B -m unittest discover -s <suite> -p <pattern> -v` 執行下列最終驗證（Open-LLM-VTuber/src、Open-LLM-VTuber、repo root 為明確 PYTHONPATH）：

| suite／pattern | 結果 |
| --- | --- |
| 中央 `tests / test_voice_service.py` | **14/14 PASS**；FakeEngine、真 pipeline 建立入口替身、isolated loopback HTTP、單載入／no-op／錯誤／有界併發／首句等待與 WAV 不遺失／舊 API。 |
| Kuro `tests / test_first_speech_latency.py` | **10/10 PASS**；fresh／hot 一次 hook、非阻塞／無重試、舊服務、Qt owner log、七句首段先送／順序／單推論／取消清理／fail-stop／legacy 獨立性／ack。 |
| Kuro `tests / test_central_voice_client.py` | **14/14 PASS**。 |
| Kuro `tests / test_central_voice.py` | **10/10 PASS**；含 preload ready／not_run 語意。 |
| Kuro `tests / test_multilingual_speech.py` | **30/30 PASS**；含完整工具 continuation、三段 speech、單份 AI History、首段不可用仍完整 display／History／final ack。 |
| Kuro `Open-LLM-VTuber/tests / test_tts_pronunciation_pipeline.py` | **47/47 PASS**。 |
| Kuro `tests / test_chat_speech_settings_qt.py` | **4/4 PASS**。 |

合計 **129/129 PASS**；11 份本輪 Python source／tests syntax compile PASS。Kuro scoped `git diff --check` PASS；中央 no-index 檢查曾因 LF／CRLF warning 與 exit 1 語意反覆失敗，標為「檢查器／換行警告，未確認格式缺陷」；最後改用 Python 標準庫 difflib＋嚴格 UTF-8／新增行尾空白定點檢查一次，PASS，沒有修改全域 Git 換行設定。原 Plan hash 保持 `b1f2441d1791417275e71f126ed2f3040350fc118ea5cb59a17284b4477b04ef`。精確命令／logs／source hashes 見 `.tmp/kuro-first-speech-20261031/RunValidation.py`、`Validation.json`、`Syntax.json`、`FinalChecks.json` 與 baseline 相對 `TaskDiff.patch`。沒有 UI build、真 GPU／付費 LLM、service lifecycle 操作、commit 或 push。

### Source／Installed／Runtime 與現在能否驗收

2026-10-31 **13:02:21 +08:00** 唯讀 GET：中央仍為原 PID **34284**、available、model_loaded=kuro，**沒有** service_version／source_sha256／capabilities／preload 欄位；Kuro `/launcher/status` 為 kuro／session／idle。此為仍在執行的舊程式，不是新版 adoption 證據。

新 source 已寫入原有執行入口目錄，沒有產生／選擇新的 installed release，沒有 reload 中央 supervisor／service，也沒有重啟 Kuro。既有 Qt immutable bundle／source pin 不變。**現在可以審查 source 與 fixture；不能驗收新版首句已加速。** 真實首句速度、模型預載移出首句的程度、Electron 第一聲、取消與嘴型／聽感均待正式換版後驗證。

### 最小 rollout／rollback（本輪未執行）

1. 等目前 Kuro 與其他中央 consumer 無進行中語音，另行授權中央 lifecycle owner 正式維護換版。沿用 `voice_supervisor.py`／`SERVICE-LIFECYCLE.md` 的 owner 與 exact PID 核對；現有 supervisor 沒有 reload API，`start-service.ps1 -Background` 只會沿用現有 listener，不能當成換版。不可新增第二個 service、清空 port 或按 Python 影像名稱強殺。
2. 換版後查 `/health` 的新 PID、`service_version=1.1.0-preload.1` 與 `source_sha256`（和本輪 FinalChecks 的中央 source hash 一致）；接著正常重啟 Kuro 的 Launcher／conversation runtime，讓它們真正 import 新 source。只在舊 runtime hot switch 不會載入新的 Python 模組。
3. 新 Profile 啟動後、真正第一句之前，確認中央 `preload.state=ready`／`model_loaded=目標 voice` 與中央 start／complete log。首次 inference 前 last_inference 應仍 not_run；readiness 說明「首次合成尚未驗證」。另測角色切換與已 loaded no-op，確認沒有 polling 重複 POST。
4. 以同一模型／xhigh／Standard 正常對話，對齊 LLM complete → 首段 tts_request／tts_complete → WS audio sent → Electron playing 的 wall time；跨程序不要直接相減 monotonic。另測六句以上日文、首段錯誤／取消、最終 ack、完整 Chat／History。記錄 startup preload 耗時與首句耗時，不能把載入拖到首句再宣稱改善。LLM/tool 原本約 20–25 秒不在本輪修復範圍。
5. 若需 rollback，以本輪 raw 基線或 `TaskDiff.patch` 只逆轉本輪允許檔案／hunks，先核對沒有後續新 WIP；不使用 git checkout／reset，也不動外部 tool_executor 修改、模型包、History、設定或 Qt bundle。中央三檔與 Kuro 本輪 source／tests／docs 成組回退，再由正式 owner 維護換版／正常啟動；原雙 lane 保留，不切回額外付費 Bridge。
