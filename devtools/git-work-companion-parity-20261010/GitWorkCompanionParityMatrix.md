# Git Work Companion 功能對照

R0 精確 Git inventory 與 R1–R3 source 接線已完成；R4 為隔離驗證／source cutover，真人桌面和獨立 Reviewer 仍 **UNVERIFIED**。不能把這份表解讀為實機驗收通過。

`PASS` 僅指列出的 source／fixture 證據；`GAP` 是未恢復能力；`LEGACY` 是退役且不可復活的 owner／路徑；`UNVERIFIED` 是尚無足夠實機或視覺證據。

## 精確來源

原路徑前綴：`pet-electron/renderer/src/work-panel/`。HEAD=`995c23c7c8d1be62000229d58610d2214f3bb745`；比較 `3baf05728921607d71306c98d43eaad155b0dbc1`。只用 `git show` 讀取，沒有恢復工作樹檔案。完整來源 hashes／functions／DOM references／CSS rules／bridge signatures：[GitSourceInventory.json](GitSourceInventory.json)。

| 檔案 | HEAD 行數 | 3baf057 行數 |
| --- | ---: | ---: |
| main.ts | 1951 | 1853 |
| types.ts | 286 | 277 |
| model.ts | 204 | 210 |
| schedule.ts | 170 | 不存在 |
| styles.css | 2233 | 2196 |

HEAD 增加 Schedule UI 與 capabilities/reconcile 邏輯，兩版都是 moon／teal、78px rail。這兩個 Git commit **沒有 gold／180px exact snapshot 證據**；不能宣稱圖 A 是其中某版。Qt Chat 180px／gold 與 Settings 73px／teal 依使用者圖 A/B 的文字描述。原始兩張圖未附在本輪，逐像素 fidelity **UNVERIFIED**。HEAD CSS 實測 2233 行，不能沿用 1794 行舊描述。

## 逐功能 input → output／正式 consumer／owner

