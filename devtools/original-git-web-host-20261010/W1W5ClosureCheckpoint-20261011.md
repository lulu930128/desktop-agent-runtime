# W1–W5 收斂交付：停在 W5 人工檢查

本輪完成已授權的候選 source/disposable 工作與原生接力入口；**W1 strict FAIL 保留，W2–W5 native UNVERIFIED，沒有產品／release acceptance。W6/W7 未開始。** 正式 launcher/VBS/Widgets 保留，candidate default-off。

| Gate | 目標及本輪結果 | 原生／人工 | 詳細 receipt |
| --- | --- | --- | --- |
| W1 | 最新24 pairs retained；tokens24/24相同；geometry6/8、0/8、0/8；Today/DPI差異分類完成 | strict FAIL；IME/focus/security/human UNVERIFIED | [W1](W1ClosureResult-20261011.md) |
| W2 | 原Host/Bridge保留；GUI-thread guard、關閉保護、bounded transient prefs；source PASS | 真scheme/channel/bootstrap等候正常Windows relay | [W2](W2ClosureResult-20261011.md) |
| W3 | 同一Qt client的真disposable WS；原生候選runner與可見UI啟動命令備妥；source PASS | 本輪import被拒，沒有已顯示GUI/PNG主張 | [W3](W3ClosureResult-20261011.md) |
| W4 | Memory disconnected/history-ready分離guard＋快照撤銷；canonical JSON/SQLite及相關負例PASS | native modal/裝置/profile restart UNVERIFIED | [W4](W4ClosureResult-20261011.md) |
| W5 | Core Today/Schedule/通知單owner，HTTP/schema v3/read-no-write/replay/concurrency PASS；缺contract維持GAP | Qt視覺/真OS notification等UNVERIFIED；停W5 | [W5](W5ClosureResult-20261011.md) |

[逐Gate計畫](W1W5ClosurePlan-20261011.md) 在程式修改前建立，含目標、owner、程式位置、entry/exit、負例及rollback。[24-method清單](W1W5ClosureMethods-20261011.md) 記錄read/write/freshness/side effect/audit與source/native分界。[原生人工步驟](NativeCandidateReview-20261011.md) 提供可開啟候選及尚未實測項目。

## 本輪變更

- `qt_web_host.py`：owner GUI thread檢查、idempotent shutdown、fixture metadata audit、Web Storage限制。未新增正式client/tray/notifier。
- `qt_web_adapter.py`：Memory讀寫要求connected及history_ready皆True，失效撤銷reviewed snapshot，重連必須重讀。
- `owner-bootstrap.ts`＋新增`owner-preferences.ts`：原六檔不改；main import前安裝五種合法展示偏好的memory相容層，secret/token/PII不得存入。關閉重開即消失；不讀寫原Qt QSettings、不開persistent Web profile。
- `candidate_native.py`、`candidate_fixture_service.py`、`Open-NativeCandidate.ps1`：隔離Qt WebEngine original UI入口、bounded self-owned service與證據。真Core/Memory owners只操作disposable root；Pet/lifecycle unavailable。共用`web_candidate_fixtures.py`的synthetic WS，沒有第二份正式business實作。
- 相關tests／validation selector／audit helper／本輪計畫及receipts。完整檔案與SHA以FinalAudit為準。

## 實測與證據

證據根：`.runtime/w1-w5-closure-20261011T072319Z/`。

- `ValidationSummary.json`：最新每suite **179 tests／17 suites全部PASS**，另typecheck/candidate-build exit0。重跑與36 Today property cases不重複加總。精確argv/cwd/elapsed/exit/count與log在各validation子目錄。
- `w4-reviewer/Results.json`：Reviewer補充後11＋41＋4＝56 tests通過。`w4-preimage-final.log` 的2個測試／5 subcase failures在舊adapter重現；現在通過。
- `native-import.json`／`native-import.process.json`：真PermissionError13／exit2。`native-W3/NativeResult.json`／`native-error.log`：同一native hard blocker；沒有啟GUI或sidecar。安全source路線已繼續至W5。
- `W1NativeEvidence.json`：最新24-pair原始JSON/PNG hashes；W1 executable fingerprint不變。完整fingerprint的差異只在W2 owner bootstrap/prefs，舊smoke不可用來證明新candidate。
- `Before.json`／`Before.diff`／`Index.diff`／`preimages/`：修改前main HEAD、442 dirty paths、1293路徑SHA/absence、exact preimages。`FinalAudit.json`／`FinalAudit.patch`：本輪局部差異、index/staged diff與無關WIP保全、原六SHA及G7 35 absent。
- `Syntax.json`／`PowerShellSyntax.json`／`DeliveryChecks.json`：Python in-memory compile、PowerShell AST、UTF-8／連結／scoped diff讀回。

中間的sidecar測試路徑錯誤與TS target API錯誤保留在歷史logs，已修正重跑；最新全部PASS。沒有以delete/recreate或security bypass處理環境。

## W5 可開啟的檢查入口

在正常使用者互動式PowerShell執行：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Open-NativeCandidate.ps1' -Checkpoint W5
```

原版Chat／History／Settings／Today／Schedule在同一candidate，SYNTHETIC title；預設15分鐘，X關閉自身視窗/WS/Core sidecar，不改正式服務。僅輸入synthetic內容，附件使用output內的`SYNTHETIC-attachment.txt`。若仍PermissionError，保存native-error即可；不提升權限、不關GPU/sandbox、不改ACL/registry、不重裝。

尚缺：新candidate真QWebEngine bootstrap/storage相容層、完整native安全負例、IME/focus、人工視覺與真device/profile/OS notification。W6下一資格需補這些證據、接受W1實測差異及另行授權；source PASS或BOOTSTRAP_OBSERVED不能代替。

## 保全與回滾

正式程式沒有採用candidate，因此現有Widgets就是保護路徑。回退本輪candidate修正前，先比對FinalAudit postimage SHA與目前檔案，只對照preimage逐hunk處理；若有後續WIP即停下比對，不能整庫reset/clean/checkout/stash。新helpers與receipts不需要為正式功能恢復而刪除。未commit/push、未讀私人history/mail/Memory或呼叫provider/LLM/OMI/broker、未改系統安全或正式依賴。

**本輪停止於W5人工檢查。**
