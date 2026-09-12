# 安全政策

## 修正範圍

安全修正以目前 `main` 為優先，不承諾舊 release 的長期維護或固定回應時限。回報時請提供 commit 或版本；第三方 runtime／SDK 問題可能需要向原維護者協調。

## 回報漏洞

請勿在公開 issue 或 PR 貼出 exploit、token、完整 log、`.env`、資料庫、對話、記憶、郵件或私人 voice reference。

本文件建立時（2026-09-12），此 repository 的 GitHub private vulnerability reporting **未啟用**，也未公布安全聯絡信箱。若 Security 頁面出現 **Report a vulnerability**，可使用該私人入口；若沒有，請在 [Issues](https://github.com/lulu930128/desktop-agent-runtime/issues) 僅提出「需要私人安全回報管道」，不附漏洞細節，待維護者安排私人方式後再傳送。不要把公開 issue 誤當成保密通道。

取得私人管道後，建議提供受影響版本、影響範圍、最小重現、所需權限、已遮蔽的證據及可行 workaround。不要使用他人真實資料驗證漏洞。修復或協調公開前，避免公布可直接利用的細節。

## 重要邊界

- Local control API 預設只供 loopback 使用，不應直接暴露到 LAN／Internet。
- Launcher session token 不得進 renderer、設定檔或 Git；原生確認與一般工具 policy 是不同保護面。
- 外部工具的寫入、刪除、發送、發布、長期記憶與高成本操作不能繞過授權。
- Kuro consumer 不停止共用中央語音服務，不將模型或私人 reference 當成公開資產。
- 安全修復應保留可診斷錯誤與來源限制，不用隱藏失敗、清空資料或關閉 policy 當作修復。

若憑證已公開，應先在發行方撤銷／輪替；刪掉 Git 最新檔案不會清除歷史。回報與修復過程依 [行為準則](CODE_OF_CONDUCT.md) 保護當事人資訊。