| ID | Git 原檔／function（精確行號） | input → output | CurrentQt consumer／gateway／owner | 狀態 | 證據／限制 |
| --- | --- | --- | --- | --- | --- |
| S01 | main.ts: renderShell L230；bindShell L279；setMode L408；renderActiveView L606；viewRoot L613 | Chat／Today／Settings／Schedule 點選 → 同一主畫面 | WorkCompanionView.set_page；qt_app._build_ui；Qt | PASS | 單一正式 shell、沒有第二 Console builder；test_v1_work_companion_view.py |
| S02 | main.ts: bindShell L279 | 最小化／最大化／關閉 → 原生視窗／tray | QMainWindow 原生標題列；closeEvent／tray owner | PASS | test_g5_desktop.py；實際桌面 tray 仍 UNVERIFIED |
| S03 | main.ts: renderChrome L558；onRuntimeState L364；refreshAll L293 | runtime 狀態 → 連線／語音／感知與診斷 | _on_chat_state_changed／_sync_pet_controls／_refresh_diagnostics | PASS | Qt／Launcher／Conversation／Pet 各自回報；test_r2_settings_parity.py；不以 Pet WS 代替 Qt 連線 |
| H01 | main.ts: setHistoryOpen L417；renderHistoryDrawer L423 | toggle／scrim／Escape／close → 可見抽屜與返回焦點 | WorkCompanionView 唯一 HistoryDrawer | PASS | test_r1_production_view.py、test_v1_work_companion_view.py；HistoryChatPage 已移除 |
| H02 | main.ts: renderHistoryDrawer L423 | title＋preview 查詢 → 篩選／找不到 | HistoryDrawer.search／_filter；WS list | PASS | test_r1_production_view.py、test_r4_history_transport.py |
| H03 | main.ts: historyRow L482 | owner 記錄 → title／preview／time／active／刪除 | HistoryDrawer.set_records；_on_chat_protocol_message | PASS | canonical last_preview／summary_short；不把 preview 當 assistant 回覆 |
| H04 | main.ts: refreshHistory L313；applyHistoryPayload L497；scheduleHistoryRefresh L356 | 讀取 → 清單／目前 UID／loading／error | QtRuntimeChatClient.request_history_list → fenced WS → Conversation | PASS | test_r1_history_parity.py、test_r4_history_transport.py；strict read 失敗不回假空清單 |
| H05 | main.ts: createNewHistory L515 | 明確新對話 → owner 建立一次／清空對話草稿 | create_history → _handle_fenced_history → create_new_history | PASS | request id 去重、expected history／conf／client／context；test_r4_history_transport.py |
| H06 | main.ts: selectHistory L529 | UID → 同角色 context／canonical timeline／active | _request_history_selection → select_history → Runtime | PASS | 同 UID 不重複 apply；busy／foreign／stale 回應拒絕；test_r1_history_parity.py |
| H07 | main.ts: deleteHistory L547 | UID＋title＋二次確認 → Runtime 刪除／取消／error | _delete_history_by_uid → delete_history(confirmed=True) | PASS | native confirmation 前後 identity fence；temp owner CRUD；test_r4_history_transport.py；雙檔刪除非 atomic，失敗明示可能部分刪除 |
| H08 | main.ts: renderHistoryDrawer L423 | 離線／busy／空／query miss／錯誤 → 分別顯示 | HistoryDrawer.set_state；15 秒 pending deadline | PASS | test_r1_production_view.py；未知結果不自動重送 |
| C01 | main.ts: renderChat L619；updateChatHeader L726 | profile/history → 標題／ID／生效模型／推理 | _update_chat_identity；Qt client handshake | PASS | test_r1_production_view.py；角色／模型完整選單集中六類 Settings，Chat 可直達 |
| C02 | main.ts: populateChatControls L745；applyProfilePatch L802；reconcileProfileRuntime L330 | role／project／model／thinking → 確認／待套用／owner 生效 | _confirm_profile_apply／_on_thinking_changed → QtLauncherController.start_profile | PASS | 新 context＋相符 conf/project/model/thinking 才顯示生效；取消復原；test_r2_settings_parity.py |
| C03 | main.ts: mergedChatMessages L975；renderChatTranscript L990 | 訊息＋工具事件 → YOU／KURO／EVENT／時間 | Conversation.get_history_timeline → transcript_html／tool_call_status | PASS | test_r1_history_parity.py、test_r4_history_transport.py；同舊 Git qt_controller.py:517 limit=120，目前明示上限；前後均未提供更早分頁 |
| C04 | main.ts: renderChatTranscript L990 | 文字／更新 → HTML escape／保留換行與閱讀位置 | QTextEdit＋transcript_html | PASS | test_v1_work_companion_view.py；原 Git 是 plain pre-wrap，未擅自改 Markdown 執行 |
| C05 | main.ts: updateComposerState L1041；setComposerNotice L1072；sendCurrentText L1130 | Enter／Shift+Enter／IME／草稿＋附件 → 單一 Qt-primary turn | ComposerEdit → _queue_chat_submit → QtRuntimeChatClient.send_text | PASS | test_g3_conversation.py、test_r1_production_view.py；Pet 缺席可用；context fence、送出失敗保留草稿 |
| C06 | main.ts: stopOutput L1161 | 停止 → scoped interrupt 請求 | _interrupt_chat → Qt-primary WS | PASS | test_r1_production_view.py；等 owner control，無假播放 ack／假完成 |
| C07 | main.ts: addFiles L1085；renderAttachments L1112；classifyFile L156；attachmentLimit L168；readFileAsDataUrl L176；fileExtension L148；formatFileSize L185 | 最多 6 附件／分類上限 → 顯示／移除／送出 | _add_chat_attachments／_build_chat_attachment／_render_chat_attachments | PASS | 4／8／12／16／24 MiB＋讀取時大小再檢查；test_v1_work_companion_view.py、test_g3_conversation.py |
| C08 | main.ts: renderChatContext L1027；bringItemToChat L1386 | Core 項目 → 可見參考草稿／脈絡標記；移除標記 | TodayPage.context_requested → _use_today_context | PASS | test_r3_today_schedule_parity.py；保留 limitations；不自動送出／不在背景注入內容 |
| C09 | main.ts: onChatState L377 | tool／text／control → 狀態與 timeline 更新 | QtRuntimeChatClient → _on_chat_protocol_message | PASS | test_r1_history_parity.py；tool preview 不當回答；晚到 turn context 被拒絕 |
| A01 | main.ts: renderSettings L1397；settingsSelectRow L1439；settingsGroup L1701；settingToggle L1710 | 六分類 → 同一 Settings 頁面 | _build_settings_surface／SETTINGS_LABELS | PASS | test_r2_settings_parity.py；6 類同 shell，沒有 settings QDialog |
| A02 | main.ts: settingsAssistantGroup L1463 | 允許角色／專案／模型／推理 → 選取待套用 | _build_workspace_page → QtLauncherController | PASS | test_r2_settings_parity.py；設定 allowlist，不添加 provider |
| A03 | main.ts: applyProfilePatch L802 | native confirm → profile apply／reconcile／timeout | _confirm_profile_apply → start_profile／既有 hot switch | PASS | fixture 驗證 confirmed selection 與 runtime identity；實際模型／語音採用 UNVERIFIED |
| M01 | main.ts: settingsConversationGroup L1513 | 目前標題／數量／保存說明／History／新對話 | _update_chat_identity／_open_history_from_settings／同一 drawer | PASS | WS 已讀清單與 active UID；未完成讀取不顯示為 0 段 |
| M02 | main.ts: refreshMemories L322；settingsMemoryGroup L1539；memoryRow L1578 | 記憶清單 → 狀態／類型／scope／source／更新／詳情 | _refresh_memory_list／read_memory_records → canonical Memory | PASS | test_r2_settings_parity.py；synthetic records；私有 Memory 未讀取 |
| M03 | main.ts: addMemoryFromSettings L1600 | 新增內容＋confirm → owner add／unchanged／error | _add_memory_dialog → controller.add_memory(expected_conf_uid) | PASS | 現 owner 僅 260 字，舊 UI 1200 字上限未恢復（GAP）；不默默截斷；test_r2_settings_parity.py |
| M04 | main.ts: runMemoryAction L1609 | approve／reject／enable／disable → digest-fenced 更新 | _change_selected_memory → set_memory_status | PASS | 已確認 record digest／conf uid；test_r2_settings_parity.py、test_mcp_m0_memory.py |
| M05 | main.ts: runMemoryAction L1609 | 刪除確認 → digest-fenced owner delete | controller.delete_memory → delete_character_memory | PASS | 沒有新 store；stale review 拒絕；test_r2_settings_parity.py、test_character_memory_manager.py |
| M06 | main.ts: runMemoryAction L1609 | 整理确认＋所有當時 digests → compact 結果 | controller.compact_memory → compact_character_memories | PASS | snapshot 改變拒絕；test_r2_settings_parity.py；未宣稱跨 process transaction |
| V01 | main.ts: sensorEnabled L862；microphonePaused L869；updateSensorControls L873；handleMicrophonePrimary L901；runMicrophoneAction L909；settingsMicrophoneRow L1640 | 開始／暫停／繼續／完成送出／取消 → Pet capture 狀態 | _microphone_action → pet-local mic-*；Qt send_capture | PASS | test_r2_settings_parity.py、test_g6_pet_boundary.py；錄音綁 context，無裝置測試 |
| V02 | main.ts: toggleSensor L948；settingsPerceptionGroup L1621 | camera／screen 明確啟用 → owner state／error | _set_pet_toggle_from_menu → controller.set_pet_toggle | PASS | 啟用原生確認與 context fence；未知擷取能力時 disabled；真感知 UNVERIFIED |
| V03 | main.ts: renderChrome L558 | 感知狀態 → 跨頁持續指示 | RuntimeStatus.capture_available／mic_paused → privacy_status | PASS | test_r2_settings_parity.py；未知不顯示為已關閉 |
| T01 | main.ts: settingsToolsGroup L1672 | 工具／category／mode／reason／default → 唯讀政策 | read_tool_policy_summary → ToolPolicy.check；Settings tools | PASS | 不 execute 工具；stored policy 与 runtime 採用分開；test_r2_settings_parity.py |
| T02 | main.ts: settingsToolsGroup L1672 | 需要工具確認 → blocked explanation | 現有 ToolPolicy owner | GAP | 沒有正式確認隊列／權限寫入 owner；控制 disabled，沒有全域 allow 旁路（原 UI 也未提供此隊列） |
| P01 | main.ts: settingsPetGroup L1755；applyOutfit L1795 | 服裝選擇＋套用 → Pet set-outfit | QtLauncherController.apply_outfit；Pet owner | PASS | 既有 gateway；Pet 狀態缺席 disabled；test_r2_settings_parity.py／test_g6_pet_boundary.py；Live2D 實機 UNVERIFIED |
| P02 | main.ts: applyExpression L1811 | preset → Pet set-expression | expression_options／controller.set_expression | PASS | 目前 owner 註冊選項；不讀寫 model asset；實機 UNVERIFIED |
| P03 | main.ts: settingsPetGroup L1755 | 播放待機 → play-motion Idle | run_pet_command → Pet | PASS | test_r2_settings_parity.py |
| P04 | main.ts: setPetBoolean L1903 | 滑鼠穿透／game mode → owner state | controller.set_pet_toggle／_sync_pet_controls | PASS | 沿用 allowlist；未取得 Pet 狀態時 disabled；test_g6_pet_boundary.py |
| P05 | main.ts: settingsPetGroup L1755 | 顯示／移下一螢幕／重置位置 → Pet geometry | show_pet／move_pet_next_display／reset-pet-position | PASS | test_r2_settings_parity.py；多螢幕實機 UNVERIFIED |
| D01 | main.ts: settingsExperienceGroup L1728；applyPreferences L1919 | compact／reduce motion → local appearance | QSettings compact＋transcript_html；Qt 無 drawer 動畫 | PASS | test_r2_settings_parity.py；reduce motion 固定啟用 disabled＋理由，非兩種動畫還原 |
| D02 | main.ts: capabilitySummary L1832；settingsRuntimeGroup L1849 | owner 狀態 → phase／reason／voice／revision／profile | _refresh_diagnostics／CoreHealthPage | PASS | test_r2_settings_parity.py、test_runtime_capabilities.py；runtime adoption 未驗證 |
| D03 | main.ts: settingsRuntimeGroup L1849 | retry／stop／restart＋confirm → lifecycle 請求 | Launcher retry_runtime／stop_profile／restart signal | PASS | test_g5_desktop.py；停止保留 Pet／Core／共享語音；此工作沒有實際執行 |
| D04 | main.ts: settingsRuntimeGroup L1849 | reset／retry-pet-model → 重置／重新載入角色 | reset-pet-position／_reload_pet_model → reload_pet_frontend | PASS | 舊 pet-electron/src/main.js:3155 亦 webContents.reload；新按鈕確認＋Pet 可用才啟用；test_r2_settings_parity.py |
| D05 | main.ts: settingsSourceGroup L1883 | source state → status／time／limitations | CoreHealthPage／read_today；Core | PASS | test_g4_qt_core.py；不觸發 provider refresh |
| Y01 | main.ts: onBriefingData L371；renderToday L1166；renderPriorityBlock L1197 | Core snapshot → 優先項目／數量／時間 | TodayPage.apply；Core /v1/today | PASS | test_r3_today_schedule_parity.py；刷新按 workId 保留選取與詳情 |
| Y02 | main.ts: renderSourcesBlock L1225 | Core source filter → items／status | TodayPage._render_items／Core sourceStates | PASS | 未複製 model.ts 的 market/domain 排序；test_r3_today_schedule_parity.py |
| Y03 | main.ts: openDetail L1300；closeDetail L1321；renderDetail L1329 | workId → reason／evidence／time／stale／limitations | TodayPage.show_detail／detail_text | PASS | test_r3_today_schedule_parity.py；inline 詳情取代 web drawer；失敗標記上次投影並停用草稿按鈕 |
| Y04 | main.ts: bringItemToChat L1386 | 選定項目 → 可見且可編輯 Chat 草稿 | Core projection → _use_today_context | PASS | test_r3_today_schedule_parity.py；無自動 send |
| L01 | model.ts: normalizeViewItem L107；sectionItems L131；uniqueItems L147；todayItems L157；sourceItems L167；priorityItems L185；sourceCount L193；sourceStatus L201 | legacy Briefing 分類／priority → 前端投影 | 由 Core Work／Attention／Today 取代 | LEGACY | 不恢復 frontend ranking、Market／Mail fetcher 或新 cache |
| L02 | main.ts: refreshMail L1288 | Mail confirm → 舊 provider refresh | 無正式 Qt action owner | LEGACY | Today 明示手動刷新未恢復；不復活舊 provider path |
| L03 | main.ts: loadMailDetail L1307 | messageId → 舊 mail body | 無 Core canonical body projection | LEGACY | 明示當前郵件內文與 Study 課程跳轉不可用；不直連 provider／OAuth |
| L04 | main.ts: fallbackBridge L65–85 | fallbackBridge／window.kuroWorkPanel／舊 IPC | 正式 Qt 不存在此路徑 | LEGACY | G7 35/35 absent；test_g8_runtime.py、test_v1_work_companion_view.py |
| Q01 | schedule.ts: call L41；refresh L44；render L63 | date／day／week／today／more → Core view／coverage | SchedulePage.refresh／load_more → read_schedule_view | PASS | test_g4_qt_core.py、test_schedule_api.py；僅 Core |
| Q02 | schedule.ts: edit L123；modal L116；field L120；select L121；input L122 | 新增／修改欄位 → prepare→confirm→mutate | ScheduleEditor.save／item_payload → Core | PASS | test_g4_qt_core.py、test_schedule_core.py；失敗保留 draft |
| Q03 | schedule.ts: edit L123 | recurrence／count／until／scope → revision fenced command | ScheduleEditor → existing Core schema | PASS | test_schedule_core.py、test_g4_qt_core.py |
| Q04 | schedule.ts: row L95；mutateState L107；cancel L111 | complete／cancel＋target revision＋scope＋confirm＋key | SchedulePage.mutate／command → Core | PASS | test_r3_today_schedule_parity.py、test_schedule_core.py |
| Q05 | schedule.ts: noticeAction L161 | read／dismiss／snooze → Core notification action | SchedulePage.reminder_action／QtScheduleDelivery | PASS | test_g5_desktop.py、test_g8_runtime.py、test_schedule_notifications.py；OS notification UNVERIFIED |
| Q06 | schedule.ts: editPreferences L166 | quiet hours／timezone＋confirm → preferences | SchedulePage.reminder_action → Core | PASS | test_schedule_notifications.py；現成 canonical preferences |
| Q07 | schedule.ts: refresh L44 | async refresh → latest query／selection stable | CorePage one-flight＋SchedulePage query generation | PASS | test_g4_qt_core.py、test_r3_today_schedule_parity.py；沒有平行 manager |

