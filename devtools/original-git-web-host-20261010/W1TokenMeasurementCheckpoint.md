# W1 CSS token 量測修正 — 2026-10-10

**局部修正與離線驗證 PASS；修正後 Qt smoke／完整 W1：UNVERIFIED；W2–W7：NOT STARTED。**

## 本次實際證據

已唯讀檢查使用者正常 Windows session 的 [.runtime/w1-smoke-20261010-145401-183/chat.json](.runtime/w1-smoke-20261010-145401-183/chat.json)：Qt 6.11.1、host status PASS、offTheRecord=true、platform=windows、bridgeRequests=11、viewport 1280×720／DPR 1、fonts loaded、rail width 78、chrome height 50、composer 820×60；但 `geometry.tokens={}`。

該次 `SmokeResult.json` 如實記錄 `ValidationError: Original visual tokens differ`、exit 1；Settings 尚未執行。這是 token 量測／驗證失敗，不應倒推 Qt import 或 host readiness 失敗。舊 PNG、JSON、logs 全部保留，不改寫 FAIL receipt，也不將 host PASS 升格成 W1 PASS。

## 最小修正

- `geometry.js`：將 `Array.from(getComputedStyle(...))` 的 custom-property discovery 換成明確列舉原版 `:root` 的 **16** 個名字，再逐名執行 `getPropertyValue(name).trim()`。
- 包含原版全部顏色、rail/detail/chrome 尺寸及兩個 font tokens。只固定名字，**值仍取自 rendered page**；沒有填入 fallback、CSS 預設值或改寫 computed style。缺失 token 保留空字串，既有 validator 繼續拒絕。
- 原實作假設 CSSStyleDeclaration iterator 會列出 custom properties；Node mock 重現「iterator 空，但逐名可解析」的差異。新版可處理此量測缺口；仍須下一次 Qt 實測確認 Qt 回傳值。
- 六份原始 Git source、Qt host、frontend UI、preview protocol、`w1_smoke.py`、`capture_parity.py` 與安全設定均未修改。

## 變更與驗證

本輪只修改 `geometry.js`、`test_w1_smoke.py`，新增 `test_geometry.cjs` 與本 checkpoint；證據位於 [.runtime/w1-token-measurement-fix/](.runtime/w1-token-measurement-fix/)。Typecheck／build 只使用既有工具、輸出既有 task frontend/dist，無套件安裝或正式 renderer-dist 變更。

- `node --check geometry.js`、`node --check test_geometry.cjs`：exit 0。
- `node test_geometry.cjs`：exit 0。Node built-ins only，無第三方 npm dependency、browser 或 Qt；驗證 empty iterator 仍讀到全部 16 個 root tokens、computed override 保留、missing token 得到空字串。
- `test_w1_smoke`：8 項通過；新增跨語言回歸把真正 geometry.js 的 mock 測量結果送進未修改的 Python validator，完整 tokens 通過，缺少 `--iris` 仍以原本 ValidationError 拒絕。這些 mock 不代表 Qt runtime 證據。
- 既有 TypeScript `tsc --project tsconfig.json --noEmit`、Vite `build --config vite.config.mjs`：均 exit 0。
- source／index／WIP 及舊 evidence 完整性：見本次 `before.json`、`after.json`、`preservation-before.json` 與 `Result.json`。

本輪不重試 Codex sandbox 的 Qt／PIL／Playwright import，不啟動真實 Qt／browser，不改 ACL、正式 env、provider、Kuro／Core／Pet；沒有 stage／commit／push。

## 正常 PowerShell 重跑

`geometry.js` 屬於 smoke sourceFingerprint；舊 receipt 不可沿用。請使用全新的目錄：

```powershell
Set-Location C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010
$run = Join-Path $PWD ('.runtime\w1-smoke-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
& .\.venv\Scripts\python.exe -B .\w1_smoke.py --output $run
if ($LASTEXITCODE -ne 0) { throw "Smoke 未通過；請檢查 $run\SmokeResult.json" }
```

此命令會先核對 source／imports／build，再執行 Chat、Settings。成功後仍須 screenshot reviewer 與後續 parity；不開始 W2。
