# G8 final acceptance checkpoint

> **最新複查（2026-10-10）：G7 實體清理已達 35/35 PASS；G8 完整回歸仍需補驗，產品 Release NOT ACCEPTED。** 本輪 Node 架構 20/20、MCP 18/18、Python syntax 204 檔、JavaScript syntax 15 檔、Renderer typecheck、diff check 通過；完整 Python runner 因無權建立 repo-local disposable TEMP 卡在測試前置，完整 Node runner／Renderer build 未重跑。此前 Electron hidden fixture FAIL（renderer 49／GPU 0xC0000135）以及正式 Windows 桌面仍未驗證。請見 [G7 最終 Reviewer 驗收](G7PostDeleteAcceptance-20261010.md)。以下的 BLOCKED 33/35 為歷史紀錄，不再代表 G7 現況。

> **本輪靜態重驗（2026-10-10）**：manifest／備份／consumer 靜態核對通過，但 G7 兩個實體檔仍遭 `UnauthorizedAccessException (0x80070005)` 阻擋，故 **STATIC BLOCKED／NOT ACCEPTED**。本輪沒有程式變更，不將前輪 Python 326／Node 83／MCP 14+4／renderer PASS 冒充本輪重跑。Electron hidden fixture 保留前輪 renderer 49／GPU 0xC0000135 **FAIL**；正式 Windows／Live2D **UNVERIFIED**。見 [本輪結果](../../../G7FinalTwoResults-20261010.json) 與 [安全補刪及驗收接力](../../../G7FinalTwoHandoff-20261010.md)。

> **後續更新（2026-10-09）**：本輪重新執行 Python 326 項／25 suites、Node 83 項、renderer typecheck/build 全部通過；G7 實體刪除從 25/35 改進至 **33/35**，仍有兩檔 Access Denied。最小 Electron 空白頁也重現 renderer 49／GPU 0xC0000135，OS/runtime 根因未定。正式實機仍 UNVERIFIED，結論維持 **STATIC BLOCKED／NOT ACCEPTED**。見 [Reviewer 增量複查](G8ReviewerStaticFollowup.md) 與 [G7 最新結果](G7FollowupDeletionResults.json)。以下保留前輪 checkpoint 原始內容。

日期：2026-10-09。**已完成本輪可安全執行的 G8 source／architecture／isolated runtime 驗證；release verdict：NOT ACCEPTED。**

G6 source-ready；G7 35 個預列刪除檔中 25 已刪、10 被 Windows 拒絕，physical deletion **BLOCKED**。隔離 Electron renderer smoke **FAIL**。正式 Windows 桌面、tray／OS notification、硬體與模型／語音驗收 **UNVERIFIED**。不能宣告「Qt Final Convergence 完成／可封版」，也不能移除 migration evidence。

## Gate chain 與實際修正

| Gate | Source／isolated 結果 | 正式接受狀態 |
| --- | --- | --- |
| [G5](G5Checkpoint.md) | canonical Qt startup/event/tray/delivery 查核；17 Qt desktop＋6 entrypoint tests；Windows UUID mutex/event signal/consume PASS | canonical cold boot／second launch／tray／restart 未驗收 |
| [G6](G6Checkpoint.md) | Electron Pet-only、pet-local status／presentation、Qt conversation/input ownership 已實作與回歸 | Live2D／input／audio 實機未驗收 |
| [G7](G7Checkpoint.md) | external production consumer=0；config／IPC／routes／dead Qt code 清除；25 physical deletions | 10 OS access denied；repository legacy implementation count 尚非 0 |
| G8 | source regression／renderer checks／API-WS-Qt transports PASS | hidden Electron FAIL、正式 desktop UNVERIFIED；NOT ACCEPTED |

### Confirmed defects（已修復）

- Pet 每 5 秒向已退役 :23568 要求 runtime/presentation，導致 stale/failed diagnostics：改為本地 renderer inspector＋Launcher explicit descriptor push；missing/loading/failed/offscreen/ready 分離。
- 舊 Pet input 路徑仍可能觸發對話：Pet 僅 capture，Qt primary WS 持有送出；history 切換後丟棄舊 capture；mic 上限 60 秒，uncertain send 不重播。
- Core/Mail lifecycle 原本附著 Pet spawn：沿用既有 Launcher owner 移至 desktop/profile service startup；Qt text chat 不需要 Pet。
- inherited Core／Launcher token／Mail handoff env 泄漏到 Pet 的舊支線移除。
- Mail producer 仍 POST /briefing/snapshot、daily_brief 有 legacy GET/live fallback：移除舊 HTTP consumer；既有 poller/producer 改名 mail_poller.py／mail.refresh，tool identity/catalog/policy 同步，不留 alias。bounded handoff 移除 UI sections／假空 tasks，原 Mail classification/rules/preferences、Core Today/Study policy 保留。
- Qt Pet command/backend config 缺少明確成功 ACK 時也可能顯示成功：現在只接受 ok=true。
- Pet ai_state 不再覆寫 Qt canonical conversation state；本地停止播放與 Qt conversation interrupt 分離。