## 所有 source functions 的歸屬

以下包含純 presentation helpers 及 fallback methods，避免只列主按鈕漏掉來源功能。相同 ID 的 input/output、owner、測試與限制以上表為準。

| Git function | 對照契約 | 狀態（承接限制） |
| --- | --- | --- |
| main.ts:66 schedule | L04 | LEGACY |
| main.ts:67 getState | L04 | LEGACY |
| main.ts:68 getData | L04 | LEGACY |
| main.ts:69 getChatState | L04 | LEGACY |
| main.ts:70 getChatHistory | L04 | LEGACY |
| main.ts:71 getProfile | L04 | LEGACY |
| main.ts:72 applyProfile | L04 | LEGACY |
| main.ts:73 getHistories | L04 | LEGACY |
| main.ts:74 createHistory | L04 | LEGACY |
| main.ts:75 selectHistory | L04 | LEGACY |
| main.ts:76 deleteHistory | L04 | LEGACY |
| main.ts:77 getMemories | L04 | LEGACY |
| main.ts:78 memoryAction | L04 | LEGACY |
| main.ts:79 getTools | L04 | LEGACY |
| main.ts:80 sendText | L04 | LEGACY |
| main.ts:81 refreshMail | L04 | LEGACY |
| main.ts:82 getMailMessage | L04 | LEGACY |
| main.ts:83 control | L04 | LEGACY |
| main.ts:110 button | S01 | PASS |
| main.ts:117 toBoolean | P04 | PASS |
| main.ts:122 normalizeMode | S01 | PASS |
| main.ts:126 isBusyState | C05 | PASS |
| main.ts:130 wait | C02 | PASS |
| main.ts:134 messageRoleLabel | C03 | PASS |
| main.ts:141 messageRoleClass | C03 | PASS |
| main.ts:148 fileExtension | C07 | PASS |
| main.ts:156 classifyFile | C07 | PASS |
| main.ts:168 attachmentLimit | C07 | PASS |
| main.ts:176 readFileAsDataUrl | C07 | PASS |
| main.ts:185 formatFileSize | C07 | PASS |
| main.ts:219 constructor | S01 | PASS |
| main.ts:230 renderShell | S01 | PASS |
| main.ts:279 bindShell | S01, S02 | PASS |
| main.ts:293 refreshAll | S03 | PASS |
| main.ts:313 refreshHistory | H04 | PASS |
| main.ts:322 refreshMemories | M02 | PASS |
| main.ts:330 reconcileProfileRuntime | C02 | PASS |
| main.ts:356 scheduleHistoryRefresh | H04 | PASS |
| main.ts:364 onRuntimeState | S03 | PASS |
| main.ts:371 onBriefingData | Y01 | PASS |
| main.ts:377 onChatState | C09 | PASS |
| main.ts:408 setMode | S01 | PASS |
| main.ts:417 setHistoryOpen | H01 | PASS |
| main.ts:423 renderHistoryDrawer | H01, H02, H08 | PASS |
| main.ts:482 historyRow | H03 | PASS |
| main.ts:497 applyHistoryPayload | H04 | PASS |
| main.ts:515 createNewHistory | H05 | PASS |
| main.ts:529 selectHistory | H06 | PASS |
| main.ts:547 deleteHistory | H07 | PASS |
| main.ts:558 renderChrome | S03, V03 | PASS |
| main.ts:606 renderActiveView | S01 | PASS |
| main.ts:613 viewRoot | S01 | PASS |
| main.ts:619 renderChat | C01 | PASS |
| main.ts:726 updateChatHeader | C01 | PASS |
| main.ts:745 populateChatControls | C02 | PASS |
| main.ts:802 applyProfilePatch | C02, A03 | PASS |
| main.ts:862 sensorEnabled | V01 | PASS |
| main.ts:869 microphonePaused | V01 | PASS |
| main.ts:873 updateSensorControls | V01 | PASS |
| main.ts:901 handleMicrophonePrimary | V01 | PASS |
| main.ts:909 runMicrophoneAction | V01 | PASS |
| main.ts:948 toggleSensor | V02 | PASS |
| main.ts:975 mergedChatMessages | C03 | PASS |
| main.ts:990 renderChatTranscript | C03, C04 | PASS |
| main.ts:1027 renderChatContext | C08 | PASS |
| main.ts:1041 updateComposerState | C05 | PASS |
| main.ts:1072 setComposerNotice | C05 | PASS |
| main.ts:1085 addFiles | C07 | PASS |
| main.ts:1112 renderAttachments | C07 | PASS |
| main.ts:1130 sendCurrentText | C05 | PASS |
| main.ts:1161 stopOutput | C06 | PASS |
| main.ts:1166 renderToday | Y01 | PASS |
| main.ts:1197 renderPriorityBlock | Y01 | PASS |
| main.ts:1225 renderSourcesBlock | Y02 | PASS |
| main.ts:1288 refreshMail | L02 | LEGACY |
| main.ts:1300 openDetail | Y03 | PASS |
| main.ts:1307 loadMailDetail | L03 | LEGACY |
| main.ts:1321 closeDetail | Y03 | PASS |
| main.ts:1329 renderDetail | Y03 | PASS |
| main.ts:1386 bringItemToChat | C08, Y04 | PASS |
| main.ts:1397 renderSettings | A01 | PASS |
| main.ts:1439 settingsSelectRow | A01 | PASS |
| main.ts:1463 settingsAssistantGroup | A02 | PASS |
| main.ts:1513 settingsConversationGroup | M01 | PASS |
| main.ts:1539 settingsMemoryGroup | M02 | PASS |
| main.ts:1578 memoryRow | M02 | PASS |
| main.ts:1600 addMemoryFromSettings | M03 | PASS |
| main.ts:1609 runMemoryAction | M04, M05, M06 | PASS |
| main.ts:1621 settingsPerceptionGroup | V02 | PASS |
| main.ts:1640 settingsMicrophoneRow | V01 | PASS |
| main.ts:1672 settingsToolsGroup | T01, T02 | GAP, PASS |
| main.ts:1701 settingsGroup | A01 | PASS |
| main.ts:1710 settingToggle | A01 | PASS |
| main.ts:1728 settingsExperienceGroup | D01 | PASS |
| main.ts:1755 settingsPetGroup | P01, P03, P05 | PASS |
| main.ts:1795 applyOutfit | P01 | PASS |
| main.ts:1811 applyExpression | P02 | PASS |
| main.ts:1832 capabilitySummary | D02 | PASS |
| main.ts:1849 settingsRuntimeGroup | D02, D03, D04 | PASS |
| main.ts:1883 settingsSourceGroup | D05 | PASS |
| main.ts:1903 setPetBoolean | P04 | PASS |
| main.ts:1914 runControl | D03 | PASS |
| main.ts:1919 applyPreferences | D01 | PASS |
| main.ts:1924 hideToast | C05 | PASS |
| main.ts:1932 showToast | C05 | PASS |
| types.ts:271 refreshMail | L02 | LEGACY |
| model.ts:59 text | Y03 | PASS |
| model.ts:64 sourceLabel | Y03 | PASS |
| model.ts:69 levelLabel | Y03 | PASS |
| model.ts:74 statusLabel | Y03 | PASS |
| model.ts:79 statusTone | Y03 | PASS |
| model.ts:87 formatDateLabel | Y03 | PASS |
| model.ts:99 formatFullDate | Y03 | PASS |
| model.ts:107 normalizeViewItem | L01 | LEGACY |
| model.ts:131 sectionItems | L01 | LEGACY |
| model.ts:147 uniqueItems | L01 | LEGACY |
| model.ts:157 todayItems | L01 | LEGACY |
| model.ts:167 sourceItems | L01 | LEGACY |
| model.ts:185 priorityItems | L01 | LEGACY |
| model.ts:193 sourceCount | L01 | LEGACY |
| model.ts:201 sourceStatus | L01 | LEGACY |
| schedule.ts:11 btn | Q01 | PASS |
| schedule.ts:14 shift | Q01 | PASS |
| schedule.ts:15 errorText | Q01 | PASS |
| schedule.ts:35 constructor | Q01 | PASS |
| schedule.ts:41 call | Q01 | PASS |
| schedule.ts:44 refresh | Q01, Q07 | PASS |
| schedule.ts:63 render | Q01 | PASS |
| schedule.ts:95 row | Q04 | PASS |
| schedule.ts:107 mutateState | Q04 | PASS |
| schedule.ts:111 cancel | Q04 | PASS |
| schedule.ts:116 modal | Q02 | PASS |
| schedule.ts:120 field | Q02 | PASS |
| schedule.ts:121 select | Q02 | PASS |
| schedule.ts:122 input | Q02 | PASS |
| schedule.ts:123 edit | Q02, Q03 | PASS |
| schedule.ts:161 noticeAction | Q05 | PASS |
| schedule.ts:166 editPreferences | Q06 | PASS |

