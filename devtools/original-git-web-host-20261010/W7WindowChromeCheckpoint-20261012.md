# W7 Windows Qt 單一視窗 chrome checkpoint

本輪限定 `C:\project\desktop-agent-runtime`。起始 `main@74b372f9c48a16c7deb129faf835970b6b1c2a05`、worktree clean。這是新 W7 source／bundle 版本；不承接舊 W6 native PASS，不代表正式程序已載入。未 commit／push／tag，未重啟正式服務、改私人 profile 或降低 sandbox／GPU／OS 安全設定。

## 目標、邊界與實作

1. Web 分支在 show 前設定 `Qt.FramelessWindowHint`；不呼叫 `menuBar()`。唯一標題列仍是原 Git HTML `.chrome`，其 minimize／maximize／close 三按鈕不改。Widgets 分支保留原生外框、Kuro menu 與原有 builder。
2. tray 增加 Restart Kuro，接既有 `_confirm_restart_launcher`，確認後才走原 restart；Show／Quit、X→tray／reveal 與同一 Controller／chat client 保留。
3. `owner-presentation.ts` 在 trusted mouse 左鍵 pointerdown 判定非互動 header，經同一 OwnerTransport → RequestBroker → QtOwnerAdapter → GUI-thread Port → 同一 QMainWindow 的 `windowHandle().startSystemMove()`。不使用 CSS 假拖移，也沒有 geometry polling、第二 GUI 或 manager。
4. 縮放區是 viewport 最外側 6 CSS px，四邊與四角明確 allowlist；排除按鈕、表單、可編輯區、Privacy、window-actions。rail 內部不拖移；rail 最外側空白邊緣仍是明確 resize 區。前端採 CSS px，Qt／Chromium 處理實際縮放，不自行乘 DPR。
5. 初始視窗狀態未知時禁止 resize，`getWindowState` 與 Qt WindowStateChange event 同步狀態；native 端再次拒絕 maximized resize、fullscreen／minimized／hidden、modal dialog、非單一左鍵、缺 handle 與非法 edge。OS 拒絕時回傳錯誤且不重試。
6. native move 可能吞掉 mouseup／DOM dblclick，因此以第二次 header pointerdown、Qt 系統 doubleClickInterval／startDragDistance 判定 maximize／restore。blur 清除上次點擊。此接線已測，真正 Windows 滑鼠手勢仍待實測。
7. 六份 ORIGINALS 一個 byte 都不改；只改正式 adapters／Qt bridge。CSP、navigation denial、asset allowlist、identity／permission fences 不降低。

