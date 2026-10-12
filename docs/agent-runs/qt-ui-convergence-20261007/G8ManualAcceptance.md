# G8 人工驗收與可重跑步驟

> **2026-10-10 現況：G7 35/35 實體刪除已 PASS，無須再執行本文件下方歷史『兩檔／十檔補刪』命令。** 應先執行 [G7 最終驗收](G7PostDeleteAcceptance-20261010.md) 中的 read-only `-VerifyOnly` 與完整 Python／Node／Renderer source regression，然後進行本頁的真實桌面項目。此前 Electron hidden smoke FAIL，正式 release 仍 NOT ACCEPTED。

目前 release verdict：**NOT ACCEPTED**。本文件是待執行 checklist；未填實測證據的項目全部為 **UNVERIFIED**。不把 unit/offscreen/synthetic 或 build 成功當實機 PASS。

## 安全前提

正式啟動會依使用者設定讀取本機資料、建立既有 runtime state。本輪沒有執行；請由使用者在允許此項操作後手動驗收。保持 Mail/Study disabled，勿為展示啟用 Gmail/OAuth 或 refresh provider。不要修改 logon、startup shortcut、registry、ACL；不要 reset DB、清 userData、全機 kill。Central Voice :18890 不在本 checklist 的控制範圍。

## 可直接重跑的隔離 source checks

從 repo root 執行：

```powershell
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group python
.\envs\kuro-llm310\python.exe -B tests/run_qt_convergence.py --group node
npm.cmd --prefix pet-electron run check:renderer
npm.cmd --prefix pet-electron run build:renderer
git -c core.safecrlf=false diff --check
```

Python runner 使用 disposable TEMP/TMP、offscreen、synthetic inputs，禁止連 shared/live ports。Core child 測試用臨時 DB/port，沒有正式 DB migration。Node suite 不會自動執行 manual model/device smokes。

隱藏 Electron fixture 使用真正 main/preload/renderer，所有 show/focus method 在 fixture 攔截、沒有 model descriptor／provider，仍不等同正式桌面。Windows PowerShell 直接 `& electron.exe` 可能不等待，請用以下能取得 child exit 的命令：

```powershell
@'
from pathlib import Path
import os, subprocess, tempfile
root = Path.cwd()
with tempfile.TemporaryDirectory(prefix=".validation-temp-electron-", dir=root) as tmp:
    env = os.environ.copy()
    env.update(TEMP=tmp, TMP=tmp)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    result = subprocess.run(
        [str(root/"pet-electron/node_modules/electron/dist/electron.exe"),
         str(root/"tests/g8_hidden_electron_smoke.cjs")],
        cwd=root, env=env, timeout=35, startupinfo=startup,
        creationflags=subprocess.CREATE_NO_WINDOW)
    print("electron_exit=", result.returncode)
'@ | .\envs\kuro-llm310\python.exe -B -
```

本輪此 smoke 的實際 exit=2147483651；renderer launch-failed 49、GPU -1073741515。尚未定位完整 OS/dependency 原因；勿自行降低 sandbox、改 ACL 或把它改成 PASS。

## G7 補刪 blocker

**2026-10-10 現況：33/35／BLOCKED。** 最後兩檔各一次原權限刪除仍收到 `UnauthorizedAccessException (0x80070005)`，磁碟仍存在；完整證據見 [本輪結果](../../../G7FinalTwoResults-20261010.json)。歷史十檔迴圈已撤下，現在只允許原 manifest 的 `pet-electron/src/briefing-window.html` 與 `pet-electron/src/briefing-preload.js`。

使用一般使用者 PowerShell：

```powershell
Set-Location -LiteralPath 'C:\project\desktop-agent-runtime'
.\G7FinalTwoDelete-20261010.ps1
```

腳本先核對固定 repo、所有父目錄無 reparse、完整 manifest SHA、備份 archive SHA／CRC／35 個 ZIP entry SHA、兩檔 disk SHA，以及 323 個 production source/config/build 檔的 bytes 與 inventory 未變；全部通過才以不帶 `-Force` 的精確 `Remove-Item` 刪除。若 source 已變、檔案重新出現或 denied 就停止，不修改 ACL／owner／屬性、不改名、不刪資料夾、不升權。可先用 `-VerifyOnly` 做完全唯讀檢查。

