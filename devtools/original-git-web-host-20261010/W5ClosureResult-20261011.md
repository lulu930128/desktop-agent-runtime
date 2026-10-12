# W5 結果：隔離收斂 checkpoint；停在人工檢查

依 [Gate 計畫](W1W5ClosurePlan-20261011.md)，W4 source/disposable tests 通過後進入。Core `/v1/today` 保持唯一 order/workId/freshness/timestamps/limitations；candidate build resolver 用 canonical-model，pinned model.ts 不改也不成第二套 priority owner。

實測來源：`.runtime/w1-w5-closure-20261011T072319Z/w5-validation/Results.json`，notification commands9、schedule core19、notifications10、API6、runtime9、R3 parity6、G8 guard3，全 exit0。G8 僅 source guard，沒有做 W7 桌面採用。W4/disposable/frontend suites 另驗 36 Today permutation×freshness×complete cases、cache context invalidation；36 是同一 test 內 cases，不另加成36 tests。

- disposable Core HTTP＋schema v3 SQLite：GET/status/view/notifications、POST prepare、取消 mutation、Web materialize 拒絕前後 DB bytes 相同；不啟動 scheduler。
- mutate：expectedRevision/idempotency/Qt native confirm contract、重送不新增 item/receipt、stale/conflict 拒絕；未知 mutation 不重送。
- notifications：QtScheduleDelivery 唯一 claim→authorize→ack；Web 只有 bounded dismiss/snooze/preferences＋revision/key/confirm。並行同命令、claim contention、lease、unknown、不重播皆測試；tray 是 fixture，沒有真 OS 通知。
- Mail body/refresh、Study jump、ToolPolicy mutation、不完整 lifecycle contract 保持 GAP，不恢復 provider/legacy fallback。

24方法的 owner、transport、read/write、freshness/context、side effects、audit 與 source/native proof，見 [當次清單](W1W5ClosureMethods-20261011.md)。

W5 native 檢查入口（與 W3 共用原版候選，關閉 W3 後再開）：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Open-NativeCandidate.ps1' -Checkpoint W5
```

本輪 GUI 仍未跑過 import，native evidence 採 `native-W3` 同一硬阻塞，不以重試製造不同 Gate 的假證據。可測 source 與 disposable owner 全部完成；原生 UI、IME、security negative 與人工接受仍 UNVERIFIED，W1 strict FAIL 保留。詳 [原生檢查](NativeCandidateReview-20261011.md)。

最終保全見 `FinalAudit.json`：六檔 original Git SHA、G7 35 absent、index/staged diff、既有每個路徑 SHA、exact scoped patch/preimages。正式 launcher/VBS/Widgets/G8 guard source 未修改。rollback 是維持 candidate OFF；本次局部修正僅按 FinalAudit＋preimage 回退，不覆蓋後續 WIP/DB。

**停止於 W5 人工檢查；W6/W7 未開始。** W6 的下一個資格仍需 W1 人工接受與 native W2–W5 證據、owner exclusive handoff 審查及另行授權。本輪不是產品或 release acceptance。