Qt API 依據：[QWindow startSystemMove／startSystemResize](https://doc.qt.io/qt-6/qwindow.html#startSystemMove)。API 回傳支援不等同 Win11 Snap／DPI 實測成功。

## 執行計畫與進度

- 已完成：規則／QualityBar／產品方向、canonical source 與 builder inspection；保存 1,309 tracked files 起始 SHA 與修改檔 preimages。
- 已完成：Web frameless、tray、gesture protocol／adapter／Port、前端 hit tests 與 Qt offscreen regression。
- 已完成：官方 builder build → verify → `VerifiedOwnerBundle.load` 新舊包 → 更新 source pin。
- 已完成：兩輪隔離 native lifecycle；renderer exit 49，停止重試且不降安全設定。
- 已完成：完整 `w7-window-chrome` profile 28/28 exit 0、334 tests；隔離檔案 roundtrip 通過。正式 runtime／native 手勢仍未驗收。

## 精確 pin 與資產

| 欄位 | W6 舊 pin（保留） | W7 新 pin |
| --- | --- | --- |
| fingerprint | `dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e` | `8ba8ea29313601f944f760b901410efb8fc92bc801199d3b0b72ba22b7fa9b14` |
| manifest SHA256 | `c2920dff0455acfdbee2fcb9ae0a0f42cd1aa6c9d6b1690d54da5e377b765bed` | `425eff86d0426df19aa16e5142658f12f95504955037d623a16ebd633a230630` |
| Ed25519 public key | `0155b171027785abc70b0afcbba2e746fc49c7fb06b2cff705844acb2ca5da7b` | `10733638989cee0420da1ba31b550d192dca6f91676d25524e079c40b77cb5f5` |
| signature | `868e58bc3c994baf9f8d6d6e7661af4d8c01b479c9f925e9c2e2ad93e1b71d31bef33ef848153e8b8a49b161869566395c469491b6cb62fba8d98715bbd18b04` | `c6aa35146177156cc7ef03aa2a1a9535e60c5f58a23a72ca612cd38faeada2fc5027ad287cd644e93e981c1746812bfe81636d791c17c1ba9303883d8e89e208` |
| qt_web_release.py SHA256 | `bf91caa1f6945b69fd366e05fc73199281d977324e17b14b1c589e12388261eb` | `5ba89d3ee1ee860e71ea135072c949a180f55ec0392054575e0561b1c4208e2a` |

兩包位於 `assets/qt-owner/<fingerprint>`，均保留為 ignored generated assets，不 force-add。新包含 4 個資產；正式入口 `prepare_owner_presentation` 在 QApplication 前以固定 pin 載入、驗章與驗 hash。部署缺包／簽章不符會 fail closed，沒有舊包 fallback。這輪 builder 成功並驗證後才改 pin；失敗時沒有改 pin 的分支。

證據根目錄：`.runtime/w7-window-chrome-20261012/`。

- [Before.json](.runtime/w7-window-chrome-20261012/Before.json)：起始 HEAD／status／tracked byte hashes。
- [Build.json](.runtime/w7-window-chrome-20261012/Build.json)：官方 builder `STAGING_VERIFIED`。
- [PinVerificationBeforeUpdate.json](.runtime/w7-window-chrome-20261012/PinVerificationBeforeUpdate.json)：更新前新舊包皆經 `VerifiedOwnerBundle.load`。
- [w7_window_chrome_gate.py](w7_window_chrome_gate.py)：獨立 W7 exact source gate，11 份來源 SHA＋當前 builder lineage／六份 ORIGINALS／簽章 pin；source 或 pin 漂移必須拒絕。`W7_SOURCE_PIN_VERIFIED` 永遠不授予 native PASS。
- [SourcePinGate.json](.runtime/w7-window-chrome-20261012/SourcePinGate.json)：最終 source／builder／VerifiedOwnerBundle 驗證結果。
- [ChangeHashes.json](.runtime/w7-window-chrome-20261012/ChangeHashes.json)：12 份修改檔的 exact pre/post SHA；[Integrity.json](.runtime/w7-window-chrome-20261012/Integrity.json) 記錄最終變更 allowlist 與未涉及檔案保全。

相容整組 Web runtime 的 exact SHA 如下；這 **7 份必須一起回復**，不可只回復 pin。其餘 5 份測試／validator 修改也在 ChangeHashes 中，隔離 roundtrip 一併驗證。

| 檔案 | W6 起始 SHA256 | W7 SHA256 |
| --- | --- | --- |
| `kuro_launcher/qt_app.py` | `8d882d0563d44993606a414ef8114e4bb49da55adfcd34d293debb25aaaee4fe` | `ff6d7ad5894647df4fc25097931afa8126b8ce10ceb9f18f2e5f650397cf3096` |
| `kuro_launcher/qt_web_host.py` | `eb88f04d5ac0c6b1cca0384eb2fa95621014a0599b3ce5acc3c54004180304a4` | `c012de7ee9c5afa3baf31b0fee1c73ce9776f6dc28d6e3ef976b1810599ecac9` |
| `kuro_launcher/qt_web_adapter.py` | `38e52a5acc1f823fc031049ee6f3631c48babedb1a61910f03e8b38a1373b491` | `3811bca7d741e247b380580f1847851863ec4a56786adbbc9959423774a739ad` |
| `kuro_launcher/qt_web_protocol.py` | `1ed6042b6786f743287dcf9fd1b83fa61b19286f3e60517d796dcd220bfcd27c` | `4850ecc3b291b6a186451cc59cadde5cc355c268fde21849afb1cc26e5143c82` |
| `kuro_launcher/qt_web_release.py` | `bf91caa1f6945b69fd366e05fc73199281d977324e17b14b1c589e12388261eb` | `5ba89d3ee1ee860e71ea135072c949a180f55ec0392054575e0561b1c4208e2a` |
| `frontend/src/owner-bridge.ts` | `01ca938c2922033b21a638187558171d397dce614a0b3d762258c90ad5e60e3e` | `3761b9a9ebc14652230116062d779f9fb15c420a41853604f34504418118d874` |
| `frontend/src/owner-presentation.ts` | `a9433b5353f1e1bcbb7b828a13b3f6f63d9d78fd345842c5b8796eed5ad27a3f` | `cd6aed78af2d5b36c327e12abee3cdb32b9a4f6f69c598391201f32f6ef4b52a` |

表中 frontend 路徑相對於本 checkpoint 所在目錄。

## 驗證範圍與歷史證據

正式 W7 source regression 使用 `w7-window-chrome` profile，集合精確等於原 `RELEASE_SUITES - {qt_web_release_candidate} + {qt_web_window_chrome}`；禁止 `--only`，缺 suite 即 fail。原 `release-candidate` 保留 W6 語意，不包含 W7 suite，對目前 source 仍應失敗。

- 初輪 [regression/Results.json](.runtime/w7-window-chrome-20261012/regression/Results.json)：保留所有原始失敗。
- `qt_web_release_candidate`：10 tests，2 failures／4 errors。原因為 W7 Qt source 與 release pin 不符 W6 exact SHA；**LEGACY_ONLY／EXPECTED_SOURCE_DRIFT**，不可計入 W7 PASS。`w6_release_candidate.py` 的 PREIMAGE_SHA／ADOPTED_SHA、舊 raw receipts、原測試檔均不改。W7 自己測試 `release_preimage()` 必須拒絕目前版本。
- G5：初輪 17 tests／1 failure 僅為新增 Restart 的 action list；更新刻意新增的項目與 Quit index 後 17/17 PASS。真實功能沒有因測試而改。
- G8：初輪只因寫死 W6 fingerprint 失敗；改驗固定 source pin 對應的 VerifiedOwnerBundle，所有 no-legacy 邊界 assertions 保留，3/3 PASS。
- Qt W7：目前 8 tests，包括真實 Web constructor（WebEngine surface inert）、無框／無 QMenuBar、Widgets tray/menu、restart 確認取消／接受、X／reveal／quit、八邊 Qt.Edge mapping、maximized／按鍵 guard、identity／duplicate fences、source/pin gate 與 profile 不可省略。
- Node：20/20 PASS，包括既有三按鈕 bridge、八邊角／invalid geometry、trusted mouse、header 雙擊、Privacy／表單／rail exclusion；typecheck PASS。
- Widgets 截圖測試只重導 `test_r2_settings_parity`、`test_r3_today_schedule_parity` 的 output-only ROOT 到本次 artifacts；不跳過 assertion、不覆寫歷史 screenshots。Scope.json 明列重導。

完整 profile **28/28 exit 0、334 tests PASS**，包含 Node typecheck。runner OS exit 0；[Results.json](.runtime/w7-window-chrome-20261012/full-profile/Results.json)、[Scope.json](.runtime/w7-window-chrome-20261012/full-profile/Scope.json) 與 [FinalValidation.json](.runtime/w7-window-chrome-20261012/FinalValidation.json) 可逐項核對。這是 **W7_SOURCE_SCOPE_PASS**；測試使用 disposable／synthetic IO，不代表正式服務、資料或 native renderer 驗收。

## 隔離 native：完成時 final receipts

使用既有 `run_w6_existing_window.py`，輸出到全新 W7 evidence 目錄。此為 W6 harness 重用，raw contract 的 `w7Started=false` 是 harness 原欄位，不能據此描述本次任務版本，也沒有重寫 raw 欄位。

[native/RelayResult.json](.runtime/w7-window-chrome-20261012/native/RelayResult.json) 的 final 結果：

| 輪次 | PID | actual exit | reported exit | renderer |
| --- | --- | --- | --- | --- |
| first | 22120 | 2 | 2 | exit 49，loadFinished=false |
| restarted | 51908 | 2 | 2 | exit 49，loadFinished=false |

`restartObserved=true`。兩輪均以 Windows native platform 顯示同一 KuroQtLauncherWindow，通過單一 native owner count、X→tray、second launch activation、reveal、restart 邊界、late-results silent、idempotent cleanup、chat thread stopped／quit；first 額外驗證 byte-identical relaunch helper，restarted 驗證 parent 已退出。兩輪 `sourceUnchangedDuringRun=true`，實際程序均已退出。

renderer 在 JavaScript callback 前失敗，overall **BLOCKED**，fresh native security axes **NOT_REACHED**。HTML header 實際拖移／resize／doubleclick、Win11 Snap、最大化 hover snap layout、不同 DPI／跨螢幕與正式 cold-start pack 均 **UNVERIFIED**。沒有以 mocked native call、offscreen geometry 或舊 W6 74/74 冒充新 W7 native PASS；不再重試 exit 49，不關 sandbox／GPU。

## Reviewer 重現指令

以下只驗證 source／隔離 tests，不啟動正式服務。profile output 必須是新目錄。

```powershell
Set-Location 'C:\project\desktop-agent-runtime'
.\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\w7_window_chrome_gate.py
.\envs\kuro-llm310\python.exe -I -B .\devtools\original-git-web-host-20261010\build_owner_bundle.py --verify --output .\devtools\original-git-web-host-20261010\.runtime\w7-review-build.json
.\envs\kuro-llm310\python.exe -B .\devtools\original-git-web-host-20261010\validate_candidate.py --profile w7-window-chrome --output .\devtools\original-git-web-host-20261010\.runtime\w7-review-profile
git diff --check
```

## 精確回滾與後續人工 gate

本輪不執行正式回滾／cold start。以下由使用者另行選擇時進行：

1. 如正式 Kuro 正在執行，先透過既有 Quit 正常退出，確認 owner 已退出；不可 broad kill，也不可藉 source 修改宣稱 loaded-runtime 已回滾。
2. 以本次 `Before.json` 與最終 `Integrity.json` 核對每個目標：目前 bytes 必須等於 W7 new SHA，`preimages/<path>` 必須等於 old SHA；有任何較新 WIP／hash 不符即停止。
3. 回到完整舊 Web source checkpoint：依 exact allowlist 還原本輪修改的 12 個 tracked files 的 preimages。不要 reset／checkout／清理 bundle。W7 新 gate／test／checkpoint 可留作版本史；它們不會被正式 launcher import，但舊 source 下 W7 gate 預期拒絕。
4. 原先帶框 Web UI 的精確 old pin 如上表；舊包已驗證並保留。只換 old pin 而保留新的 frameless Qt 會失去 gesture adapter，**不可作為完整 Web rollback**。
5. 緊急 Widgets fallback **需另行授權**：在既有 Qt source 保留 Widgets 路徑下，將唯一 source adoption assignment `RELEASE_PIN = OwnerBundlePin(...)` 明確改成 `RELEASE_PIN = None`，不刪包、不動 profile／私人設定；下次啟動才選 Widgets。這不是完整 Web rollback，不是 W7 PASS，也不自動回寫或熱切換現存程序。
6. 回滾後重新驗證 old bundle 與 source SHA，再由使用者正常啟動；正式 loaded pack／視窗與 native 手勢仍需新的實機證據。

已完成安全隔離 roundtrip：[RollbackRoundtrip.json](.runtime/w7-window-chrome-20261012/RollbackRoundtrip.json)。只在新建 `.runtime/w7-window-chrome-20261012/rollback-mirror/` 做 **12 檔 W7 → W6 → W7** byte roundtrip，各階段驗證所有 exact SHA、Python compile、該階段 source pin 對應的簽章 bundle；正式 checkout bytes 不變，沒有 process actions、沒有執行 Widgets fallback。這是檔案回復演練，不是 native rollback acceptance。

後續人工驗收需在正常 Windows session：關閉舊 Kuro 後正常啟動，確認唯一 HTML chrome／三按鈕、tray 三項、同一 owner／WS，再測 header 拖移、八邊角、雙擊、maximized resize 拒絕、Privacy／表單／rail 內部、Snap、125%／150% DPI 及跨螢幕。這輪不自動執行。
