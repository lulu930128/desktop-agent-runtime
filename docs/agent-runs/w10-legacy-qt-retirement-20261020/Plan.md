# W10 舊 Qt Widgets 退役

使用者已批准本輪 source deletion；基準為 `main` 的
`f4980098b46986d0d0b6ca2ef7fbc538732913bc`，開始時工作樹乾淨。

1. 核對正式入口、產品文件、共用 owner 與測試依賴；將 raw preimage、SHA 存入 repo ignored `.tmp/w10-legacy-qt-retirement-20261020/`。
2. 精確保留 Qt Web presentation 與共用 lifecycle，移除 Widgets constructor/builders/callbacks/style；簽章 pin 不變，缺少 pin／資產時 fail closed。
3. 遷移有效 History／Chat／Core／Schedule 測試，完成依賴檢查後物理刪除三個 UI modules。歷史 W6–W8 gates、archive、receipt 原封保留。
4. 建立獨立 W10 source baseline，執行 Python syntax、offscreen owner／Qt signals、synthetic loopback WS／Core HTTP、protocol/security 與有限 regression。歷史 source SHA 不作為當前 PASS。
5. 記錄 source／isolated 結果、保留 owner、測試遷移、W11 debt 與後續 Win11 native cold-start 驗收。

範圍只限 Kuro 的 W10 source／tests／docs。不得改 Backend、Pet、六份 immutable frontend、簽章資產、builder、私人 state、字型／圖示、CustomTkinter；不得 commit／push／正式服務啟停。若發生 PermissionDenied／EPERM，停止該寫入，不換工具或權限繞過。測試失敗先查 traceback 並修正，不以 skip 或減少斷言取得 PASS。