### Architecture risk／legacy debt／unverified

- **legacy debt／BLOCKED**：10 個 legacy source 尚在；它們彼此有 references，但已無 cluster 外 production consumer。任何 env 值均不得恢復舊 application UI。
- **confirmed runtime failure**：hidden Electron renderer launch-failed，完整 OS/dependency 原因 **UNVERIFIED**；不推定為正式機器不可用或宣稱 Live2D 可用。
- **UNVERIFIED**：正式 Core/Conversation/Pet adoption、Windows tray/notification、private history/memory、model/audio/devices、DPI、多螢幕、logon。Synthetic evidence 不涵蓋它們。
- Mail/Study 現有設定保持 disabled。已測 disabled／missing／stale／bounded synthetic actionable evidence；未私自啟用 provider 或捏造正式 Today items。

## 檔案與 ownership

G6 source 檔見 [G6Checkpoint](G6Checkpoint.md)；G7 每個刪除候選、hash、外部 consumer 與結果見 [manifest](G7DeletionManifest.json)／[deletion results](G7DeletionResults.json)。本輪與起點完整 path sets、source hashes 見 [G8Integrity](G8Integrity.json)。

| 本輪主要區域 | 實際變更 |
| --- | --- |
| pet-electron/src/main.js、main-process/control-server.js、menus.js、pet-status.js、preload.js、state.js | 單一 Pet window／allowlist；local status／descriptor；無 launcher/business IPC／routes／tray；清除舊 state schema |
| pet-electron/renderer/src/backend/*、commands/pet-command-router.ts、main.ts、env.d.ts；vite.renderer.config.ts | pet-presentation；Qt capture bridge；無 conversation send/history/browser；僅 index.html build entry |
| kuro_launcher/qt_controller.py、qt_app.py、qt_chat_client.py、config.py、mail_poller_runtime.py；launcher_qt.py；kuro_launcher.settings.yaml | 唯一 Qt UI與既有 lifecycle；Qt capture WS；移除 legacy methods／flags／token/config；single Launcher poller |
| kuro_core/shadow_probe.py | 移除 legacy Briefing HTTP adapter，保留 bounded explicit Study probe |
| Open-LLM-VTuber/local_mcp/mail_tools_server.py、mail_poller.py | bounded producer/handoff，移除 legacy UI projection與 HTTP fallback；沒有新增 service |
| Open-LLM-VTuber/src/open_llm_vtuber/mcpp/tool_identity.py、tool_catalog_manager.py；tool_catalog.json、tool_policy.json | producer tool identity/catalog/policy 名稱同步；限制不放寬 |
| tests/test_g8_runtime.py、g8_hidden_electron_smoke.cjs、run_qt_convergence.py | 真 loopback/temporary DB/Qt/WS smoke、hidden Electron fixture、bounded repeatable runner |
| G3/G4/G5/G6／Mail／Pet／Schedule／Core tests | 清除 legacy-only expectations，保留有效 canonical 行為與新增 capture/ACK/handoff assertions |
| README.md、AGENTS.md、docs/architecture/*、docs/guides/*、docs/index.md、本 checkpoint 目錄 | 當前事實與限制；保留日期性歷史 |

## 實際驗證與 exit

完整機器可讀結果：[G8ValidationResults.json](G8ValidationResults.json)。

| 命令／surface | 實際結果 |
| --- | --- |
| envs/kuro-llm310/python.exe -B tests/run_qt_convergence.py --group python | 第一輪完整 **323 tests，25 suites，各 exit 0** |
| 後續 affected targeted suites | Mail status 16、Mail work 8、G6 11、Pet lifecycle 9、runtime capabilities 8、G5 17、launcher entrypoint 6，全 exit 0 |
| 最終 root suite 集合 | **326 distinct tests 已驗證**：第一輪後新增 ACK 2＋Mail snapshot 1；不是聲稱單次完整 326 重跑 |
| Runtime MCP identity/policy/market routing targeted | 3＋5＋6 = **14 tests，exit 0** |
| envs/kuro-llm310/python.exe -B tests/run_qt_convergence.py --group node | **83 tests，exit 0** |
| npm.cmd --prefix pet-electron run check:renderer | exit 0 |
| npm.cmd --prefix pet-electron run build:renderer | exit 0；86 modules，唯一 index.html entry。既有 Cubism classic external script 警告保留 |
| Python in-memory compile／node --check | 最終檔案數、命令／exit 見 G8Integrity；不寫 pyc |
| git -c core.safecrlf=false diff --check、UTF-8／local Markdown links | 最終結果見 G8Integrity；未將歷史截圖當 runtime acceptance |
| tests/test_g8_runtime.py | **3 tests PASS**（包含在 323/326 中，不另加總） |
| tests/g8_hidden_electron_smoke.cjs | **FAIL**；process exit 2147483651，renderer launch-failed exit 49，GPU exit -1073741515 |

Python runner 使用 repo-root disposable TEMP/TMP、offscreen、synthetic providers，攔截非 loopback 與正式/shared ports；每 suite 90 秒限制。Core child 測試只使用 temporary DB/port。Node 只跑 *.test.cjs/mjs，不隱含執行 manual model/device smokes。Central Voice tests 是 mocks，不呼叫 :18890。

後續 targeted 等價可重跑命令為設定同一 disposable/offscreen/PYTHONPATH 後，以 unittest discover 的 -p 指定 G8ValidationResults 中 suite；完整可重跑指令已收斂於 [人工 checklist](G8ManualAcceptance.md)，不依賴刪除的臨時 helper scripts。

### 跨層 evidence 的邊界

1. Real Core API/SQLite（temporary）→ Qt controller/CoreRuntime → QtScheduleDelivery：claim→authorize→synthetic tray show→ack，第二 poll 不重複顯示。這不是 OS notification 可見性。
2. Real loopback WS → 真 QtRuntimeChatClient/WebSocketHandler：沒有 Pet 仍能 synthetic text turn；Pet role 的 text/mic/interrupt/history/config 被拒；wrong request_id ack 不完成，正確 ack 才完成。Provider/context 為 fixture，不呼叫 LLM、TTS 或讀 history。
3. UUID Windows kernel mutex/event：第二 process signal、primary consume once。這不是 canonical Qt visible/reveal/second launch。
4. Electron fixture 使用 fresh temporary userData、無 descriptor/model／media，show/focus 被攔截。修正 PowerShell GUI 子程序未等待的 harness 問題後，用 subprocess.run 等待仍 renderer/GPU FAIL。初次殘留的自有 child 經 executable/start time 核對後精確結束；沒有全機 kill 或操作共用服務。

## 完整性／邊界／rollback

起點 main、HEAD 995c23c7c8d1be62000229d58610d2214f3bb745、35 modified＋53 untracked 已完整保存於 [G5G8InitialPathSnapshot](G5G8InitialPathSnapshot.json)。最終 integrity 逐 path 區分 preserved／modified-in-scope／manifest-approved deletion，不能用最終 dirty 數量冒充「88 檔未改」。

Ignored source archive `g7-source-rollback.zip.bak` 保存全部 35 候選原始 bytes（含 WIP），另含 G7/docs 前 preimages；最終 CRC／SHA 與 manifest 比對見 G8Integrity。它不是完整 G6 前備份。回退需要局部 restore 配對 source/consumer，不能 reset/clean/checkout HEAD、回滾正式 DB或啟用雙 owner。

- 沒有 commit/push、修改其他 repo、正式 DB migration／reset、private userData/models 刪除。
- 沒有讀取/列印 private mail body、history、memory、OAuth/secret、model/voice 素材。
- 沒有 provider refresh、外部發送、中央 Voice API／啟停、OS startup／registry／ACL 修改。
- 只對 ports 做被動 metadata 觀察；最終 listener/PID 結果見 G8Integrity，不以 absent listener 當 acceptance。

## Pending blockers 與 release rule

1. **G7 BLOCKED**：依 [人工 checklist](G8ManualAcceptance.md) 的 manifest+hash+path-guard 命令，使用具原有權限的帳號補刪 10 檔；若 denied 仍停止，不改 ACL。重跑 inventory/architecture checks，更新 evidence。
2. **G8 FAIL**：處理 Electron renderer/GPU launch failure，重跑 hidden fixture；成功仍僅代表隔離 renderer smoke。
3. **G5/G8 UNVERIFIED**：按 checklist 完成 canonical visible startup、second launch、X/tray/reveal/Quit、auto_start=false、owned child restart/crash/reconnect、Qt Chat無Pet、notification實際可見、device/model/voice/DPI及既有logon觀察。不得未經授權存取私有內容或啟用 Gmail／Study／中央 Voice控制。
4. 只有 physical legacy source=0、source/runtime evidence完備且正式桌面項目被實測接受後，才可以改判 ACCEPTED。此輪判定維持 **NOT ACCEPTED**。
