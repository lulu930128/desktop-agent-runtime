# W3／W5 原生候選人工檢查

這是 **SYNTHETIC、disposable、feature-off** 的 original renderer＋真正 `qt_web_host.py` candidate。不是原本 read-only browser preview，不是正式 launcher。本輪 Codex 執行在 import 時 PermissionError13，尚未看到此 GUI；下列是可執行的接力，不是已完成的 native 驗收。

## 開啟與關閉

正常互動式 Windows PowerShell，不使用管理員、不改 execution policy/ACL、不關 GPU/sandbox、不安裝依賴：

```powershell
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Open-NativeCandidate.ps1' -Checkpoint W3
# 完成並關閉 W3 視窗後，可開 W5；同一份 original candidate source。
& 'C:\project\desktop-agent-runtime\devtools\original-git-web-host-20261010\Open-NativeCandidate.ps1' -Checkpoint W5
```

預設15分鐘上限，可用 `-Seconds 1200` 最多20分鐘。視窗 X（含原版chrome close）結束 candidate 及自身 sidecar，無tray/常駐；script 回到提示字元。不要執行正式 VBS/launcher 來測本候選。若 import 失敗即保存 error，未啟sidecar；不修改或重建原venv。

使用既有 task `.venv` 的Qt、repo既有Node compiler、既有test Python；WebSocket client只載入原有pure-Python websocket package，不載入另一份PySide DLL。sidecar不建立production controller/config，只以 `__new__` 組裝已在disposable tests驗過的Memory/Core facade。所有資料只在本次 `.runtime/native-candidate-W3|W5-<timestamp>/`；loopback ports自建，不attach正式ports。

## 證據與判準

`NativeResult.json`：PID/executable、Qt版本、asset manifest/source SHA、off-record、GUI queued worker metadata、channel response/event、native confirm結果、storage/permission/navigation probe、broker/thread shutdown。`native-chat.png` 只在實際renderer/bridge出現後拍攝。`ServiceReady.json`／`ServiceResult.json`：自有PID/ports、WS context/reconnect、Core/Memory方法名；`service.log`／`native-error.log`留錯誤。fixture token只在task evidence，未送入Web或Web Storage。

`BOOTSTRAP_OBSERVED` 只證明程式觀測到 bridge與shell及client ready，**不自動提升成W1/W2/W3/W4/W5 PASS**。有任何 EXPOSED、非GUI worker、非off-record、錯誤side effect即FAIL；probe未完成/沒有相應signal/無截圖則UNVERIFIED，不能以未崩潰推定PASS。瀏覽器native禁止行為須分開檢查CSP阻止與Qt handler收到後拒絕，download click未產生signal只表示未觀測，不能當download handler已測。

| 檢查 | 正常操作／期望 | 證據種類 |
| --- | --- | --- |
| 原版外觀 | Chat/Today/Settings、六分類、History抽屜；1280×720／1380×860、100/125/200%另走W1 matrix | 人工／native screenshot；strict差異不改寫 |
| focus／IME | Tab焦點、中文組字Enter只完成組字、Shift+Enter換行、普通Enter送synthetic文字 | 真鍵盤／IME人工；JS合成event不能代替 |
| Chat／tool | 只輸入synthetic文字；固定reply/tool timeline，不能出現STALE MUST NOT RENDER | native UI＋同一qt-primary WS；無LLM |
| reconnect | 輸入 `SYNTHETIC DISCONNECT`，只断此fixture连接；待Qt原client重連，新context後重讀History | 真WS disconnect/reconnect；不可把未確認送出算完成 |
| History | list/search/new/select/delete；delete先取消再確認 | native modal取消不dispatch、確認才WS；无private history |
| 附件 | 只選output的 `SYNTHETIC-attachment.txt` | Qt native picker＋bounded payload；不要選私人檔案 |
| Memory | synthetic文字新增、停用、刪除、取消；每次確認檢查actor/content | native modal＋canonical disposable JSON/SQLite；260字限制 |
| Settings偏好 | mode/source/six categories/compact/reduce-motion；關閉重開重設 | transient設計，不是設定遺失bug；不碰正式QSettings |
| Today／Schedule | stale/partial來源限制可見；新增synthetic deadline先prepare、取消/確認、重讀 | Core schema v3 DB；Web materialize始終拒絕 |
| Tool／Mail／Study | policy唯讀；沒有contract的操作unavailable | 不向provider補資料 |
| Pet／profile | 本fixture回unavailable，不能假成功；真裝置/正式restart不在本輪 | source負例已測，native裝置/生命周期UNVERIFIED |
| 安全 | automatic local-scheme fetch/navigation/popup、storage secret、Notification request、blob download probes | 實際JS結果＋Qt denial signals；未觀測保留UNVERIFIED |
| 關閉 | X後script返回，ServiceResult exit0、chatThreadStopped/brokerClosed | 自有sidecar結束，正式runtime不變 |

禁止將真私人訊息、Memory或附件輸入此fixture。synthetic history是protocol fixture；Core/Memory為實際owner的disposable IO。Today採synthetic canonical payload，沒有真domain fresh evidence。沒有第二scheduler/notifier或Windows通知。若要涵蓋實體裝置權限、file system picker負面、完整native download handler或profile restart，仍需另有合適native證據；本輪source PASS不可代替。

最終把NativeResult、PNG、人工每項PASS/FAIL/UNVERIFIED交給reviewer。仍停W5，不修改正式launcher或進W6/W7。
