# W1–W3 本機檢查點 — 2026-10-11

本輪停在 **W1 真實環境阻塞**。W1 歷史視覺 FAIL 保留；W2、W3 未進行新的 native gate 實測，也未進入 W4–W7。正式 UI、VBS、launcher、使用者設定、原六份 renderer 與 feature-off candidate 均未修改。沒有 commit/push、ACL 變更、套件安裝、production restart 或 private DB/History/Memory/provider 操作。

## Gate 裁決

| Gate | 本輪狀態 | 實際證據與限制 |
| --- | --- | --- |
| W1 | **FAIL 保留；重驗 BLOCKED** | task `.venv` 的 WebChannel/WebEngineWidgets、PIL、playwright import 全部 PermissionError 13。一般與 require_escalated 皆失敗，後者明確 exit 2；未進 DLL/GPU/render。1280×720、1380×860 × scale 1/1.25/2 × 四頁共 24 組本輪未執行。 |
| W2 | **UNVERIFIED／受 W1 阻塞** | custom scheme、CSP、QWebChannel、off-record、navigation/download/permission 及 worker GUI thread native proof 本輪未執行。不用歷史 source tests 冒充通過。 |
| W3 | **UNVERIFIED／未開始本輪接線實測** | 同一 WebEngine candidate + QtRuntimeChatClient + disposable WS 完整 UI 流程未執行。歷史 272 tests 不列為本輪 PASS。 |

Today +3px/native date：歷史 `parity-msedge-1-20261010T071240461324Z/ParityResult.json` 與 `W1TodayParityCheckpoint.md` 仍指出上游 header/line box 位移與 date intrinsic width 待釐清；Edge154/Qt Chromium140 是已記錄環境差異，不是可接受性判決。沒有新的深層 DOM/font/native input measurement，因此沒有宣稱已確認或修復唯一根因，也沒有改 margin、input type 或 threshold。

## 本輪驗證

完整 argv、cwd、exit、case count：本目錄 `.runtime/w1-w3-review-20261011T051809Z/validation/Results.json`、`PreviewValidation.json`。

- `validate_candidate.py --output .../validation --only typecheck original-build parity_collection parity_diagnosis w1_smoke deep_comparison test_geometry test_deep_geometry`：exit 0；typecheck/build 各 exit 0；六 suites 分別 6/3/8/3/1/2，共 **23 tests** PASS。這些是採證 helper/synthetic tests，不是真實 WebEngine smoke。
- `node --test preview_bridge.test.cjs`：exit 0，3 tests；`envs/kuro-llm310/python.exe -B -m unittest test_preview_protocol -v`：exit 0，4 tests。驗證 fixture reads、mutators fail closed、identity/revision/duplicate/malformed guards。
- 合計 **8 suites / 30 tests**，加 typecheck/build；未測 W4/W5。
- 新 PowerShell 腳本 AST parse、UTF-8 讀回、局部 diff whitespace 檢查；實際互動 Windows 啟動仍待一般使用者身分驗證。

## 預覽實測與可見性

本輪 build 的唯讀 synthetic preview：`http://127.0.0.1:4179/work-panel.html?view=chat`。Node PID **53976**、loopback LISTENING 與 HTTP 200 已觀察；最終存活狀態見 `FinalAudit.json`。這不是 Qt acceptance，也不是 production Chat。

瀏覽器控制工具兩次失敗，第二次回報 `Restricted read-only access requires the elevated Windows sandbox backend`。直接啟動獨立 profile Edge 的 PID **49192** 曾存在，後來已退出；沒有可見 window handle。stderr 記錄 GPU process exit `-1073741790`，最後 `GPU process isn't usable. Goodbye.`。没有關閉 sandbox/GPU。故 **不能聲稱使用者畫面已開啟，本輪 Chat/Settings/History/Today 新截圖均無法取得**。

初次 PowerShell `Start-Process` 被 PATH/Path 重複環境 key 阻塞；改用 Python `subprocess.Popen` 後僅 server 成功，沒有用此替代方式繞過 Qt/package ACL。

在一般 Windows PowerShell 執行一鍵預覽（不需系統管理員，不改 execution policy）：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Open-ReadOnlyBrowserPreview.ps1'
```

腳本驗證 Git 六檔、check/build，選新 loopback port，啟動 task-owned Vite 與獨立 Edge profile，開 Chat/Settings/Today，保存 PID/URL/HTTP 後的 launch receipt；History 從 Chat 抽屜查看。沒有視窗 handle 時明示 UNVERIFIED。檢查完先關隔離 Edge，再回 PowerShell 按 Enter，僅停止該次建立的 server。新 profile/evidence 保留，不清理使用者資料。

人工檢查項：

1. Chat 的 78px rail、50px chrome、青綠色 tokens、composer 和控制列是否為已確認原版。
2. Settings 六分類切換與內容排列；不套用 profile/Memory/工具設定。
3. Chat History 抽屜開關、搜尋 synthetic fixture；CRUD 不應真的執行。
4. Today/Schedule 的垂直間距、日期欄位寬度與縮放後是否溢出；browser 單端觀察不解除 Qt +3px FAIL。
5. 送出、附件、Mail、Schedule mutation 等應拒絕／unavailable；不得出現正式歷史或 provider 資料。

W1 measurement 重跑沿用 `Invoke-W1WindowsRelay.ps1`；它仍只涵蓋既有 harness，缺少 dedicated History pair/native interaction/security 不會自動變成完整 W1 PASS。

## 保全、變更與 rollback

- HEAD / branch：`af83df273602be3a616d6567855ea71d61a9ace7` / `main`。
- 起始 WIP **428 路徑：64 M / 34 D / 330 untracked**；`Before.json` 保存 1245 份現存非 ignored source/WIP SHA、六來源 SHA、index SHA、完整 status；`Before.diff` 保存局部既有 diff。這不是 private/runtime 全量備份。
- 原始六檔與 `995c23c7c8d1be62000229d58610d2214f3bb745` bytes 全部吻合；G7 **35/35** 原路徑不存在，正式入口沒有引用 `qt_web_host`。
- 新增可追蹤檔僅本 checkpoint 與 `Open-ReadOnlyBrowserPreview.ps1`。另有 ignored `.runtime/w1-w3-review-20261011T051809Z/` 新證據、獨立 Edge profile，以及重建的 ignored `frontend/dist`；沒有修改舊 evidence。
- `FinalAudit.json` 列出本輪所有新檔 SHA、原 source/WIP/index 前後比較、listener/HTTP 與 browser 狀態。不產生新 commit SHA。
- rollback：正式 Qt Widgets fallback 原樣保留；本輪沒有 production adoption 可回滾。若要移除新增腳本/文件，先比對 `FinalAudit.json` 的 SHA 後僅處理這兩檔，不能全庫 reset/clean/stash/checkout。預覽 server 停止前須重驗 PID、路徑與 listener，避免 PID reuse；不以程序名稱批次終止。

**停止點：W1 blocker／使用者預覽檢查點。未開始 W4。**
