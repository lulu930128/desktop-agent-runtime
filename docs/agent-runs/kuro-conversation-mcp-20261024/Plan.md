# 執行計畫

1. 保存 WIP／ignored config／bundle hash 基線；確認現成 Python／Node、入口與完整 STDIO discovery。OMI 環境失敗則停止切換。
2. 更新唯一 registry、角色、政策、catalog 與中文 Settings；移除舊 OMI autorun／direct HTTP，保留歷史 identity owner pin 但不可執行。
3. 用真 STDIO 及合成 loopback fixture 驗證 schema、payload、allow/deny、無秘密繼承；其他成品只讀盤點 transport/auth/confirmation 阻擋。
4. 既有 builder 產生獨立 signed bundle，驗簽並更新 RELEASE_PIN；執行 targeted tests、isolated Qt toggle/CAS/readback、diff 與基線比對。

任何 ACL、環境或 discovery 失敗記錄精確邊界，不以安裝、proxy、fallback 或略過 guard 解決。
