# G0 — Foundation checkpoint freeze

日期：2026-10-09
狀態：**G0 source checkpoint ready；production runtime adoption 未驗收；G1 未開始。**

## 範圍與判定

以 main 的實際 M1a–M1f working tree 為準，base HEAD：995c23c7c8d1be62000229d58610d2214f3bb745。整批 foundation 保留未提交；ready 表示可供 reviewer 驗收的 source checkpoint，不表示 Git working tree clean、正式 runtime 已採用或 Qt migration 已完成。沒有 commit/push。

最終產品決策依 [QtFinalConvergencePlan](QtFinalConvergencePlan.md)：唯一主 UI = Qt；Electron 最終只留 Live2D-only shell。舊 capability 經 parity、runtime acceptance、authoritative cutover、consumer inventory 歸零後 physical delete，不留 silent fallback。歷史產品／M0 文件中的 Work Panel、Reader、Briefing 描述不取代已鎖定的終局決策。

## M1a–M1f source ownership

| 階段／能力 | Foundation owner／consumer | Persistence／read-write path | Adoption 狀態 |
| --- | --- | --- | --- |
| M1a Study projection | study_adapter.study_snapshot_observation；shadow probe 與 integration 共用 | payload → bounded aggregate Observation；不寫 DB、不保存 raw words/Today 內容 | Source validated，不是 Task/Today owner |
| M1b Study file boundary | study_snapshot_file_observation → handoff.read_json_handoff | configured file → bounded read → adapter；無 refresh/provider IO/writer | Source validated；UI reader 未切換 |
| M1c Study shadow/parity | shadow_probe.build_study_shadow_report／explicit CLI | 同一 adapter → whitelist status/metrics；不落 DB、不自動呼叫 legacy Briefing | Synthetic regression PASS；既有 live parity 為歷史證據，本次未讀正式 snapshot |
| M1d rejected experiment | 無現行 production consumer | Study route 塞進 ScheduleServer 的實驗已回退 | 歷史 rejected，不是 production fallback；M1e route 使用 general host |
| M1e Core host | kuro_core_service.py → CoreApplication → 單一 CoreApiServer；Launcher/Electron main consume | listener/auth/parsing/route registry/process identity；無 domain persistence | Source + isolated child validated；正式常駐 runtime adoption 未測 |
| M1e ScheduleCapability | ScheduleStore／ScheduleNotifications；Electron restricted Core client／配送 consumer | lease 內 shared schema v3 bootstrap；schedule routes → schedule tables；worker materialization/eligibility、claim/authorize/ack | Schedule 有歷史正式採用；本次 general-host migration 只做 isolated 驗證 |
| M1e IntegrationRegistry | integrations.py 組裝 enabled Study/Mail wrappers | GET 委派 adapter，不 import ScheduleStore、不寫 observations；status 只報 configuration | Source-ready；兩個 integration 預設 disabled；UI consumer 未 cutover |
| M1f Mail producer | mail_tools_server.mail_update_briefing 唯一接上 mail_status_handoff.write_status；既有 poller 呼叫同一 producer | provider attempt → bounded private mail_status.json；lock/attempt ordering + 同目錄 temp/atomic replace | Source-ready；無新增 provider client/poller/process/port；正式 handoff 未讀寫 |
| M1f Mail reader | MailIntegration → mail_adapter.build_mail_status → 共用 handoff.py | configured file → read-only /v1/integrations/mail；無 DB/OAuth/provider/refresh/Briefing store IO | Source + isolated child validated；UI/Today/Briefing 未 cutover |

storage.KuroCoreStore.initialize 仍是正式 Schedule shared schema bootstrap；Observation/Decision persistence 仍是 shadow。G0 無 DB migration、拆庫或新 persistence owner。

## Reverse-search 與 legacy primary

核對 production source/tests/config 的 constructors、imports、routes、writer call sites、child env 與 Electron consumer，未讀正式 payload。

