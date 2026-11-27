# Qt 回答顯示與長工具清單語音修正

修正串流換行遺失、live／history 雙排，以及 v1／v2 prompt 衝突。完整 Display 與 private 日文 Speech 分離；不追加翻譯或摘要 API。

優先僅修既有 Qt adapter，驗證目前 pin 對應的 renderer 合併方法。只有 fixture 證明無法完整修復時，才局部修改 frontend Source，並將正式 Release 標為 BLOCKED。不得修改 immutable 檢查、builder、ReleasePin 或簽署流程，不尋找或建立 signing key。

只做 Source、synthetic fixtures 與定點測試。不 stage／commit／push／deploy，不重啟 runtime，不操作私人歷史或付費模型。保留 142 個既有 dirty 檔案與先前 Speech v2、GPT-6、MCP 修改。

驗收：換行／重複文字／空白原序保存；live→history 非同步重整維持一筆回答；分開回合相同問答不遺失；reconnect 不重播舊回答。v2 footer 有效且隱藏，語音短且不讀工具清單；fallback 若存在只能如實提示詳情在畫面，不能冒充摘要。Source、Test、Release、Runtime 分開判定。