## DOM events／元素／bridge calls 逐項索引

保留來源程式行；data-* markup 與 callback 皆列出。CSS 的 data selector 在下節，並非 JS event。

| Git 位置 | 實際 source reference | 契約 |
| --- | --- | --- |
| main.ts:113 | `element.addEventListener("click", onClick);` | S01 |
| main.ts:225 | `bridge.onState((state) => this.onRuntimeState(state));` | S01 |
| main.ts:226 | `bridge.onData((data) => this.onBriefingData(data));` | S01 |
| main.ts:227 | `bridge.onChatState((state) => this.onChatState(state));` | S01 |
| main.ts:235 | `&lt;div class="brand-orbit" aria-hidden="true">K&lt;span class="state-pulse" data-state-pulse>&lt;/span>&lt;/div>` | S01 |
| main.ts:242 | `&lt;button class="rail-button" type="button" data-mode="chat" aria-label="普通對話">${ICONS.chat}&lt;span class="rail-label">對話&lt;/span>&lt;/button>` | S01 |
| main.ts:243 | `&lt;button class="rail-button" type="button" data-mode="today" aria-label="今天與行事曆">${ICONS.today}&lt;span class="rail-label">今天&lt;/span>&lt;/button>` | S01 |
| main.ts:247 | `&lt;div class="presence">&lt;span class="presence-dot" data-presence-dot>&lt;/span>&lt;span class="presence-label" data-presence-label>正在確認連線&lt;/span>&lt;/div>` | S01 |
| main.ts:248 | `&lt;button class="rail-button" type="button" data-mode="settings" aria-label="設定">${ICONS.settings}&lt;span class="rail-label">設定&lt;/span>&lt;/button>` | S01 |
| main.ts:254 | `&lt;span class="chrome-title" data-chrome-title>Kuro 工作面板&lt;/span>` | S01 |
| main.ts:255 | `&lt;span class="chrome-meta" data-chrome-meta>LOCAL-FIRST&lt;/span>` | S01 |
| main.ts:258 | `&lt;div class="privacy-indicators" data-privacy-indicators aria-label="感知功能狀態">&lt;/div>` | S01 |
| main.ts:260 | `&lt;button class="window-button" type="button" data-window="minimize" aria-label="最小化">${ICONS.minimize}&lt;/button>` | S01 |
| main.ts:261 | `&lt;button class="window-button" type="button" data-window="maximize" aria-label="最大化或還原">${ICONS.maximize}&lt;/button>` | S01 |
| main.ts:262 | `&lt;button class="window-button close" type="button" data-window="close" aria-label="關閉">${ICONS.close}&lt;/button>` | S01 |
| main.ts:266 | `&lt;div class="runtime-status" data-runtime-status role="status">&lt;/div>` | S01 |
| main.ts:267 | `&lt;div class="stage" data-stage>` | S01 |
| main.ts:268 | `&lt;button class="history-scrim" type="button" data-history-scrim aria-label="關閉對話紀錄">&lt;/button>` | S01 |
| main.ts:269 | `&lt;aside class="history-drawer" data-history-drawer aria-label="對話紀錄">&lt;/aside>` | S01 |
| main.ts:270 | `&lt;main class="view-root" data-view-root>&lt;/main>` | S01 |
| main.ts:271 | `&lt;aside class="detail-drawer" data-detail-drawer aria-label="項目詳情">&lt;/aside>` | S01 |
| main.ts:273 | `&lt;div class="toast" role="status" aria-live="polite" data-toast>&lt;/div>` | S01 |
| main.ts:280 | `appRoot.querySelectorAll&lt;HTMLButtonElement>("[data-mode]").forEach((element) => {` | S01, S02 |
| main.ts:281 | `element.addEventListener("click", () => this.setMode(normalizeMode(element.dataset.mode \|\| "today")));` | S01, S02 |
| main.ts:283 | `appRoot.querySelector&lt;HTMLButtonElement>("[data-window='minimize']")` | S01, S02 |
| main.ts:284 | `?.addEventListener("click", () => bridge.minimizeWindow());` | S01, S02 |
| main.ts:285 | `appRoot.querySelector&lt;HTMLButtonElement>("[data-window='maximize']")` | S01, S02 |
| main.ts:286 | `?.addEventListener("click", () => bridge.toggleMaximizeWindow());` | S01, S02 |
| main.ts:287 | `appRoot.querySelector&lt;HTMLButtonElement>("[data-window='close']")` | S01, S02 |
| main.ts:288 | `?.addEventListener("click", () => bridge.closeWindow());` | S01, S02 |
| main.ts:289 | `appRoot.querySelector&lt;HTMLButtonElement>("[data-history-scrim]")` | S01, S02 |
| main.ts:290 | `?.addEventListener("click", () => this.setHistoryOpen(false));` | S01, S02 |
| main.ts:295 | `bridge.getState(),` | S03 |
| main.ts:296 | `bridge.getData(),` | S03 |
| main.ts:297 | `bridge.getChatState(),` | S03 |
| main.ts:298 | `bridge.getProfile(),` | S03 |
| main.ts:299 | `bridge.getMemories(),` | S03 |
| main.ts:300 | `bridge.getTools()` | S03 |
| main.ts:315 | `const result = await bridge.getHistories();` | H04 |
| main.ts:316 | `this.history = result?.ok ? result : await bridge.getChatHistory();` | H04 |
| main.ts:324 | `this.memories = await bridge.getMemories();` | M02 |
| main.ts:333 | `bridge.getState(),` | C02 |
| main.ts:334 | `bridge.getChatState(),` | C02 |
| main.ts:335 | `bridge.getProfile()` | C02 |
| main.ts:419 | `appRoot.querySelector&lt;HTMLElement>("[data-stage]")?.classList.toggle("has-history", this.historyOpen);` | H01 |
| main.ts:424 | `const drawer = appRoot.querySelector&lt;HTMLElement>("[data-history-drawer]");` | H01, H02, H08 |
| main.ts:445 | `search.addEventListener("input", () => {` | H01, H02, H08 |
| main.ts:449 | `const next = appRoot.querySelector&lt;HTMLInputElement>("[data-history-drawer] .history-search");` | H01, H02, H08 |
| main.ts:517 | `const result = await bridge.createHistory();` | H05 |
| main.ts:535 | `const result = await bridge.selectHistory(historyUid);` | H06 |
| main.ts:548 | `const result = await bridge.deleteHistory(record.uid, record.title);` | H07 |
| main.ts:564 | `const chromeTitle = appRoot.querySelector&lt;HTMLElement>("[data-chrome-title]");` | S03, V03 |
| main.ts:565 | `const chromeMeta = appRoot.querySelector&lt;HTMLElement>("[data-chrome-meta]");` | S03, V03 |
| main.ts:566 | `const presenceDot = appRoot.querySelector&lt;HTMLElement>("[data-presence-dot]");` | S03, V03 |
| main.ts:567 | `const presenceLabel = appRoot.querySelector&lt;HTMLElement>("[data-presence-label]");` | S03, V03 |
| main.ts:568 | `const statePulse = appRoot.querySelector&lt;HTMLElement>("[data-state-pulse]");` | S03, V03 |
| main.ts:569 | `const privacy = appRoot.querySelector&lt;HTMLElement>("[data-privacy-indicators]");` | S03, V03 |
| main.ts:579 | `const capabilityStatus = appRoot.querySelector&lt;HTMLElement>('[data-runtime-status]');` | S03, V03 |
| main.ts:599 | `appRoot.querySelectorAll&lt;HTMLButtonElement>("[data-mode]").forEach((element) => {` | S03, V03 |
| main.ts:614 | `const root = appRoot.querySelector&lt;HTMLElement>("[data-view-root]");` | S01 |
| main.ts:627 | `&lt;button class="history-toggle" type="button" data-history-toggle aria-label="開啟對話紀錄">${ICONS.history}&lt;/button>` | C01 |
| main.ts:629 | `&lt;h1 class="chat-title" data-chat-title>普通對話&lt;/h1>` | C01 |
| main.ts:630 | `&lt;div class="chat-subtitle" data-chat-subtitle>目前對話&lt;/div>` | C01 |
| main.ts:634 | `&lt;label class="inline-select character-select">&lt;span>角色&lt;/span>&lt;select data-character-select aria-label="目前角色">&lt;/select>&lt;/label>` | C01 |
| main.ts:635 | `&lt;span class="runtime-pill" data-chat-runtime>正在確認連線&lt;/span>` | C01 |
| main.ts:638 | `&lt;div class="chat-context" data-chat-context>` | C01 |
| main.ts:639 | `&lt;div class="chat-context-copy" data-chat-context-copy>&lt;/div>` | C01 |
| main.ts:640 | `&lt;button class="text-button" type="button" data-clear-context>清除&lt;/button>` | C01 |
| main.ts:643 | `&lt;div class="message-list" data-message-list aria-live="polite">&lt;div class="message-list-inner" data-message-inner>&lt;/div>&lt;/div>` | C01 |
| main.ts:645 | `&lt;div class="attachment-row" data-attachment-row>&lt;/div>` | C01 |
| main.ts:648 | `&lt;button class="sensor-button" type="button" data-sensor="microphone" aria-label="開啟麥克風">${ICONS.mic}&lt;span>麥克風&lt;/span>&lt;/button>` | C01 |
| main.ts:649 | `&lt;button class="sensor-button mic-submit" type="button" data-mic-action="submit" aria-label="完成並送出錄音" hidden>${ICONS.send}&lt;span>送出錄音&lt;/span>&lt;/button>` | C01 |
| main.ts:650 | `&lt;button class="sensor-button mic-cancel" type="button" data-mic-action="cancel" aria-label="取消錄音" hidden>${ICONS.cancel}&lt;span>取消&lt;/span>&lt;/button>` | C01 |
| main.ts:651 | `&lt;button class="sensor-button" type="button" data-sensor="camera" aria-label="開啟鏡頭">${ICONS.camera}&lt;span>鏡頭&lt;/span>&lt;/button>` | C01 |
| main.ts:652 | `&lt;button class="sensor-button" type="button" data-sensor="screen" aria-label="本回合擷取螢幕">${ICONS.screen}&lt;span>本回合螢幕&lt;/span>&lt;/button>` | C01 |
| main.ts:655 | `&lt;label class="inline-select">&lt;span>模型&lt;/span>&lt;select data-model-select aria-label="LLM 模型">&lt;/select>&lt;/label>` | C01 |
| main.ts:656 | `&lt;label class="inline-select">&lt;span>推理&lt;/span>&lt;select data-thinking-select aria-label="推理深度">&lt;/select>&lt;/label>` | C01 |
| main.ts:660 | `&lt;button class="composer-button" type="button" data-attach aria-label="加入附件">${ICONS.attach}&lt;/button>` | C01 |
| main.ts:661 | `&lt;textarea rows="1" data-composer-input aria-label="輸入普通對話" placeholder="問 Kuro，或從今天的項目延伸討論…">&lt;/textarea>` | C01 |
| main.ts:662 | `&lt;button class="composer-button send" type="button" data-composer-action aria-label="送出訊息">${ICONS.send}&lt;/button>` | C01 |
| main.ts:663 | `&lt;input type="file" data-file-input hidden multiple />` | C01 |
| main.ts:665 | `&lt;div class="composer-foot">&lt;span data-composer-notice>Enter 送出 · Shift + Enter 換行&lt;/span>&lt;span data-ai-state>IDLE&lt;/span>&lt;/div>` | C01 |
| main.ts:670 | `const input = root.querySelector&lt;HTMLTextAreaElement>("[data-composer-input]");` | C01 |
| main.ts:673 | `input.addEventListener("input", () => {` | C01 |
| main.ts:678 | `input.addEventListener("keydown", (event) => {` | C01 |
| main.ts:685 | `root.querySelector&lt;HTMLButtonElement>("[data-attach]")?.addEventListener("click", () => {` | C01 |
| main.ts:686 | `root.querySelector&lt;HTMLInputElement>("[data-file-input]")?.click();` | C01 |
| main.ts:688 | `root.querySelector&lt;HTMLInputElement>("[data-file-input]")?.addEventListener("change", (event) => {` | C01 |
| main.ts:692 | `root.querySelector&lt;HTMLButtonElement>("[data-composer-action]")?.addEventListener("click", () => {` | C01 |
| main.ts:697 | `root.querySelector&lt;HTMLButtonElement>("[data-clear-context]")?.addEventListener("click", () => {` | C01 |
| main.ts:701 | `root.querySelector&lt;HTMLButtonElement>("[data-history-toggle]")?.addEventListener("click", async () => {` | C01 |
| main.ts:705 | `root.querySelectorAll&lt;HTMLButtonElement>("[data-sensor]").forEach((element) => {` | C01 |
| main.ts:706 | `element.addEventListener("click", () => {` | C01 |
| main.ts:712 | `root.querySelectorAll&lt;HTMLButtonElement>("[data-mic-action]").forEach((element) => {` | C01 |
| main.ts:713 | `element.addEventListener("click", () => {` | C01 |
| main.ts:728 | `const titleElement = this.viewRoot().querySelector&lt;HTMLElement>("[data-chat-title]");` | C01 |
| main.ts:729 | `const subtitleElement = this.viewRoot().querySelector&lt;HTMLElement>("[data-chat-subtitle]");` | C01 |
| main.ts:730 | `const runtimeElement = this.viewRoot().querySelector&lt;HTMLElement>("[data-chat-runtime]");` | C01 |
| main.ts:748 | `const character = this.viewRoot().querySelector&lt;HTMLSelectElement>("[data-character-select]");` | C02 |
| main.ts:749 | `const model = this.viewRoot().querySelector&lt;HTMLSelectElement>("[data-model-select]");` | C02 |
| main.ts:750 | `const thinking = this.viewRoot().querySelector&lt;HTMLSelectElement>("[data-thinking-select]");` | C02 |
| main.ts:766 | `character.addEventListener("change", () => this.applyProfilePatch({ character_id: character.value }));` | C02 |
| main.ts:781 | `model.addEventListener("change", () => this.applyProfilePatch({ model: model.value }));` | C02 |
| main.ts:798 | `thinking.addEventListener("change", () => this.applyProfilePatch({ thinking_power: thinking.value }));` | C02 |
| main.ts:821 | `const result = await bridge.applyProfile(payload) as Record&lt;string, unknown> & {` | C02, A03 |
| main.ts:875 | `this.viewRoot().querySelectorAll&lt;HTMLButtonElement>("[data-sensor]").forEach((element) => {` | V01 |
| main.ts:895 | `this.viewRoot().querySelectorAll&lt;HTMLButtonElement>("[data-mic-action]").forEach((element) => {` | V01 |
| main.ts:913 | `const result = await bridge.control(`mic-${action}`, {});` | V01 |
| main.ts:954 | `const result = await bridge.control(action, { enabled });` | V02 |
| main.ts:992 | `const list = this.viewRoot().querySelector&lt;HTMLElement>("[data-message-list]");` | C03, C04 |
| main.ts:993 | `const inner = this.viewRoot().querySelector&lt;HTMLElement>("[data-message-inner]");` | C03, C04 |
| main.ts:1029 | `const context = this.viewRoot().querySelector&lt;HTMLElement>("[data-chat-context]");` | C08 |
| main.ts:1030 | `const copy = this.viewRoot().querySelector&lt;HTMLElement>("[data-chat-context-copy]");` | C08 |
| main.ts:1043 | `const action = this.viewRoot().querySelector&lt;HTMLButtonElement>("[data-composer-action]");` | C05 |
| main.ts:1044 | `const attach = this.viewRoot().querySelector&lt;HTMLButtonElement>("[data-attach]");` | C05 |
| main.ts:1045 | `const input = this.viewRoot().querySelector&lt;HTMLTextAreaElement>("[data-composer-input]");` | C05 |
| main.ts:1046 | `const notice = this.viewRoot().querySelector&lt;HTMLElement>("[data-composer-notice]");` | C05 |
| main.ts:1047 | `const state = this.viewRoot().querySelector&lt;HTMLElement>("[data-ai-state]");` | C05 |
| main.ts:1074 | `const notice = this.viewRoot().querySelector&lt;HTMLElement>("[data-composer-notice]");` | C05 |
| main.ts:1114 | `const row = this.viewRoot().querySelector&lt;HTMLElement>("[data-attachment-row]");` | C07 |
| main.ts:1133 | `? this.viewRoot().querySelector&lt;HTMLTextAreaElement>("[data-composer-input]")` | C05 |
| main.ts:1140 | `const result = await bridge.sendText(message, this.attachments);` | C05 |
| main.ts:1162 | `const result = await bridge.control("interrupt");` | C06 |
| main.ts:1293 | `const result = await bridge.refreshMail();` | L02 |
| main.ts:1309 | `const result = await bridge.getMailMessage(messageId);` | L03 |
| main.ts:1330 | `const stage = appRoot.querySelector&lt;HTMLElement>("[data-stage]");` | Y03 |
| main.ts:1331 | `const drawer = appRoot.querySelector&lt;HTMLElement>("[data-detail-drawer]");` | Y03 |
| main.ts:1391 | `const input = this.viewRoot().querySelector&lt;HTMLTextAreaElement>("[data-composer-input]");` | C08, Y04 |
| main.ts:1610 | `const result = await bridge.memoryAction(action, payload);` | M04, M05, M06 |
| main.ts:1797 | `const result = await bridge.control("set-outfit", {` | P01 |
| main.ts:1817 | `const result = await bridge.control("set-expression", {` | P02 |
| main.ts:1904 | `const result = await bridge.control(action, { enabled });` | P04 |
| main.ts:1915 | `const result = await bridge.control(action, payload);` | D03 |
| main.ts:1925 | `const toast = appRoot.querySelector&lt;HTMLElement>("[data-toast]");` | C05 |
| main.ts:1933 | `const toast = appRoot.querySelector&lt;HTMLElement>("[data-toast]");` | C05 |
| schedule.ts:12 | `const node=el("button",cls,label);node.type="button";node.onclick=callback;return node;` | Q01 |
| schedule.ts:42 | `try{return await this.bridge.schedule(action,payload);}catch{return {ok:false,error:"core_unavailable"};}` | Q01 |
| schedule.ts:47 | `const health=await this.call("status");` | Q01, Q07 |
| schedule.ts:53 | `if(materialize)await this.call("materialize",{through:shift(end,1)});` | Q01, Q07 |
| schedule.ts:54 | `const [result,notifications]=await Promise.all([this.call("view",{start:this.start,end,timezone:this.timezone,limit:100,offset:more?this.view.nextOffset\|\|0:0}),this.call("notifications")]);` | Q01, Q07 |
| schedule.ts:68 | `const date=el("input");date.type="date";date.value=this.start;date.setAttribute("aria-label","查看日期");date.onchange=()=>{if(date.value){this.followingToday=false;this.start=date.value;void this.refresh();}};` | Q01 |
| schedule.ts:70 | `for(const [value,label] of [[1,"單日"],[7,"七日"]] as const){const o=el("option","",label);o.value=String(value);range.append(o);}range.value=String(this.span);range.onchange=()=>{this.span=Number(range.value);void this.refresh();};` | Q01 |
| schedule.ts:108 | `const result=await this.call("mutate",{action,id:entry.scheduleId,expectedRevision:entry.revision,scope:"this",occurrenceDate:entry.occurrenceDate,confirmed:true,idempotencyKey:crypto.randomUUID()});` | Q04 |
| schedule.ts:113 | `const error=el("p","schedule-status is-error");const submit=btn("確認取消",async()=>{submit.disabled=true;const result=await this.call("mutate",{action:"cancel",id:entry.scheduleId,expectedRevision:entry.revision,scope:scope.value,...(scope.value!=="all"?{occurrenceDate:entry.occurrenceDate}:{}),confirmed:true,idempotencyKey:crypto.randomUUID()});if(!result.ok){error.textContent=errorText(result);submit.disabled=false;}else{dialog.close();await this.refresh();}});` | Q04 |
| schedule.ts:118 | `dialog.addEventListener("close",()=>{dialog.remove();if(this.dialog===dialog)this.dialog=null;});document.body.append(dialog);this.dialog=dialog;return dialog;` | Q02 |
| schedule.ts:124 | `let record=entry?await this.call("item",{id:entry.scheduleId}):null;` | Q02, Q03 |
| schedule.ts:143 | `fill(seed);scope.onchange=()=>{const master=record!.item as Item;fill(scope.value==="all"?master:{...entry!.item,recurrence:scope.value==="future"?master.recurrence:null});};` | Q02, Q03 |
| schedule.ts:144 | `allDay.onchange=()=>{const s=start.value.slice(0,10),e=end.value.slice(0,10);update();start.value=allDay.checked?s:`${s}T09:00`;end.value=allDay.checked?(e===s?shift(e,1):e):`${e}T10:00`;};` | Q02, Q03 |
| schedule.ts:145 | `kind.onchange=()=>{completion.checked=kind.value!=="event";update();};recurring.onchange=ending.onchange=notify.onchange=update;` | Q02, Q03 |
| schedule.ts:149 | `const reload=btn("重新讀取版本（保留草稿）",async()=>{if(!entry)return;const latest=await this.call("item",{id:entry.scheduleId});if(!latest.ok){error.textContent=errorText(latest);return;}record=latest;error.textContent="已讀取最新版本，草稿仍保留。請確認內容與修改範圍，再儲存。";});` | Q02, Q03 |
| schedule.ts:151 | `form.onsubmit=async(event)=>{event.preventDefault();if(save.disabled)return;save.disabled=true;error.textContent="";` | Q02, Q03 |
| schedule.ts:155 | `const prepared=await this.call("prepare",{item});if(!prepared.ok){error.textContent=errorText(prepared);save.disabled=false;return;}` | Q02, Q03 |
| schedule.ts:158 | `const result=await this.call("mutate",{...payload,idempotencyKey:pendingKey});if(!result.ok){error.textContent=errorText(result);save.disabled=false;return;}dialog.close();await this.refresh();};` | Q02, Q03 |
| schedule.ts:164 | `const result=await this.call("notification-action",{action,id:notice.id,confirmed:true,...(action==="snooze"?{until}:{})});if(!result.ok)window.alert(errorText(result));await this.refresh(false);` | Q05 |
| schedule.ts:168 | `dialog.append(this.field("啟用勿擾（面板仍保留提醒）",enabled),this.field("開始",start),this.field("結束",end),this.field("勿擾時區",tz),error,btn("儲存設定",async()=>{const result=await this.call("notification-action",{action:"preferences",confirmed:true,preferences:{quietEnabled:enabled.checked,quietStart:start.value,quietEnd:end.value,timezone:tz.value}});if(!result.ok){error.textContent=errorText(result);return;}dialog.close();await this.refresh(false);}));dialog.showModal();` | Q06 |