| 搜尋面 | 結論／分類 |
| --- | --- |
| CoreApplication／CoreApiServer／HTTP server | Production Core composition 只有 service → core_app → api_server；其餘 construction 是 isolated tests。既有 work_panel_api 是 legacy Launcher proxy，不是平行 Core host |
| ScheduleServer | 現行 production source 無 class/import/construction/fallback；文件命中屬歷史背景 |
| mail_status_handoff／write_status | 唯一 production call site 在 explicit mail.update_briefing；既有 mail_briefing_poller 呼叫相同 producer。沒有新 poller 或額外 writer |
| Mail provider/poller | provider/OAuth/read-only fetch 留在 local_mcp/mail_tools_server；Electron mail-briefing-service 仍管理 poller、preferences/rules、manual refresh、message detail。daily_brief 既有 live fallback 未搬、未新增 |
| Study read/write | Core integration 與 shadow probe 共用 adapter；Electron study-briefing 仍是 Briefing/Today UI primary。既有 local_mcp/study_tools/vocab_tracker.py 的 import/sync/mark snapshot writer 是學習 domain producer，不是 G0 新增的平行 writer |
| Qt direct DB/provider | 無新增 SQLite/store/provider/handoff read path。Launcher config 持有並傳遞路徑，不代表 UI 直接讀資料 |
| Today/Briefing | briefing-store.js／today-classifier.js 仍是 legacy primary：snapshot composition/persistence、Study merge、Today projection。Core 尚無 Work/Attention/Today API |

新 read-only status path 與 legacy UI reader 並存，是明列的 migration boundary，不是雙 UI primary。不能因此刪 legacy reader/poller/store，也不能把 aggregate Observation 當 actionable Today item。**沒有未處理的 G0 parallel-path blocker。**

## Canonical settings／CLI／child environment

- settings → config.load_config → typed AppConfig → CoreRuntime → Core CLI → CoreApplication → IntegrationRegistry。
- Study：enabled=false；snapshot_path 為設定的 Open-LLM-VTuber/private/study/study_snapshot.json；TTL=3600；max=2097152 bytes，hard cap=16777216。
- Mail：enabled=false；status_path 為設定的 Open-LLM-VTuber/private/gmail/mail_status.json；TTL=1800；max/hard cap=65536 bytes。
- TTL 都限定 1–2592000 整數；TTL/max 不接受 bool、string、零或超界值。Enabled 需 explicit resolved absolute path；load_config 展開變數及相對路徑。Handoff 檔案不必存在；missing 是 GET availability=missing，不是 startup failure。
- Study CLI：--study-enabled、--study-snapshot、--study-ttl-seconds、--study-max-bytes。Mail CLI：--mail-enabled、--mail-status、--mail-ttl-seconds、--mail-max-bytes。
- Mail producer 的 Electron child env KURO_MAIL_STATUS_FILE 與 --mail-status 使用相同 resolved config path。Writer 另限制在既有 Gmail private root 下，錯誤回報固定 error type，不另找 fallback path。
- Disabled 不傳該 integration CLI、不註冊 route（404）。Core 或 Mail disabled 時 Electron child 不保留 inherited Mail status path；既有 Mail poller enable/preferences 行為未改。
- Process contract=kuro.core.api.v1；nested Schedule=kuro.core.schedule.v1/schema 3；Registry=kuro.core.integrations.v1；Study/Mail contract 各為 kuro.core.integration.study.v1／kuro.core.integration.mail.v1。Launcher/Electron gate 不接受舊 Schedule-only process identity。
- Handoff reader 與 writer atomic replace 對 Windows sharing/access/busy error 的 retry 各最多 0.5 秒；writer commit lock 另有 2 秒上限。不 unlink target、不 truncate overwrite；Core GET 不寫檔。
- Provider success 先寫 bounded handoff，再送 legacy dashboard；dashboard failure 不覆寫 provider success。Provider failure 保留 last-good counts/time，只存 auth_required/provider_error，無 raw mail/token。

## G0 確認與修正

1. **P1 inherited KURO_MAIL_STATUS_FILE leak**：_spawn_pet_electron_locked 原先只清除 KURO_CORE_URL/TOKEN/INSTANCE，parent env 可繞過 Core/Mail disabled。新 mocked-spawn test 在兩種 disabled case 重現失敗。Production fix 只把 KURO_MAIL_STATUS_FILE 加入原清除清單，再合併 core_runtime.child_environment；沒有 test-only 分支，enabled case 仍採 canonical config path。
2. **Timestamp overflow robustness**：Study updatedAt + TTL／timezone normalization、Mail timezone normalization 在 datetime 邊界可能拋 OverflowError。Adapter 將無效來源時間轉為受控 partial/unknown freshness（Study）或 partial limitation（Mail）；各新增一個 synthetic regression。沒有改正常來源語意、分類、優先順序或 legacy UI 行為。
3. **Stale comment／scaffolding**：Study docstring 改為 shadow probe 與 read-only integration 共用；移除 shadow probe 重複 URL guard。M0/M1d 紀錄保留歷史時間範圍，不當現行 production。

