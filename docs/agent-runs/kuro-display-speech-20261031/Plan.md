# 修正計畫

1. 保存既有 WIP bytes／index 與 task preimages；跑 Qt、Speech、frontend 基線。用匿名 fixture 重現換行與雙排、missing Speech 靜音。
2. 先修 adapter 的 display_append 與 full-text 語意，檢查釘選 renderer 的 async history／相同回合文字／reconnect。必要時才修 frontend Source，Release 留 BLOCKED。
3. response prompt 對齊既有 v2 parser 與 private lane prompt。評估 missing-only、ja-JP、完整長技術清單的固定提示；malformed、拒絕與 partial 不得被 fallback 蓋過。
4. 執行定點 tests／typecheck／隔離 build，核對 pin 與已簽資產不變，交付 task-only diff、精確計數與未驗證範圍。

任何 unrelated WIP／index 變更先停止處理；不以更改 immutable source 規則或 pin 繞過 Release 阻塞。測試失敗先定位，不把 source mock 通過說成 runtime 採用。
