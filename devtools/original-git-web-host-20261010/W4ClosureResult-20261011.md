# W4 結果：source/disposable PASS；native UNVERIFIED

依 [Gate 計畫](W1W5ClosurePlan-20261011.md)，原版六 Settings 分類保持 DOM/CSS；profile/controller/effective WS、Memory canonical manager、ToolPolicy read-only、Pet gateway/Qt capture submit 各 owner 不換。進入時 W3 launchable source checkpoint 已完成；GUI 硬阻塞只限制 native 路線。

本輪修正 `QtOwnerAdapter.prepare`：Memory 讀／寫都明確要求 `chat.connected is True AND chat.history_ready is True`；任一不成立即清除 `memory_snapshot`，在任何 owner IO 或 native confirm 前拒絕。即使 real Qt client 通常同時清除 identity，仍保留防禦性 guard。

新增獨立負例：connected=False/history_ready=True；connected=True/history_ready=False；兩者皆False。先 getMemories 或先 memoryAction 都撤銷已審核快照；重連而沒有重新讀取時，mutation 仍回 `read_memory_before_confirming`。controller 無 IO、confirm 無呼叫；不是只把兩個旗標一起清掉的測試。

最新 `w4-reviewer/Results.json`：`qt_web_w4_w5` **11**、`qt_web_candidate` **41**、`qt_web_disposable` **4**，全部 exit0；`w4-validation` 的 R2 **16** exit0。preimage 兩個新增測試在 `w4-preimage-final.log` 重現 **5 failures／exit1**，現在通過；沒有覆寫 worktree 來回退重現。

其餘負例已實測：Memory 260字/digest/actor/confirm取消/並行內容保全；失敗 refresh 撤銷快照；profile 新context與 effective WS；capture missing、inner ok=False、不明結果／actor swap；ToolPolicy 失敗不 discovery／升權；Pet 拒絕不能寫入 outfit 或送到 Conversation。JSON＋derived SQLite 只在 disposable root。新可見 fixture 的真 Memory IO 沿用原 controller/manager。

展示偏好決議見 [W2](W2ClosureResult-20261011.md)：只有五種 bounded transient values，重開消失；沒有 private/authoritative state 或第二個持久 owner。此項與原 Qt QSettings 互不寫入；沒有以非受控 Web profile 換取持久化。

native Settings 操作、Memory modal、真 profile restart、Pet 硬體/感知仍 UNVERIFIED。可見 fixture 對 Pet/lifecycle 明確 unavailable，**不回 mock-success**；真 profile/device 驗收不在本次 private-free fixture 中假造。回滾只涉及 adapter 本次 guard 與測試，依 preimage/FinalAudit，正式 Memory/設定未修改。
