# W1 結果：strict FAIL；人工/native 互動 UNVERIFIED

目標、owner、位置、進入／結束條件與回滾以 [Gate 計畫](W1W5ClosurePlan-20261011.md#w1native視覺) 為準。進入基線已核對：六份 Git original bytes、最新 24 pairs、11 個 W1 executable helpers fingerprint。

本輪重新讀取 `.runtime/w1-windows-relay-20261011T0636350178563Z/`：smoke PASS；Chat/Settings/History/Today × 兩尺寸 × 三 DPR **24 pairs 完整**。幾何 raw equality：DPR1 **6/8**，1.25 **0/8**，2 **0/8**；deepGeometry 各 **6/8**；tokens 各 **8/8**。三份 ParityResult 原始 verdict 全是 FAIL，沒有改寫。SHA、逐 pair 指標及 provenance 見 `.runtime/w1-w5-closure-20261011T072319Z/W1NativeEvidence.json`。

| 尚未接受項 | 實測／原因分類 | 嚴重度與 reviewer 判準 |
| --- | --- | --- |
| Today kicker／下游 +3px | 100% Edge `10月11日星期日` 高12，Qt `10月11日 星期日` 高15；第一個分歧 line box 已定位，字串在 Intl 輸出不同 | 結構幾何 FAIL；ICU/CLDR 或實際 fallback glyph font 尚非唯一已證根因。人工核對字型、字距、控制項可讀性及下游位移 |
| date intrinsic width | 100% Edge151／Qt139；125% border1／0.8px | native 控制項 layout 差異，非 kicker 衍生；需人工開 date picker、鍵盤操作／裁切驗收，不改 type/width/CSS 遮掩 |
| 125% fractional layout | raw geometry 不等，device-grid 特徵與 quantization 相容，border/input 也不同 | 不能全歸為浮點尾數；人工核對焦點框、文字溢出、互動命中；raw strict FAIL 保留 |
| 200% | 最新 post-show bounded resize 已量到完整720/860 viewport；仍有分數 layout／Today 差異 | 舊711 viewport 問題不再套用最新資料，但不是全 Gate PASS |
| History | 最新兩尺寸三 DPR 有真的 drawer intersection／settled 測量 | 仍需 native mouse/tab/focus；JS click 不是 IME 或人工證據 |

本次 W1 preview host、pinned DOM/CSS、preview build 未改。完整 smoke fingerprint 的兩個差異僅 `owner-bootstrap.ts`／新增 `owner-preferences.ts`（W2 candidate）；它們不在 W1 preview 執行圖。**不以舊 smoke 授權新的 W2 candidate**；既有 smoke reuse guard 不放寬。

本輪 `native-import.process.json` exit2；`native-import.json` 是實際 `PermissionError: [Errno 13] ... PySide6/__init__.py`，PIL/playwright 也被拒。未到 Qt DLL/GPU/render，不改 ACL、sandbox、GPU 或依賴。native focus/IME、資源／導航／下載／權限、native date picker 未新增實證。

安全接力（正常互動式 Windows PowerShell）：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Invoke-W1WindowsRelay.ps1'
```

該 relay 保存新 matrix，不覆寫原測量。W2 custom scheme/Bridge 另用 [原生候選說明](NativeCandidateReview-20261011.md)。本 Gate 結束於「分類及 source integrity 完成，W1 FAIL／人工 UNVERIFIED」，不等待数学上的零像素誤差、不阻擋 W2–W5 隔離 source。沒有 W1 修改需回滾；歷史 receipts 原样保留。
