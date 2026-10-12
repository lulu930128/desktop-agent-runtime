# W7 限定工程 readiness 與人工驗收

2026-10-11。**TECHNICAL_READINESS_SCOPED；正式 release 為 GATED。** 本報告只接受同機 source pin、正式套件無私態 preflight、原使用者隔離 native receipts 與 source regressions。W6.E automation PASS 不等於 W6.F adoption，也不等於 W7 全部封版。

## 已到達的工程範圍

| 門檻 | 裁決與證據 |
| --- | --- |
| 既有 window 原生自動化 | W6.E ACCEPTED，雙輪 74/74／70 required、單 owner／WS、security、restart。原 run 為 SYNTHETIC，不是正式私態操作。 |
| 單一 source pin | 四資產、manifest／Ed25519／CSP／lineage／immutable bytes 與 fail-closed tamper dry-run PASS；proposed patch 未套用。 |
| 套件／Python | Python 3.10.12、Qt/Essentials/Addons/shiboken 6.11.1、cryptography 46.0.3，7 modules／6 DLL identity、64 shared files／1,253 RECORD ownership。無 app/import override，未安裝。 |
| Source 回歸 | 固定 release-candidate profile、既有 Web branch constructor、security/evaluator/coverage/identity/navigation 負例、既有 source/Qt queue/loopback tests、typecheck；結果見 ValidationSummary。 |
| 完整封裝／可重現安裝 | **尚未完成**。requirements-qt.txt 只列 Essentials/websocket-client，未完整宣告 Addons/cryptography；目前 Addons 為具有 64 shared-file ownership 處理的既有 derived wheel。不可簡單 pip install Addons 或宣稱乾淨机器 release-ready。未來需獨立 package distribution／trusted publisher／installer驗收。 |
| 原版與 WIP | 六 original Git bytes、G7 35 absent、全部原 receipts、HEAD/index／allowlist外既有 paths 保全。 |

## 人工門檻與順序

- [ ] **先做獨立人工視覺驗收**：正常使用者桌面看既有隔離 candidate；Chat／Today／Schedule／Settings／History／Memory review、空白／loading／offline／stale／partial／error／cancel狀態與繁中文字，使用者記錄接受或問題。W1 歷史 strict layout 差異已接受的事實保留，不能改寫舊 strict FAIL。
- [ ] **Physical IME／keyboard**：真正中文組字、候選選取、Enter不誤送、focus/tab、modal取消與返回；注入 Qt IME events 不替代此門檻。
- [ ] **DPI／雙螢幕**：使用者日常縮放比例與視窗尺寸、跨螢幕、最小化／還原；檢查遮擋、文字溢出與焦點。自動 PNG存在不等於人審。
- [ ] **明確 W6.F 正式採用授權**：確認唯一 fingerprint、未套用 source patch、準備好的 rollback、真 profile可能啟服務的範圍，並記錄使用者／時間／批准對象。receipt 的 UNVERIFIED 不可自動改寫。
- [ ] **受控正式冷啟動**：取得上項授權後，核實當次 owner，正常 Quit；重驗 pin／dependencies／preimages、採用唯一 source pin，以現有 VBS啟動。證明當次 source/DLL/bundle、同一 window、一 Controller／WS／tray／notifier，X→tray/reveal／second launch／restart／Quit。不能靠舊 process 被喚回聲稱新source已載入。
- [ ] **真 OS toast**：使用者確認通知有實際顯示／點擊回同一視窗、claim/authorize/ack與去重；synthetic tray.showMessage不代表 Windows delivery。所需 production schedule操作須另列明範圍。
- [ ] **Pet／Live2D**：真 renderer、角色畫面、既有 pet-presentation role、缺席時文字可用；不用新服務或第二 qt-primary WS。
- [ ] **Camera／mic／screen／Voice**：使用者自己確認裝置、權限、capture取消／送出與語音播放；任何真內容送出／付費 quota需另行明確授權。Shared Voice :18890由外部 owner管理，本輪未查控／啟停。
- [ ] **Widgets退役另審**：正式 Web display驗收成立後才用 reverse-reference圖及精確移除清單，分批保存 rollback、再驗唯一 owner；不能與本輪 source PASS一起自動刪除。
- [ ] **W7 最終決策**：人工/device／production adoption／package distribution各門檻有當次 evidence後，才決定具體 release範圍。未具足者明列限制，不能總PASS。

## 仍存在的產品能力限制

一般 tools 的 `confirmation_available=false` 仍是 blocked能力；Mail body/refresh canonical contract 仍未提供。沒有讀真郵件、私人 Chat/Memory、OMI、LLM付費內容或正式DB，不代表它們已驗收。Source/runtime/ui/manual/provider 各層須分別裁決。

本輪沒有新的 production listener、service、feature flag、readiness override、UI fallback、第二 Controller／WS 或第二套UI。唯一正式入口維持 Widgets／RELEASE_PIN=None。
