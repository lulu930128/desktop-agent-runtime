# Gate 計畫

| Gate | 可驗證成果 | 驗證與停止條件 |
| --- | --- | --- |
| R0 | HEAD／3baf057 精確 inventory、parity matrix、DOM/CSS 證據及不能對映項目 | Git object hashes、所有 functions／events／CSS selectors 掃描；不得把 gold 描述當成 Git 證據 |
| R1 | 真實 History CRUD／搜尋／選取／active、確認／pending／error、工具 timeline、Chat | 建構／WS 路由原有 regression 先通過；再跑 owner、fence、重複／過期回應與 Qt fixture 測試 |
| R2 | 六類 Settings、Profile／Memory／Policy／capture／Pet | confirmation、profile binding、owner allowlist、不可用理由 |
| R3 | Core Today priority／sources／details、selection stable、Schedule | 僅 Core projection、revision／idempotency／prepare／confirmation，temp HTTP tests |
| R4 | 單一正式 Qt 組裝與 deterministic source cutover | 全主線相關回歸、offscreen screenshots、G7 35 absent、WIP integrity；真人桌面仍 UNVERIFIED |

## 執行規則

每個 Gate 的 checkpoint 彙整於 `Progress.md`。未通過不宣稱完成；P1 先修復，再繼續接線。所有實際啟動、停止、重啟與真人操作留給使用者。source 回退必須依 `Baseline.json` 和本次 delta 驗證，只回退本次改動，不覆寫其他人的新工作。`Rollback.md` 明列 G3 test-only before-bytes 缺口，不宣稱整個 worktree 可精確回退。
