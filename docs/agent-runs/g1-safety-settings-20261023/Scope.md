# G1 安全接線與正式 Settings

基準：main / c53f2f0d59c44c63e2120785beb989231de3e558，初始 clean。
G0 receipt：`.tmp/g0-safety-runtime-20261023T172235/G0Status.json`。
本輪證據：`.tmp/g1-safety-settings-20261023/`。

## 授權範圍與驗收

1. 修正 Bridge stop/profile/toggle/restart/close：只停止 held ManagedProc，外來 listener 不可 taskkill；以 mock 正負案例證明。
2. 沿用唯一 Qt Web/Launcher/Core owner，提供獨立主動語音與 Settings > Tools OMI 政策；嚴格驗證、確認寫入、持久化、後端消費及真實 inactive 狀態。
3. 預設主動語音及 OMI 觀測關閉；G1 不執行排程觀測，即使偏好已儲存也不得聲稱生效。
4. 盤點 Mail read/detail、Pet presentation、附件 caps；僅接 canonical contract，其餘明確 fail-closed 並列 Debt。
5. 保護六份 immutable Git original renderer；只改 owner adapter/presentation overlay，經定點驗證後使用既有 content-addressed 簽章流程更新 pin，保留舊 bundle。

## 禁止事項

不啟動正式 Kuro、停止中央 Voice、碰正式 DB/個人資料、刷新 provider、消耗付費 LLM、修改其他 repo/MCP/OMI、commit/push。
使用者最後指示本輪封存 G1 後結束。G2 下一 turn 實作：日文 Study Hub、英文 Study Hub、OMI、Mail 四個獨立只讀正式 Integration、Core Observation／Today 有界投影，以及 Source Contract／Freshness／Offline／Policy 接線。G2 不是 G1 額外測試，也不是 G6 主動語音。
遇 Windows sandbox 初始化或 ACL 拒絕即停止，不變更權限或改 executor/shell 繞過。

## 執行順序

- 先以 G0 負向案例鎖定 P1，再做最小 owner-fenced 修正及 targeted regression。
- 檢查既有 Settings/owner/persistence/consumer contract，接入正式讀寫與 truthful capability。
- 使用 task-local synthetic fixtures 驗證保存/讀回/拒絕/失敗與前端 transport；無穩定 contract 留 Debt。
- 最後驗 immutable originals、候選 bundle、簽章、pin 與 diff，保存 Scope/Diff/Tests/交接。

G1 Source isolated PASS、Native UNVERIFIED 分別回報。四個來源的 G2 工程留待下一 turn，本輪不宣稱已交付 G2。