刪除後腳本會驗證 manifest **35/35 全不存在**；接著依 [本輪交接](../../../G7FinalTwoHandoff-20261010.md) 重跑原 Python／Node／MCP／renderer／syntax／diff，記錄新證據再更新 checkpoint。不能只改舊 JSON 的 deleted，也不能把 source PASS 當正式桌面 ACCEPTED。保留 ignored `g7-source-rollback.zip.bak`；禁止重套歷史 `G8FinalizationDocs.patch`。

## 正式桌面逐項驗收

| 項目 | 操作 | 接受條件／目前狀態 |
| --- | --- | --- |
| Cold boot | 從 repo root 執行 `wscript.exe .\桌寵啟動器.vbs` | Qt 首次可見、無 WorkPanel/Reader/Briefing；UNVERIFIED |
| Second launch | 再執行同一 VBS | 喚回同一 Qt/PID，沒有第二 Qt/tray/poller；UNVERIFIED |
| X/tray/reveal | 按 X，再點 Qt tray | X 只 hide，reveal 可回主畫面；無 tray 時不消失；UNVERIFIED |
| startup_auto_start=false | 使用者先備份 source settings，手動設 false，啟動後還原 | Qt 可見、不自動啟動 profile；offscreen PASS、實機 UNVERIFIED |
| Qt pages | Chat/Today/Schedule/Settings/History/Memory/Diagnostics 逐頁開啟 | 無舊 UI alias、資料與失敗語意可辨；UNVERIFIED |
| Chat 無 Pet | 使用既有 Qt 控制隱藏／關閉自有 Pet，送一則無私人內容的文字 | Qt primary 能對話，沒有第二 session；使用者自行承擔已授權的 LLM 用量；UNVERIFIED |
| Pet presentation | 開 Pet，測 motion/expression/拖曳/縮放/跨螢幕／重載 | 一個 Pet window；model ready/visible 與 shell online 分開；UNVERIFIED |
| Input | 使用者明確開啟 camera/screen/mic，使用無私人內容的測試來源 | Qt 發送、Pet 不觸發對話；切換 history 後舊 capture 丟棄；UNVERIFIED |
| Audio/lipsync | 僅在使用者已授權音訊／模型操作時測播放、中斷與結束 | 真正播完才 ack；Qt 不偽造 ack；本輪未呼叫中央 Voice，UNVERIFIED |
| Today disabled | 保持現有 Mail/Study disabled | 顯示 disabled/missing/限制，不能把空白說成無待辦；UNVERIFIED |
| Today configured missing | 只用隔離 fixture：G8/Core tests | 已自動 PASS；正式配置不改、不捏造 actionable items |
| Schedule 通知 | 使用者明確同意後建立可辨識測試排程與通知，測完透過 UI 取消 | Core claim-authorize → 單次 Qt 顯示 → ack；OS 實際可見/quiet/crash 行為 UNVERIFIED |
| Quit/restart | Qt 明確 Quit，再由 VBS 啟動；另測 Qt restart | 自有 child 收斂、未知 listener 不 kill、18890 untouched；UNVERIFIED |
| Crash/restart | 記錄並核對測試 child PID/instance/root 後，只對該 child 模擬 crash | 不重播 uncertain delivery，不產雙 poller／owner；正式 UNVERIFIED |
| Logon/startup | 僅觀察既有 OS 行為 | 未授權改 shortcut/registry；UNVERIFIED |

唯讀檢查只列必要 metadata：

```powershell
netstat -ano | Select-String ':23456|:23567|:23568|:23569'
$p = Invoke-RestMethod http://127.0.0.1:23567/status
$p | Select-Object service, protocolVersion, pid, instanceId, sourceRoot
$p.capabilities.pet
```

預期 :23568 無 listener；其他 listener 仍需核對 owner/contract/畫面。不要列印 chat/mail/memory 或 bearer tokens；不要把 HTTP 200 直接填 PASS。

每一項記錄時間、source revision＋dirty digest、PID/instance/root、操作、觀察與 PASS/FAIL/UNVERIFIED。G7 physical deletion 完成、Electron runtime smoke/實機互動通過、上述 G5/G8 桌面項目有證據後，才可把 release verdict 改成 ACCEPTED；Git commit/push 仍需另外明確要求。