## WorkPanelBridge 原契約 → 現行 gateway

| 原 types.ts signature | 正式語義歸屬（不恢復原 bridge） |
| --- | --- |
| L256 `schedule(action: "status" \| "view" \| "item" \| "mutate" \| "materialize" \| "prepare" \| "notifications" \| "notification-action", payload?: Record&lt;string, unknown>): Promise&lt;Record&lt;string, unknown> & { ok: boolean; error?: string }>;` | Q01 Q02 Q03 Q04 Q05 Q06 Q07 |
| L257 `getState(): Promise&lt;RuntimeState>;` | S03 |
| L258 `getData(): Promise&lt;BriefingData>;` | Y01 L01 |
| L259 `getChatState(): Promise&lt;ChatState>;` | C09 |
| L260 `getChatHistory(): Promise&lt;ChatHistoryPayload>;` | C03 |
| L261 `getProfile(): Promise&lt;ProfileState>;` | A02 |
| L262 `applyProfile(payload: Record&lt;string, unknown>): Promise&lt;Record&lt;string, unknown>>;` | A03 |
| L263 `getHistories(historyUid?: string): Promise&lt;ChatHistoryPayload>;` | H04 |
| L264 `createHistory(): Promise&lt;ChatHistoryPayload>;` | H05 |
| L265 `selectHistory(historyUid: string): Promise&lt;ChatHistoryPayload>;` | H06 |
| L266 `deleteHistory(historyUid: string, historyTitle?: string): Promise&lt;ChatHistoryPayload>;` | H07 |
| L267 `getMemories(): Promise&lt;MemoryState>;` | M02 |
| L268 `memoryAction(action: string, payload?: Record&lt;string, unknown>): Promise&lt;MemoryState & Record&lt;string, unknown>>;` | M03 M04 M05 M06 |
| L269 `getTools(): Promise&lt;ToolPolicyState>;` | T01 T02 |
| L270 `sendText(text: string, attachments: AttachmentPayload[]): Promise&lt;Record&lt;string, unknown>>;` | C05 C07 |
| L271 `refreshMail(): Promise&lt;Record&lt;string, unknown>>;` | L02 |
| L272 `getMailMessage(messageId: string): Promise&lt;Record&lt;string, unknown>>;` | L03 |
| L273 `control(action: string, payload?: Record&lt;string, unknown>): Promise&lt;Record&lt;string, unknown>>;` | C06 V01 V02 P01 P02 P03 P04 P05 D03 D04 |
| L274 `closeWindow(): void;` | S02 |
| L275 `minimizeWindow(): void;` | S02 |
| L276 `toggleMaximizeWindow(): void;` | S02 |
| L277 `onState(callback: (state: RuntimeState) => void): () => void;` | S03 |
| L278 `onData(callback: (data: BriefingData) => void): () => void;` | Y01 |
| L279 `onChatState(callback: (state: ChatState) => void): () => void;` | C09 |

