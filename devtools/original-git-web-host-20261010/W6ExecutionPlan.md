# W6.D/E/F：現有視窗接線與原生刪除 gate

2026-10-11 本輪授權取代先前僅 B/C 的操作限制。套件不重裝；正式 UI 切換必須有同一 Python 3.10、同一 KuroQtLauncherWindow 的原生證據。若桌面不可取得，保留正式 Widgets，完成 source、disposable harness 與可重跑 receipts。W1 已接受的視覺差異不阻止結構實作，strict FAIL 歷史不改寫。

1. **基線**：保存 1,322 Git-visible paths、471 dirty paths、index、115 scoped preimages；重驗 installed ownership、imports/DLL、原六 renderer、G7 35 absent、程序與 ports。證據根由 `.runtime/w6-def-current.txt` 指向本輪新目錄，不覆寫舊 receipt。
2. **接線**：既有 QMainWindow 內互斥 Web/Widgets 建構；唯一 controller/client/tray/delivery。pre-app scheme、內容定址 bundle、Ed25519 簽章及明確 pin 驗證後載入記憶體；不加入 persistent cache。正式選擇器維持 Widgets，直到 native gate 有證據。
3. **責任拆分**：Web 分支不建 Widgets、不接舊 presentation observers、不做舊初始化讀取。status read 合併到 Port；保留 lifecycle、chat auto-connect、restart/cleanup。修正 timeout/disconnect、modal reentrancy、late callbacks。
4. **驗證**：targeted source/security/contract/regression；正式 Python 的 disposable existing-window harness，隔離 config/state/ports/mutex、真 client/Core/Memory owner。原生無法顯示時記 BLOCKED，不加 Qt override、不提權補過。
5. **退役 gate**：有 exact source/bundle/native evidence 才切正式入口及退役 Widgets；否則零刪除、保留 rollback。W6 未通過時 W7 執行不開始，只列 release blockers。
6. **交付**：W6FinalCheckpoint、精確差異/保全 receipt、人工 checklist、rollback 與安全 relay；第二輪獨立 read-only reviewer，Codex 自測不等於人審。

不讀私人聊天/Memory/mail/production DB，不呼叫 provider/LLM/OMI，不停止 Voice :18890，不 commit/push/reset/clean/checkout/stash。未知正式程序只記錄，不操作。
