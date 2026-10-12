# History／Chat 文案編碼修復

2026-10-10，Reviewer 指出的 P1 已在 source 修正。根因是本輪以 Windows PowerShell here-string 經 native stdin 傳入 Python 時，新增中文字串被轉成 ASCII `?`。改用 UTF-8 `apply_patch` 修復新增 History／Chat 區域的 label、狀態、placeholder、確認文字與分隔符；沒有修改私人資料或既有其他文案。

- `test_work_companion_source_encoding.py`：3 / 3 PASS。嚴格 UTF-8 解碼、Python compile、UI string literal 無連續三個問號、無 U+FFFD，並核對 Reviewer 指定的可讀文案。
- `test_r1_ws_dispatch_regression.py`：6 / 6 PASS。
- `test_r1_history_parity.py`：17 / 17 PASS（此時的 widget 測試仍是元件級，不能冒充正式 view integration）。
- `test_g3_conversation.py`：第一次 3 個 fixture AttributeError；補齊新增的 busy／identity fixture 及 confirmed keyword 後 27 / 27 PASS。WS／無 Pet 發送斷言保留。

完整輸出保存在同目錄各 suite `.txt`。後續 UI 整合會重新執行並覆核；此 checkpoint 不表示 R1～R4 已完成。正式 runtime 未重啟，Reviewer 靜態複查仍待進行。

安全寫入規則：含中文字面值的修改只用 UTF-8 patch；若用 shell 執行結構化重排，腳本只能是 ASCII，原文以 Python UTF-8 讀回／寫回，不能把中文 source 放入 PowerShell native pipeline。