## CSS 結構逐項索引

Qt Widgets/QSS 不執行原 DOM/CSS。以下每個原 CSS rule 都留位置與對映區域；structural／interaction tests 可 PASS，像素與動畫仍 **UNVERIFIED**，不把 selector 掃描當作 fidelity 通過。Native window buttons 由 QMainWindow 提供；reduce-motion 固定啟用。

| styles.css rule | Qt 結構 | fidelity |
| --- | --- | --- |
| L1 `:root` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L22 `.local-schedule` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L23 `.schedule-toolbar, .schedule-row-actions` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L24 `.schedule-toolbar input, .schedule-toolbar select, .schedule-field input:not([type=checkbox]), .schedule-field select, .schedule-field textarea` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L25 `.schedule-toolbar input, .schedule-toolbar select` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L26 `.schedule-group` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L27 `.schedule-group h3, .schedule-group summary` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L28 `.local-schedule-row` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L29 `.schedule-row-copy` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L30 `.schedule-row-copy strong` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L31 `.schedule-row-copy span` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L32 `.schedule-row-copy small` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L33 `.schedule-row-actions` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L34 `.schedule-row-actions button` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L35 `.schedule-status` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L36 `.schedule-status.is-error` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L37 `.schedule-dialog` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L38 `.schedule-dialog::backdrop` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L39 `.schedule-dialog .block-heading` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L40 `.schedule-form` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L41 `.schedule-form fieldset, .schedule-form > .schedule-status, .schedule-form > button` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L42 `.schedule-field` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L43 `.schedule-field input[type=checkbox]` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L44 `.schedule-form fieldset` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L45 `.schedule-form-grid` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L46 `.schedule-weekdays` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L47 `.schedule-dialog [hidden]` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L48 `.schedule-reminders` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L49 `.reminder-row` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L50 `.reminder-row strong` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L51 `select:focus-visible` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L52 `@media(max-width:640px)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L52 `.local-schedule-row` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L52 `.schedule-row-actions` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L52 `.schedule-form` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L52 `.schedule-dialog` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L54 `*` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L58 `html, body, #app` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L67 `body` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L75 `button, textarea, input` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L81 `button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L85 `button:focus-visible, textarea:focus-visible, input:focus-visible` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L92 `button:disabled` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L97 `::-webkit-scrollbar` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L102 `::-webkit-scrollbar-thumb` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L107 `::-webkit-scrollbar-track` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L111 `.work-panel` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L119 `.rail` | Rail／CompanionNav | UNVERIFIED |
| L131 `.brand` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L140 `.brand-orbit` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L155 `.brand-orbit::after` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L167 `.state-pulse` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L180 `.state-pulse[data-state="thinking"], .state-pulse[data-state="processing"], .state-pulse[data-state="loading"]` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L190 `.state-pulse[data-state="speaking"], .state-pulse[data-state="listening"]` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L197 `.state-pulse[data-state="offline"]` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L201 `@keyframes state-breathe` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L202 `0%, 100%` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L203 `50%` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L206 `.brand-copy` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L210 `.brand-name` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L216 `.brand-role` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L228 `.rail-nav` | Rail／CompanionNav | UNVERIFIED |
| L234 `.rail-spacer` | Rail／CompanionNav | UNVERIFIED |
| L238 `.rail-button` | Rail／CompanionNav | UNVERIFIED |
| L257 `.rail-button:hover` | Rail／CompanionNav | UNVERIFIED |
| L262 `.rail-button.is-active` | Rail／CompanionNav | UNVERIFIED |
| L268 `.rail-button svg` | Rail／CompanionNav | UNVERIFIED |
| L276 `.rail-button.is-active svg` | Rail／CompanionNav | UNVERIFIED |
| L280 `.rail-label` | Rail／CompanionNav | UNVERIFIED |
| L288 `.rail-footer` | Rail／CompanionNav | UNVERIFIED |
| L296 `.presence` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L307 `.presence-dot` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L315 `.presence-dot.is-online` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L320 `.presence-label` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L324 `.workspace` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L332 `.chrome` | Chrome／privacy_status | UNVERIFIED |
| L345 `.chrome-context` | Chrome／privacy_status | UNVERIFIED |
| L352 `.chrome-title` | Chrome／privacy_status | UNVERIFIED |
| L360 `.chrome-meta` | Chrome／privacy_status | UNVERIFIED |
| L369 `.window-actions` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L375 `.chrome-right` | Chrome／privacy_status | UNVERIFIED |
| L383 `.privacy-indicators` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L390 `.privacy-chip` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L403 `.window-button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L414 `.window-button:hover` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L419 `.window-button.close:hover` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L424 `.window-button svg` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L432 `.stage` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L442 `.stage.has-detail` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L446 `.history-scrim` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L457 `.history-drawer` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L474 `.stage.has-history .history-scrim` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L479 `.stage.has-history .history-drawer` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L483 `.history-drawer-header` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L491 `.history-drawer-title` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L498 `.history-drawer-header p` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L505 `.history-drawer-actions` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L512 `.history-drawer-actions .primary-button` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L517 `.history-search` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L529 `.history-search:focus` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L534 `.history-list` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L540 `.history-row` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L549 `.history-row.is-active` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L554 `.history-open` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L565 `.history-open:hover, .history-delete:hover` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L570 `.history-title, .history-preview, .history-meta` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L578 `.history-title` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L584 `.history-preview` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L590 `.history-meta` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L597 `.history-delete` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L608 `.history-delete svg` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L613 `.history-empty` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L624 `.history-empty strong` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L629 `.view-root` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L636 `.view-frame` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L643 `.section-kicker` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L652 `.section-title` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L661 `.section-description` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L669 `.section-heading-row` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L677 `.mono-meta` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L683 `.primary-button, .quiet-button, .icon-button, .source-filter, .text-button` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L693 `.primary-button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L701 `.primary-button:hover` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L705 `.quiet-button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L713 `.quiet-button:hover` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L718 `.quiet-button.is-danger` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L723 `.text-button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L729 `.text-button:hover` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L734 `.empty-state` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L744 `.empty-state strong` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L751 `.detail-drawer` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L762 `.stage.has-detail .detail-drawer` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L767 `.detail-scroll` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L773 `.detail-topline` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L781 `.detail-eyebrow` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L789 `.icon-button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L798 `.icon-button:hover` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L803 `.detail-title` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L811 `.detail-meta-list` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L822 `.detail-meta-list dt` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L826 `.detail-meta-list dd` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L832 `.detail-copy` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L838 `.detail-note` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L847 `.detail-actions` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L855 `.chat-frame` | _build_chat_tab／chat header／context | UNVERIFIED |
| L863 `.chat-header` | _build_chat_tab／chat header／context | UNVERIFIED |
| L868 `.chat-heading-row` | _build_chat_tab／chat header／context | UNVERIFIED |
| L875 `.chat-title-cluster, .chat-header-actions` | _build_chat_tab／chat header／context | UNVERIFIED |
| L883 `.history-toggle` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L896 `.history-toggle:hover` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L901 `.history-toggle svg` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L906 `.history-toggle svg, .history-delete svg, .sensor-button svg` | HistoryDrawer／HistoryScrim／HistoryOpen | UNVERIFIED |
| L916 `.inline-select` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L925 `.inline-select select` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L937 `.inline-select select:focus` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L941 `.chat-title` | _build_chat_tab／chat header／context | UNVERIFIED |
| L948 `.chat-subtitle` | _build_chat_tab／chat header／context | UNVERIFIED |
| L954 `.runtime-pill, .status-pill, .level-pill` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L970 `.runtime-pill::before, .status-pill::before` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L979 `.runtime-pill.is-online::before, .status-pill.tone-good::before` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L984 `.status-pill.tone-warn::before` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L988 `.status-pill.tone-bad::before` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L992 `.chat-context` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1003 `.chat-context.is-visible` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1007 `.chat-context-copy` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1013 `.chat-context-copy strong` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1017 `.message-list` | TranscriptBox／transcript_html | UNVERIFIED |
| L1024 `.message-list-inner` | TranscriptBox／transcript_html | UNVERIFIED |
| L1029 `.message` | TranscriptBox／transcript_html | UNVERIFIED |
| L1037 `.message:first-child` | TranscriptBox／transcript_html | UNVERIFIED |
| L1041 `.message-role` | TranscriptBox／transcript_html | UNVERIFIED |
| L1049 `.message.is-assistant .message-role` | TranscriptBox／transcript_html | UNVERIFIED |
| L1053 `.message.is-event .message-role` | TranscriptBox／transcript_html | UNVERIFIED |
| L1057 `.message-copy` | TranscriptBox／transcript_html | UNVERIFIED |
| L1066 `.message.is-user .message-copy` | TranscriptBox／transcript_html | UNVERIFIED |
| L1070 `.message-time` | TranscriptBox／transcript_html | UNVERIFIED |
| L1077 `.typing-line` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1084 `.typing-line i` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1092 `.typing-line i:nth-child(2)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1096 `.typing-line i:nth-child(3)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1100 `@keyframes thinking` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1101 `0%, 100%` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1102 `50%` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1105 `.chat-empty` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1112 `.chat-empty-mark` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1124 `.chat-empty h2` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1130 `.chat-empty p` | _build_chat_tab／chat header／context | UNVERIFIED |
| L1137 `.composer-wrap` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1142 `.conversation-controls` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1150 `.sensor-controls, .response-controls` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1158 `.sensor-button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1172 `.sensor-button:hover` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1177 `.sensor-button.is-on` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1183 `.sensor-button.is-paused` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1189 `.sensor-button.mic-submit` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1195 `.sensor-button.mic-cancel` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1199 `.sensor-button:disabled` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1204 `.sensor-button svg` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1209 `.sensor-button[hidden]` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1213 `.attachment-row` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1221 `.attachment-row:empty` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1225 `.attachment-chip` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1237 `.attachment-chip span` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1243 `.attachment-chip button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1250 `.composer` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1261 `.composer:focus-within` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1265 `.composer-button` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1277 `.composer-button:hover` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1282 `.composer-button.send` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1287 `.composer-button.stop` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1292 `.composer-button svg` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1300 `.composer textarea` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1313 `.composer textarea::placeholder` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1317 `.composer-foot` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1326 `.composer-notice.is-error` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L1331 `.today-frame` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1335 `.today-question` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1344 `.today-question em` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1349 `.today-summary` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1358 `.today-summary strong` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1364 `.today-primary` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1371 `.block-heading` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1382 `.block-heading h2` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1389 `.block-heading span` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1395 `.priority-list` | TodayPage.priority | UNVERIFIED |
| L1399 `.priority-item` | TodayPage.priority | UNVERIFIED |
| L1414 `.priority-item::before` | TodayPage.priority | UNVERIFIED |
| L1424 `.priority-item:hover::before, .priority-item.is-selected::before` | TodayPage.priority | UNVERIFIED |
| L1429 `.priority-source` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1437 `.priority-title` | TodayPage.priority | UNVERIFIED |
| L1443 `.priority-meta` | TodayPage.priority | UNVERIFIED |
| L1449 `.level-pill` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1456 `.level-pill.level-urgent, .level-pill.level-must` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1462 `.level-pill.level-focus, .level-pill.level-watch` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1468 `.schedule` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1474 `.schedule::before` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1484 `.schedule-item` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1496 `.schedule-item::before` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1508 `.schedule-time` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1514 `.schedule-title` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1521 `.schedule-meta` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1527 `.schedule-empty` | SchedulePage／ScheduleEditor | UNVERIFIED |
| L1534 `.sources-block` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1538 `.source-filters` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1545 `.source-filter` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1555 `.source-filter:hover` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1559 `.source-filter.is-active` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1564 `.source-filter small` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1571 `.source-status-line` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1583 `.source-status-copy` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1590 `.source-list` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1597 `.source-item` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1611 `.source-item:hover .source-item-title` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1615 `.source-item-title` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1621 `.source-item-meta` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1627 `.source-item-arrow` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L1633 `.settings-grid` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1640 `.settings-column` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1646 `.settings-group` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1650 `.settings-group-header` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1658 `.settings-group-header h2` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1664 `.settings-group-header span` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1669 `.setting-row` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1678 `.setting-copy strong` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1684 `.setting-copy span` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1692 `.switch` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1703 `.switch::after` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1715 `.switch.is-on` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1719 `.switch.is-on::after` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1724 `.diagnostic-list` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1728 `.diagnostic-row` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1737 `.diagnostic-row dt` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1741 `.diagnostic-row dd` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1751 `.settings-actions` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1758 `.settings-shell` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1765 `.settings-nav` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1771 `.settings-nav-item` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1784 `.settings-nav-item strong` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1790 `.settings-nav-item span` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1795 `.settings-nav-item:hover` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1799 `.settings-nav-item.is-active` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1805 `.settings-nav-item.is-active strong` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1809 `.settings-content` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1816 `.setting-row-select` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1820 `.settings-select` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1832 `.settings-select:focus` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1836 `.settings-select:disabled` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1840 `.settings-note` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L1849 `.microphone-setting-row` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1853 `.microphone-setting-actions` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1861 `.memory-add` | memory_list／memory_detail | UNVERIFIED |
| L1870 `.memory-input` | memory_list／memory_detail | UNVERIFIED |
| L1883 `.memory-input:focus` | memory_list／memory_detail | UNVERIFIED |
| L1887 `.memory-list, .tool-list` | memory_list／memory_detail | UNVERIFIED |
| L1892 `.memory-row, .tool-row` | memory_list／memory_detail | UNVERIFIED |
| L1898 `.memory-row-top, .memory-actions, .tool-row` | memory_list／memory_detail | UNVERIFIED |
| L1906 `.memory-row-top, .tool-row` | memory_list／memory_detail | UNVERIFIED |
| L1911 `.memory-meta` | memory_list／memory_detail | UNVERIFIED |
| L1917 `.memory-content` | memory_list／memory_detail | UNVERIFIED |
| L1925 `.memory-actions` | memory_list／memory_detail | UNVERIFIED |
| L1930 `.text-button.is-danger` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1934 `.tool-policy-summary` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1943 `.tool-policy-summary strong` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1948 `.tool-policy-summary span, .tool-copy span` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1955 `.tool-copy` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1961 `.tool-copy strong` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L1966 `.toast` | native QMessageBox／status labels | UNVERIFIED |
| L1984 `.toast.is-visible` | native QMessageBox／status labels | UNVERIFIED |
| L1989 `.toast.is-error` | native QMessageBox／status labels | UNVERIFIED |
| L1994 `.is-compact .priority-item, .is-compact .source-item, .is-compact .setting-row` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L2002 `.is-compact .message` | TranscriptBox／transcript_html | UNVERIFIED |
| L2006 `.reduce-motion *, .reduce-motion *::before, .reduce-motion *::after` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2015 `@media (max-width: 1080px)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2016 `:root` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2021 `.rail` | Rail／CompanionNav | UNVERIFIED |
| L2026 `.brand` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2032 `.brand-copy, .rail-label, .presence-label` | Rail／CompanionNav | UNVERIFIED |
| L2038 `.rail-button` | Rail／CompanionNav | UNVERIFIED |
| L2044 `.presence` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2049 `.view-frame` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2054 `.today-primary` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2058 `.source-list` | TodayPage.sources／CoreHealthPage | UNVERIFIED |
| L2062 `.settings-shell` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L2067 `.chat-header-actions .character-select span, .conversation-controls .inline-select span` | _build_chat_tab／chat header／context | UNVERIFIED |
| L2073 `@media (max-width: 900px)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2074 `.stage, .stage.has-detail` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L2079 `.detail-drawer` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L2092 `.stage.has-detail .detail-drawer` | TodayPage.detail／SchedulePage.detail | UNVERIFIED |
| L2096 `.today-primary, .settings-grid` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L2101 `.today-primary` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2105 `.settings-shell` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L2110 `.settings-nav` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L2116 `.settings-nav-item` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L2122 `.settings-nav-item.is-active` | SettingsSurface／SettingsNav／_settings_row | UNVERIFIED |
| L2126 `.chat-heading-row, .conversation-controls` | _build_chat_tab／chat header／context | UNVERIFIED |
| L2132 `.chat-header-actions, .conversation-controls, .sensor-controls, .response-controls` | _build_chat_tab／chat header／context | UNVERIFIED |
| L2139 `.inline-select` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2143 `.inline-select select` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2149 `@media (max-width: 650px)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2150 `.privacy-chip` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2160 `.view-frame, .chat-header` | _build_chat_tab／chat header／context | UNVERIFIED |
| L2166 `.composer-wrap` | ComposerPanel／ComposerEdit／AttachmentTray | UNVERIFIED |
| L2170 `.sensor-button span` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2174 `.sensor-button` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2180 `.setting-row-select, .memory-add, .microphone-setting-row` | memory_list／memory_detail | UNVERIFIED |
| L2186 `.microphone-setting-actions` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2192 `@media (max-height: 650px)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2193 `.rail` | Rail／CompanionNav | UNVERIFIED |
| L2197 `.brand` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2201 `.rail-button` | Rail／CompanionNav | UNVERIFIED |
| L2205 `.view-frame` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2209 `.chat-header` | _build_chat_tab／chat header／context | UNVERIFIED |
| L2214 `.message-list` | TranscriptBox／transcript_html | UNVERIFIED |
| L2220 `@media (prefers-reduced-motion: reduce)` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2221 `*, *::before, *::after` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2231 `.runtime-status` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2232 `.runtime-status[hidden]` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |
| L2233 `.workspace > .stage` | qt_work_companion_theme TOKENS／QSS／native Qt controls | UNVERIFIED |

## 明確未恢復／驗證邊界

- 無新 provider 或 owner：Mail 手動刷新／郵件內文、Study 課程跳轉保持不可用。Mail/Study 的來源狀態仍顯示 Core 真實 disabled/unavailable/partial 值，不一律捏造成正常或停用。
- 工具確認隊列／政策寫入未有 canonical owner；保持 blocked／disabled。政策檔可讀不代表 running runtime 已採用。
- 舊 Memory 1200 字 UI 與目前 260 字 owner 不相容；明示 260 字並保留超長草稿。
- History 最近 120 則的 canonical timeline 已包含工具事件（舊 Git qt_controller.py:517 亦 limit=120）；前後均未提供更早分頁，現會顯示上限。兩個 history 檔案刪除不是 atomic，錯誤訊息明示不確定結果。
- Chat role/model 選單集中 Settings，Chat 有直達入口；Today 詳情是同頁 panel。這是單一 Qt 結構對映，不能稱 Web DOM 像素原封移植。
- 125%／200% Qt offscreen、temp WS/HTTP/DB 與 fixture 是 source 證據。真實 IME、Windows GPU／tray／多螢幕、Live2D、Mic/camera/screen、model/voice、個人資料及原截圖 fidelity 全部 UNVERIFIED。
- 一次 source cutover 只有 WorkCompanionView；V1 synthetic model／preview 程式已退役。正式執行中的舊 Qt 未被重啟，需使用者之後實機驗收。
