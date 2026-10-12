"""Read Git objects and rebuild the source-backed parity inventory. No runtime IO."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = "pet-electron/renderer/src/work-panel/"
BASE = "3baf05728921607d71306c98d43eaad155b0dbc1"
inventory = json.loads((HERE / "GitSourceInventory.json").read_text(encoding="utf-8"))
sources = {}
for revision in ("HEAD", BASE):
    for name in ("main.ts", "types.ts", "model.ts", "schedule.ts", "styles.css"):
        result = subprocess.run(["git", "show", f"{revision}:{PREFIX}{name}"], cwd=ROOT, capture_output=True)
        if result.returncode:
            assert revision == BASE and name == "schedule.ts", result.stderr
            continue
        source = result.stdout.decode("utf-8")
        sources[revision, name] = source
        data = inventory[revision][name]
        assert data["sha256"] == hashlib.sha256(result.stdout).hexdigest()
        if name == "styles.css":
            # Every rule opening (including nested media rules), not declarations
            # whose values happen to contain '#' or '.'. Preserve original lines.
            clean = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), source, flags=re.S)
            rules = []
            previous = 0
            for match in re.finditer(r"[{}]", clean):
                if match.group() == "{":
                    header = clean[previous:match.start()].strip()
                    if header:
                        offset = previous + len(clean[previous:match.start()]) - len(clean[previous:match.start()].lstrip())
                        rules.append({"line": clean.count("\n", 0, offset) + 1,
                                      "source": " ".join(header.split())})
                previous = match.end()
            data["selectors"] = rules
            data["root_tokens"] = [{"line": source.count("\n", 0, m.start()) + 1, "source": m.group()}
                                   for m in re.finditer(r"--[\w-]+\s*:[^;]+;", source)]
        if name == "types.ts":
            data["bridge_methods"] = [{"line": i, "source": line.strip(),
                "function": re.match(r"\s*(\w+)\(", line).group(1)}
                for i, line in enumerate(source.splitlines(), 1)
                if i >= source[:source.index("export interface WorkPanelBridge")].count("\n") + 1
                and re.match(r"\s*\w+\(", line)]

# One row per user-visible contract; helper/event appendices below trace every
# scanned source function and DOM/bridge reference to these contracts.
rows = [
 ("S01", "main.ts", "renderShell bindShell setMode renderActiveView viewRoot", "Chat／Today／Settings／Schedule 點選 → 同一主畫面", "WorkCompanionView.set_page；qt_app._build_ui；Qt", "PASS", "單一正式 shell、沒有第二 Console builder；test_v1_work_companion_view.py"),
 ("S02", "main.ts", "bindShell", "最小化／最大化／關閉 → 原生視窗／tray", "QMainWindow 原生標題列；closeEvent／tray owner", "PASS", "test_g5_desktop.py；實際桌面 tray 仍 UNVERIFIED"),
 ("S03", "main.ts", "renderChrome onRuntimeState refreshAll", "runtime 狀態 → 連線／語音／感知與診斷", "_on_chat_state_changed／_sync_pet_controls／_refresh_diagnostics", "PASS", "Qt／Launcher／Conversation／Pet 各自回報；test_r2_settings_parity.py；不以 Pet WS 代替 Qt 連線"),
 ("H01", "main.ts", "setHistoryOpen renderHistoryDrawer", "toggle／scrim／Escape／close → 可見抽屜與返回焦點", "WorkCompanionView 唯一 HistoryDrawer", "PASS", "test_r1_production_view.py、test_v1_work_companion_view.py；HistoryChatPage 已移除"),
 ("H02", "main.ts", "renderHistoryDrawer", "title＋preview 查詢 → 篩選／找不到", "HistoryDrawer.search／_filter；WS list", "PASS", "test_r1_production_view.py、test_r4_history_transport.py"),
 ("H03", "main.ts", "historyRow", "owner 記錄 → title／preview／time／active／刪除", "HistoryDrawer.set_records；_on_chat_protocol_message", "PASS", "canonical last_preview／summary_short；不把 preview 當 assistant 回覆"),
 ("H04", "main.ts", "refreshHistory applyHistoryPayload scheduleHistoryRefresh", "讀取 → 清單／目前 UID／loading／error", "QtRuntimeChatClient.request_history_list → fenced WS → Conversation", "PASS", "test_r1_history_parity.py、test_r4_history_transport.py；strict read 失敗不回假空清單"),
 ("H05", "main.ts", "createNewHistory", "明確新對話 → owner 建立一次／清空對話草稿", "create_history → _handle_fenced_history → create_new_history", "PASS", "request id 去重、expected history／conf／client／context；test_r4_history_transport.py"),
 ("H06", "main.ts", "selectHistory", "UID → 同角色 context／canonical timeline／active", "_request_history_selection → select_history → Runtime", "PASS", "同 UID 不重複 apply；busy／foreign／stale 回應拒絕；test_r1_history_parity.py"),
 ("H07", "main.ts", "deleteHistory", "UID＋title＋二次確認 → Runtime 刪除／取消／error", "_delete_history_by_uid → delete_history(confirmed=True)", "PASS", "native confirmation 前後 identity fence；temp owner CRUD；test_r4_history_transport.py；雙檔刪除非 atomic，失敗明示可能部分刪除"),
 ("H08", "main.ts", "renderHistoryDrawer", "離線／busy／空／query miss／錯誤 → 分別顯示", "HistoryDrawer.set_state；15 秒 pending deadline", "PASS", "test_r1_production_view.py；未知結果不自動重送"),
 ("C01", "main.ts", "renderChat updateChatHeader", "profile/history → 標題／ID／生效模型／推理", "_update_chat_identity；Qt client handshake", "PASS", "test_r1_production_view.py；角色／模型完整選單集中六類 Settings，Chat 可直達"),
 ("C02", "main.ts", "populateChatControls applyProfilePatch reconcileProfileRuntime", "role／project／model／thinking → 確認／待套用／owner 生效", "_confirm_profile_apply／_on_thinking_changed → QtLauncherController.start_profile", "PASS", "新 context＋相符 conf/project/model/thinking 才顯示生效；取消復原；test_r2_settings_parity.py"),
 ("C03", "main.ts", "mergedChatMessages renderChatTranscript", "訊息＋工具事件 → YOU／KURO／EVENT／時間", "Conversation.get_history_timeline → transcript_html／tool_call_status", "PASS", "test_r1_history_parity.py、test_r4_history_transport.py；同舊 Git qt_controller.py:517 limit=120，目前明示上限；前後均未提供更早分頁"),
 ("C04", "main.ts", "renderChatTranscript", "文字／更新 → HTML escape／保留換行與閱讀位置", "QTextEdit＋transcript_html", "PASS", "test_v1_work_companion_view.py；原 Git 是 plain pre-wrap，未擅自改 Markdown 執行"),
 ("C05", "main.ts", "updateComposerState setComposerNotice sendCurrentText", "Enter／Shift+Enter／IME／草稿＋附件 → 單一 Qt-primary turn", "ComposerEdit → _queue_chat_submit → QtRuntimeChatClient.send_text", "PASS", "test_g3_conversation.py、test_r1_production_view.py；Pet 缺席可用；context fence、送出失敗保留草稿"),
 ("C06", "main.ts", "stopOutput", "停止 → scoped interrupt 請求", "_interrupt_chat → Qt-primary WS", "PASS", "test_r1_production_view.py；等 owner control，無假播放 ack／假完成"),
 ("C07", "main.ts", "addFiles renderAttachments classifyFile attachmentLimit readFileAsDataUrl fileExtension formatFileSize", "最多 6 附件／分類上限 → 顯示／移除／送出", "_add_chat_attachments／_build_chat_attachment／_render_chat_attachments", "PASS", "4／8／12／16／24 MiB＋讀取時大小再檢查；test_v1_work_companion_view.py、test_g3_conversation.py"),
 ("C08", "main.ts", "renderChatContext bringItemToChat", "Core 項目 → 可見參考草稿／脈絡標記；移除標記", "TodayPage.context_requested → _use_today_context", "PASS", "test_r3_today_schedule_parity.py；保留 limitations；不自動送出／不在背景注入內容"),
 ("C09", "main.ts", "onChatState", "tool／text／control → 狀態與 timeline 更新", "QtRuntimeChatClient → _on_chat_protocol_message", "PASS", "test_r1_history_parity.py；tool preview 不當回答；晚到 turn context 被拒絕"),
 ("A01", "main.ts", "renderSettings settingsSelectRow settingsGroup settingToggle", "六分類 → 同一 Settings 頁面", "_build_settings_surface／SETTINGS_LABELS", "PASS", "test_r2_settings_parity.py；6 類同 shell，沒有 settings QDialog"),
 ("A02", "main.ts", "settingsAssistantGroup", "允許角色／專案／模型／推理 → 選取待套用", "_build_workspace_page → QtLauncherController", "PASS", "test_r2_settings_parity.py；設定 allowlist，不添加 provider"),
 ("A03", "main.ts", "applyProfilePatch", "native confirm → profile apply／reconcile／timeout", "_confirm_profile_apply → start_profile／既有 hot switch", "PASS", "fixture 驗證 confirmed selection 與 runtime identity；實際模型／語音採用 UNVERIFIED"),
 ("M01", "main.ts", "settingsConversationGroup", "目前標題／數量／保存說明／History／新對話", "_update_chat_identity／_open_history_from_settings／同一 drawer", "PASS", "WS 已讀清單與 active UID；未完成讀取不顯示為 0 段"),
 ("M02", "main.ts", "refreshMemories settingsMemoryGroup memoryRow", "記憶清單 → 狀態／類型／scope／source／更新／詳情", "_refresh_memory_list／read_memory_records → canonical Memory", "PASS", "test_r2_settings_parity.py；synthetic records；私有 Memory 未讀取"),
 ("M03", "main.ts", "addMemoryFromSettings", "新增內容＋confirm → owner add／unchanged／error", "_add_memory_dialog → controller.add_memory(expected_conf_uid)", "PASS", "現 owner 僅 260 字，舊 UI 1200 字上限未恢復（GAP）；不默默截斷；test_r2_settings_parity.py"),
 ("M04", "main.ts", "runMemoryAction", "approve／reject／enable／disable → digest-fenced 更新", "_change_selected_memory → set_memory_status", "PASS", "已確認 record digest／conf uid；test_r2_settings_parity.py、test_mcp_m0_memory.py"),
 ("M05", "main.ts", "runMemoryAction", "刪除確認 → digest-fenced owner delete", "controller.delete_memory → delete_character_memory", "PASS", "沒有新 store；stale review 拒絕；test_r2_settings_parity.py、test_character_memory_manager.py"),
 ("M06", "main.ts", "runMemoryAction", "整理确认＋所有當時 digests → compact 結果", "controller.compact_memory → compact_character_memories", "PASS", "snapshot 改變拒絕；test_r2_settings_parity.py；未宣稱跨 process transaction"),
 ("V01", "main.ts", "sensorEnabled microphonePaused updateSensorControls handleMicrophonePrimary runMicrophoneAction settingsMicrophoneRow", "開始／暫停／繼續／完成送出／取消 → Pet capture 狀態", "_microphone_action → pet-local mic-*；Qt send_capture", "PASS", "test_r2_settings_parity.py、test_g6_pet_boundary.py；錄音綁 context，無裝置測試"),
 ("V02", "main.ts", "toggleSensor settingsPerceptionGroup", "camera／screen 明確啟用 → owner state／error", "_set_pet_toggle_from_menu → controller.set_pet_toggle", "PASS", "啟用原生確認與 context fence；未知擷取能力時 disabled；真感知 UNVERIFIED"),
 ("V03", "main.ts", "renderChrome", "感知狀態 → 跨頁持續指示", "RuntimeStatus.capture_available／mic_paused → privacy_status", "PASS", "test_r2_settings_parity.py；未知不顯示為已關閉"),
 ("T01", "main.ts", "settingsToolsGroup", "工具／category／mode／reason／default → 唯讀政策", "read_tool_policy_summary → ToolPolicy.check；Settings tools", "PASS", "不 execute 工具；stored policy 与 runtime 採用分開；test_r2_settings_parity.py"),
 ("T02", "main.ts", "settingsToolsGroup", "需要工具確認 → blocked explanation", "現有 ToolPolicy owner", "GAP", "沒有正式確認隊列／權限寫入 owner；控制 disabled，沒有全域 allow 旁路（原 UI 也未提供此隊列）"),
 ("P01", "main.ts", "settingsPetGroup applyOutfit", "服裝選擇＋套用 → Pet set-outfit", "QtLauncherController.apply_outfit；Pet owner", "PASS", "既有 gateway；Pet 狀態缺席 disabled；test_r2_settings_parity.py／test_g6_pet_boundary.py；Live2D 實機 UNVERIFIED"),
 ("P02", "main.ts", "applyExpression", "preset → Pet set-expression", "expression_options／controller.set_expression", "PASS", "目前 owner 註冊選項；不讀寫 model asset；實機 UNVERIFIED"),
 ("P03", "main.ts", "settingsPetGroup", "播放待機 → play-motion Idle", "run_pet_command → Pet", "PASS", "test_r2_settings_parity.py"),
 ("P04", "main.ts", "setPetBoolean", "滑鼠穿透／game mode → owner state", "controller.set_pet_toggle／_sync_pet_controls", "PASS", "沿用 allowlist；未取得 Pet 狀態時 disabled；test_g6_pet_boundary.py"),
 ("P05", "main.ts", "settingsPetGroup", "顯示／移下一螢幕／重置位置 → Pet geometry", "show_pet／move_pet_next_display／reset-pet-position", "PASS", "test_r2_settings_parity.py；多螢幕實機 UNVERIFIED"),
 ("D01", "main.ts", "settingsExperienceGroup applyPreferences", "compact／reduce motion → local appearance", "QSettings compact＋transcript_html；Qt 無 drawer 動畫", "PASS", "test_r2_settings_parity.py；reduce motion 固定啟用 disabled＋理由，非兩種動畫還原"),
 ("D02", "main.ts", "capabilitySummary settingsRuntimeGroup", "owner 狀態 → phase／reason／voice／revision／profile", "_refresh_diagnostics／CoreHealthPage", "PASS", "test_r2_settings_parity.py、test_runtime_capabilities.py；runtime adoption 未驗證"),
 ("D03", "main.ts", "settingsRuntimeGroup", "retry／stop／restart＋confirm → lifecycle 請求", "Launcher retry_runtime／stop_profile／restart signal", "PASS", "test_g5_desktop.py；停止保留 Pet／Core／共享語音；此工作沒有實際執行"),
 ("D04", "main.ts", "settingsRuntimeGroup", "reset／retry-pet-model → 重置／重新載入角色", "reset-pet-position／_reload_pet_model → reload_pet_frontend", "PASS", "舊 pet-electron/src/main.js:3155 亦 webContents.reload；新按鈕確認＋Pet 可用才啟用；test_r2_settings_parity.py"),
 ("D05", "main.ts", "settingsSourceGroup", "source state → status／time／limitations", "CoreHealthPage／read_today；Core", "PASS", "test_g4_qt_core.py；不觸發 provider refresh"),
 ("Y01", "main.ts", "onBriefingData renderToday renderPriorityBlock", "Core snapshot → 優先項目／數量／時間", "TodayPage.apply；Core /v1/today", "PASS", "test_r3_today_schedule_parity.py；刷新按 workId 保留選取與詳情"),
 ("Y02", "main.ts", "renderSourcesBlock", "Core source filter → items／status", "TodayPage._render_items／Core sourceStates", "PASS", "未複製 model.ts 的 market/domain 排序；test_r3_today_schedule_parity.py"),
 ("Y03", "main.ts", "openDetail closeDetail renderDetail", "workId → reason／evidence／time／stale／limitations", "TodayPage.show_detail／detail_text", "PASS", "test_r3_today_schedule_parity.py；inline 詳情取代 web drawer；失敗標記上次投影並停用草稿按鈕"),
 ("Y04", "main.ts", "bringItemToChat", "選定項目 → 可見且可編輯 Chat 草稿", "Core projection → _use_today_context", "PASS", "test_r3_today_schedule_parity.py；無自動 send"),
 ("L01", "model.ts", "normalizeViewItem sectionItems uniqueItems todayItems sourceItems priorityItems sourceCount sourceStatus", "legacy Briefing 分類／priority → 前端投影", "由 Core Work／Attention／Today 取代", "LEGACY", "不恢復 frontend ranking、Market／Mail fetcher 或新 cache"),
 ("L02", "main.ts", "refreshMail", "Mail confirm → 舊 provider refresh", "無正式 Qt action owner", "LEGACY", "Today 明示手動刷新未恢復；不復活舊 provider path"),
 ("L03", "main.ts", "loadMailDetail", "messageId → 舊 mail body", "無 Core canonical body projection", "LEGACY", "明示當前郵件內文與 Study 課程跳轉不可用；不直連 provider／OAuth"),
 ("L04", "main.ts", "", "fallbackBridge／window.kuroWorkPanel／舊 IPC", "正式 Qt 不存在此路徑", "LEGACY", "G7 35/35 absent；test_g8_runtime.py、test_v1_work_companion_view.py"),
 ("Q01", "schedule.ts", "call refresh render", "date／day／week／today／more → Core view／coverage", "SchedulePage.refresh／load_more → read_schedule_view", "PASS", "test_g4_qt_core.py、test_schedule_api.py；僅 Core"),
 ("Q02", "schedule.ts", "edit modal field select input", "新增／修改欄位 → prepare→confirm→mutate", "ScheduleEditor.save／item_payload → Core", "PASS", "test_g4_qt_core.py、test_schedule_core.py；失敗保留 draft"),
 ("Q03", "schedule.ts", "edit", "recurrence／count／until／scope → revision fenced command", "ScheduleEditor → existing Core schema", "PASS", "test_schedule_core.py、test_g4_qt_core.py"),
 ("Q04", "schedule.ts", "row mutateState cancel", "complete／cancel＋target revision＋scope＋confirm＋key", "SchedulePage.mutate／command → Core", "PASS", "test_r3_today_schedule_parity.py、test_schedule_core.py"),
 ("Q05", "schedule.ts", "noticeAction", "read／dismiss／snooze → Core notification action", "SchedulePage.reminder_action／QtScheduleDelivery", "PASS", "test_g5_desktop.py、test_g8_runtime.py、test_schedule_notifications.py；OS notification UNVERIFIED"),
 ("Q06", "schedule.ts", "editPreferences", "quiet hours／timezone＋confirm → preferences", "SchedulePage.reminder_action → Core", "PASS", "test_schedule_notifications.py；現成 canonical preferences"),
 ("Q07", "schedule.ts", "refresh", "async refresh → latest query／selection stable", "CorePage one-flight＋SchedulePage query generation", "PASS", "test_g4_qt_core.py、test_r3_today_schedule_parity.py；沒有平行 manager"),
]
by_id = {row[0]: row for row in rows}

def function_ids(name, function, line):
    if name == "main.ts" and line < 100:
        return ["L04"]
    ids = [r[0] for r in rows if r[1] == name and function in r[2].split()]
    if ids:
        return ids
    helpers = {"main.ts": {"button": "S01", "toBoolean": "P04", "normalizeMode": "S01", "isBusyState": "C05",
        "wait": "C02", "messageRoleLabel": "C03", "messageRoleClass": "C03", "constructor": "S01",
        "runControl": "D03", "hideToast": "C05", "showToast": "C05"},
        "types.ts": {"refreshMail": "L02"},
        "model.ts": {key: "Y03" for key in ("text", "sourceLabel", "levelLabel", "statusLabel", "statusTone", "formatDateLabel", "formatFullDate")},
        "schedule.ts": {"btn": "Q01", "shift": "Q01", "errorText": "Q01", "constructor": "Q01"}}
    return [helpers[name][function]]  # A new/unmapped source function fails generation.

def refs(row):
    name, names = row[1], row[2].split()
    found = []
    for function in names:
        matches = [x for x in inventory["HEAD"][name]["functions"] if x["function"] == function]
        assert matches, (name, function)
        found.append(f"{function} L{matches[-1]['line']}")
    return name + ": " + ("；".join(found) if found else "fallbackBridge L65–85")

def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;")

def table(headers, records):
    return ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(cell(c) for c in record) + " |" for record in records], ""]

doc = ["# Git Work Companion 功能對照", "",
       "R0 精確 Git inventory 與 R1–R3 source 接線已完成；R4 為隔離驗證／source cutover，真人桌面和獨立 Reviewer 仍 **UNVERIFIED**。不能把這份表解讀為實機驗收通過。", "",
       "`PASS` 僅指列出的 source／fixture 證據；`GAP` 是未恢復能力；`LEGACY` 是退役且不可復活的 owner／路徑；`UNVERIFIED` 是尚無足夠實機或視覺證據。", "",
       "## 精確來源", "",
       "原路徑前綴：`pet-electron/renderer/src/work-panel/`。HEAD=`995c23c7c8d1be62000229d58610d2214f3bb745`；比較 `3baf05728921607d71306c98d43eaad155b0dbc1`。只用 `git show` 讀取，沒有恢復工作樹檔案。完整來源 hashes／functions／DOM references／CSS rules／bridge signatures：[GitSourceInventory.json](GitSourceInventory.json)。", "",
       "| 檔案 | HEAD 行數 | 3baf057 行數 |", "| --- | ---: | ---: |"]
for name in ("main.ts", "types.ts", "model.ts", "schedule.ts", "styles.css"):
    before = inventory[BASE].get(name, {})
    doc.append(f"| {name} | {inventory['HEAD'][name]['lines']} | {before.get('lines', '不存在')} |")
doc += ["", "HEAD 增加 Schedule UI 與 capabilities/reconcile 邏輯，兩版都是 moon／teal、78px rail。這兩個 Git commit **沒有 gold／180px exact snapshot 證據**；不能宣稱圖 A 是其中某版。Qt Chat 180px／gold 與 Settings 73px／teal 依使用者圖 A/B 的文字描述。原始兩張圖未附在本輪，逐像素 fidelity **UNVERIFIED**。HEAD CSS 實測 2233 行，不能沿用 1794 行舊描述。", "", "## 逐功能 input → output／正式 consumer／owner", ""]
doc += table(["ID", "Git 原檔／function（精確行號）", "input → output", "CurrentQt consumer／gateway／owner", "狀態", "證據／限制"],
             [(r[0], refs(r), *r[3:]) for r in rows])
doc += ["## 所有 source functions 的歸屬", "", "以下包含純 presentation helpers 及 fallback methods，避免只列主按鈕漏掉來源功能。相同 ID 的 input/output、owner、測試與限制以上表為準。", ""]
function_records = []
for name in ("main.ts", "types.ts", "model.ts", "schedule.ts"):
    for item in inventory["HEAD"][name]["functions"]:
        ids = function_ids(name, item["function"], item["line"])
        function_records.append((f"{name}:{item['line']} {item['function']}", ", ".join(ids),
                                 ", ".join(sorted({by_id[key][5] for key in ids}))))
doc += table(["Git function", "對照契約", "狀態（承接限制）"], function_records)
doc += ["## DOM events／元素／bridge calls 逐項索引", "", "保留來源程式行；data-* markup 與 callback 皆列出。CSS 的 data selector 在下節，並非 JS event。", ""]
event_records = []
for name in ("main.ts", "schedule.ts"):
    functions = inventory["HEAD"][name]["functions"]
    for item in inventory["HEAD"][name]["events"]:
        enclosing = [f for f in functions if f["line"] <= item["line"]][-1]
        ids = function_ids(name, enclosing["function"], enclosing["line"])
        event_records.append((f"{name}:{item['line']}", f"`{item['source']}`", ", ".join(ids)))
doc += table(["Git 位置", "實際 source reference", "契約"], event_records)
doc += ["## WorkPanelBridge 原契約 → 現行 gateway", ""]
methods = {"schedule": "Q01 Q02 Q03 Q04 Q05 Q06 Q07", "getState": "S03", "getData": "Y01 L01",
    "getChatState": "C09", "getChatHistory": "C03", "getProfile": "A02", "applyProfile": "A03",
    "getHistories": "H04", "createHistory": "H05", "selectHistory": "H06", "deleteHistory": "H07",
    "getMemories": "M02", "memoryAction": "M03 M04 M05 M06", "getTools": "T01 T02", "sendText": "C05 C07",
    "refreshMail": "L02", "getMailMessage": "L03", "control": "C06 V01 V02 P01 P02 P03 P04 P05 D03 D04",
    "closeWindow": "S02", "minimizeWindow": "S02", "toggleMaximizeWindow": "S02", "onState": "S03",
    "onData": "Y01", "onChatState": "C09"}
doc += table(["原 types.ts signature", "正式語義歸屬（不恢復原 bridge）"],
             [(f"L{item['line']} `{item['source']}`", methods[item["function"]])
              for item in inventory["HEAD"]["types.ts"]["bridge_methods"]])
doc += ["## CSS 結構逐項索引", "",
       "Qt Widgets/QSS 不執行原 DOM/CSS。以下每個原 CSS rule 都留位置與對映區域；structural／interaction tests 可 PASS，像素與動畫仍 **UNVERIFIED**，不把 selector 掃描當作 fidelity 通過。Native window buttons 由 QMainWindow 提供；reduce-motion 固定啟用。", ""]
def css_consumer(header):
    for token, target in (("history", "HistoryDrawer／HistoryScrim／HistoryOpen"), ("schedule", "SchedulePage／ScheduleEditor"),
            ("settings", "SettingsSurface／SettingsNav／_settings_row"), ("composer", "ComposerPanel／ComposerEdit／AttachmentTray"),
            ("message", "TranscriptBox／transcript_html"), ("chat", "_build_chat_tab／chat header／context"),
            ("source", "TodayPage.sources／CoreHealthPage"), ("priority", "TodayPage.priority"),
            ("detail", "TodayPage.detail／SchedulePage.detail"), ("rail", "Rail／CompanionNav"),
            ("chrome", "Chrome／privacy_status"), ("toast", "native QMessageBox／status labels"),
            ("memory", "memory_list／memory_detail"), ("toggle", "QCheckBox／QPushButton checked")):
        if token in header:
            return target
    return "qt_work_companion_theme TOKENS／QSS／native Qt controls"
doc += table(["styles.css rule", "Qt 結構", "fidelity"],
             [(f"L{item['line']} `{item['source']}`", css_consumer(item['source']), "UNVERIFIED")
              for item in inventory["HEAD"]["styles.css"]["selectors"]])
doc += ["## 明確未恢復／驗證邊界", "",
       "- 無新 provider 或 owner：Mail 手動刷新／郵件內文、Study 課程跳轉保持不可用。Mail/Study 的來源狀態仍顯示 Core 真實 disabled/unavailable/partial 值，不一律捏造成正常或停用。",
       "- 工具確認隊列／政策寫入未有 canonical owner；保持 blocked／disabled。政策檔可讀不代表 running runtime 已採用。",
       "- 舊 Memory 1200 字 UI 與目前 260 字 owner 不相容；明示 260 字並保留超長草稿。",
       "- History 最近 120 則的 canonical timeline 已包含工具事件（舊 Git qt_controller.py:517 亦 limit=120）；前後均未提供更早分頁，現會顯示上限。兩個 history 檔案刪除不是 atomic，錯誤訊息明示不確定結果。",
       "- Chat role/model 選單集中 Settings，Chat 有直達入口；Today 詳情是同頁 panel。這是單一 Qt 結構對映，不能稱 Web DOM 像素原封移植。",
       "- 125%／200% Qt offscreen、temp WS/HTTP/DB 與 fixture 是 source 證據。真實 IME、Windows GPU／tray／多螢幕、Live2D、Mic/camera/screen、model/voice、個人資料及原截圖 fidelity 全部 UNVERIFIED。",
       "- 一次 source cutover 只有 WorkCompanionView；V1 synthetic model／preview 程式已退役。正式執行中的舊 Qt 未被重啟，需使用者之後實機驗收。", ""]
(HERE / "GitSourceInventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
(HERE / "GitWorkCompanionParityMatrix.md").write_text("\n".join(doc), encoding="utf-8")
print(json.dumps({"features": len(rows), "functions": len(function_records), "ui_references": len(event_records),
                  "bridge_methods": len(methods), "css_rules": len(inventory["HEAD"]["styles.css"]["selectors"]) }))