G0 source 增量限 kuro_launcher/qt_controller.py、kuro_core/study_adapter.py、mail_adapter.py、shadow_probe.py，及 test_schedule_runtime.py、test_kuro_core_study_adapter.py、test_kuro_core_mail_adapter.py。其餘既有 M1a–M1f dirty changes 保留。未改 Qt UI、Work Panel、Today classifier、Briefing store 或產品規則。

## Isolated regression

Repo interpreter：envs/kuro-llm310/python.exe（3.10.12）；Node v24.14.1。Python 皆使用 -B、PYTHONDONTWRITEBYTECODE=1，TEMP/TMP 指向唯一 disposable repo-local directory，finally 清除並還原 process env。Core child 使用 ephemeral port、synthetic handoff、disposable DB/log；Mail provider/dashboard mocked；Electron spawn mocked。

| Pattern／命令 | 結果 |
| --- | --- |
| test_mail_status_handoff.py | 16/16 PASS |
| test_kuro_core_mail_adapter.py | 13/13 PASS |
| test_kuro_core_study_adapter.py | 16/16 PASS |
| test_kuro_core*.py | 68/68 PASS |
| test_schedule*.py | 44/44 PASS |
| node --test tests/core_client.test.cjs | 4/4 PASS |
| inherited-env targeted test，fix 後 | 1/1 PASS，含兩種 disabled 與 enabled canonical path |
| test_kuro_core*.py -v，使用者要求額外確認 | 68/68 PASS；無 FAIL/ERROR traceback |
| git diff --check | PASS；僅既有 LF/CRLF warning |

Python 命令形式：envs\kuro-llm310\python.exe -B -m unittest discover -s tests -p '<pattern>'。Targeted adapter/inherited-env 已包含於對應 regression，不重複計數；獨立測試為 128 Python + 4 Node。

Integrity 比較三份 path set，沒有 Get-Item metadata：

- git status --porcelain=v1 -uall
- git ls-files --cached --others
- git -c core.quotepath=false ls-files --others --ignored --exclude-standard -- '*.pyc' '*.pyo' '*.tmp'

最終完整 regression 與 Core verbose 均為 statusIdentical=true、allFileSetIncludingIgnoredIdentical=true、ignoredArtifactPathSetIdentical=true、tempRemoved=true。文件更新在測試後進行，是預期 diff，不混入 test integrity。

第一次 metadata wrapper 在 tests 前因 Git quoted path／PowerShell Get-Item 失敗；後續被中斷 run 不作 acceptance evidence，其唯一 synthetic temp 已精確清除。改用純 path set 的完整 run 通過。Wrapper 問題不是 repo test failure，未為此改產品 source 或 ACL。

未讀真 Gmail/OAuth token、正式 handoff、briefing-store、history/memory raw data 或正式 Core DB；未啟動正式 Kuro stack，未 stop/restart Central Voice，未改 ACL。

**本次沒有 production runtime adoption、真實 provider 或桌面/UI acceptance evidence。**

## 下一 Gate blocking prerequisites

- G0 供 reviewer 驗收；G1 未開始，本紀錄不授權自動續跑。
- G1 先定 versioned TaskCandidate/WorkItem/Attention/TodayView/SourceEvidence contract，含 identity/time、timezone、dedup、排序理由、privacy 與 missing/partial/stale；aggregate status 不足以交付 actionable Mail/Study items。
- G1 維持 synthetic、backend-only、無 production writer cutover；不複製 Electron classifier、不新增 Gmail fetch、不讓 Qt 承擔 domain logic。
- G2 前另需 runtime adoption、consumer parity、Mail provider/poller/preferences/rules/detail/manual-refresh owner 決策、Study reader 單次 cutover 證據；本次均未完成。
- Legacy 必須經 new consumer → runtime acceptance → authoritative cutover → consumer inventory=0 → physical delete。Qt conversation、activation/tray/notification 與 Live2D-only shell 屬後續 Gates，G0 不施工。
