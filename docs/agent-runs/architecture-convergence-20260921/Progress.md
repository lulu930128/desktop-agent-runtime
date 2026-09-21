# 整合進度

## 狀態

2026-09-21：本 repo 架構收斂、研究隔離規範與來源 baseline 完成。正式 runtime／研究環境不在本輪完成宣稱內。

## 已核對與決策

- 起點 `94065af5cfbaa3b5acbd5e7e19417a803cdaa122`，`main` 與本機 `origin/main` 相同；10 個既有 TTS 檔案保留並獨立整合。
- `ScheduleServer` 是 production service；`KuroCore` 應用層只見 tests 建構，Observation／Decision 不持有正式 Today。
- Core schema v3 同時包含 observation／trace 與 schedule／notification；共享初始化是 production dependency。保留單庫／imports，明確記錄 migration、backup、restore 與剩餘耦合。
- Electron Briefing／Today／mail／study 仍是 legacy primary；已記錄四個 owner 的 read/write、保存、target 與 parity／cutover 條件。
- 中央模式 Launcher 只 probe readiness，舊文件的 startup synthesis 敘述已修正；Central Voice 保持外部 owner。
- 固定 Windows mutex／activation event、Electron userData、繼承 env 與絕對路徑都可能跨 worktree 共用；research contract 明示尚無完整隔離 profile。
- Briefing memory candidate status 只更新 snapshot，不直接保存到 runtime memory；已修正舊圖將兩者相連的誤導。

## 驗證證據

- `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p 'test_central_voice*.py' -v`：21 PASS。
- `envs/kuro-llm310/python.exe -B -m unittest discover -s tests -p 'test_runtime_capabilities.py' -v`：8 PASS；兩組無 skipped。
- TTS 3 source＋2 tests `py_compile`：PASS。
- `npm run check:renderer`：PASS；`npm run build:renderer`：首次 sandbox `spawn EPERM`，核准範圍重跑 PASS；保留既有 Live2D script 非 module 警告。
- 全部 27 個候選檔 strict UTF-8／replacement character／conflict marker／whitespace 檢查通過；18 份 Markdown 的本機連結存在性與 code fence 檢查通過。
- `kuro_core/__init__.py`、`storage.py` 與前一 checkpoint 的 AST 去 docstring 後完全相同；無可執行行為或 schema 改動。
- `git diff --check`／staged diff check 通過；每批 exact path manifest 與 credential／private artifact audit。
- [SourceBaseline.json](SourceBaseline.json) 的 14 個 SHA-256、11 個 tree OID、policy v1 configured digest 以 Git checkpoint 重算驗證；hash 使用 committed blob bytes，避免 CRLF 差異。
- 文件／註解變更依 Tier 0 未跑 Core／MCP 全套、GUI 或 runtime smoke。SourceBaseline 的 security matrix 連結保存歷史驗證範圍，不把未執行的測試標為本次 PASS。

## 提交與驗收界線

- `27df8aa`：`fix(voice): handle shared TTS readiness and recovery`，10 個檔案，無 private state。
- `bde3444`：`docs(architecture): reconcile Core ownership and research boundaries`，13 個檔案，包含 README／AGENTS／導覽、六個架構主題與 Core 註解。
- 第三筆 `docs(research): record architecture source baseline and evidence`：本任務三份 Markdown、SourceBaseline 與研究文件連結；可由 `git log -- docs/agent-runs/architecture-convergence-20260921` 追溯。
- 未重新驗證正式 runtime／provider／桌面，未重啟 Kuro 或 Central Voice；2026-09-12 Schedule 與 2026-09-13 TTS live evidence 只作歷史引用。
- 未搬 DB／schema、未做 Electron cutover、未建立研究 worktree，未 push。MCP M0 A8 與完整語音人工驗收維持未完成。

## 附件範圍對照

| 附件階段 | 本輪結果 |
| --- | --- |
| 0 dirty isolation | TTS 獨立 checkpoint，未 reset／覆寫其他工作 |
| 1–3 inventory／文件／logical split | owner、process、read/write、資料流、production／shadow 分別落在持續維護文件；imports 不搬動 |
| 4 persistence | 採方案 A：單 DB＋明確 schema／migration ownership；保留共享 bootstrap 耦合與 restore 限制，不宣稱實體拆庫 |
| 5 Electron audit | 四個 legacy primary 模組與 target／parity／cutover／rollback 條件已列出；沒有新 parallel implementation |
| 6 research boundary | 隔離規範、source baseline、policy 與 schema digest 區分、experiment metadata contract 完成 |
| 7 external workspace | 使用者明確延後；沒有建立研究集中區、worktree、DB 或執行實驗 |

後續實驗應從已記錄 commit 建立獨立環境並驗證隔離；正式採用 TTS 時另核對載入版本、角色切換、播放與人工聽感。
