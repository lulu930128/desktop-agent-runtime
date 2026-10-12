# W2 結果：source PASS；native UNVERIFIED

目標、owner、位置、進入／結束條件、負例與回滾見 [Gate 計畫](W1W5ClosurePlan-20261011.md)。W1 raw FAIL 登記後，只進 fixture 路徑，未強設 readiness PASS。

沿用 `qt_web_host.py` 的 QMainWindow child QWebEngineView、off-record profile、manifest、custom scheme、QWebChannel Wire、RequestBroker、QtOwnerAdapter。正式 launcher/VBS/Widgets 未接線，enabled=False 不 import Addons。新增 GUI-thread 建立 guard、idempotent shutdown、fixture-only metadata audit；audit 不傳 payload、token、Memory/Chat 內容，不暴露新 Web 方法。

本輪 typecheck/candidate-build 通過；asset roundtrip/tamper/traversal/network/file allowlist、41 個 broker/adapter tests 與 frontend tests 通過。精確 argv/exit/log/count 见 `.runtime/w1-w5-closure-20261011T072319Z/` 的 `w2-validation`、`w3-final`、`final-affected`、`w4-reviewer`，最新每 suite 結果以 `ValidationSummary.json` 為準。測試證明 source/bounded transport，不宣稱 native CSP、scheme 或 GUI thread signal 實機 PASS。

## Reviewer 決議：展示偏好與 Web Storage

原六檔不改。`owner-bootstrap.ts` 在 main import 前安裝 `owner-preferences.ts`：五個原版 key、原版有效值，僅單 view 的 memory Map；UI 原本的 localStorage 讀寫可運作。Qt `LocalStorageEnabled=False`，sessionStorage/IndexedDB/cache access fail closed。未持有 Chat、Memory、token、API credential、人物/專案 identity 或 domain state。

原版合法 mode/source（含 stocks/messages/notes）／六分類／compact/reduce-motion 都測過。secret/token/PII canary 對五個合法 key 及未知 key 皆拒絕；新 view 空白；固定 main.ts 只有五個 key 的 source 掃描通過。

**重開候選視窗會重設展示偏好**，不是保存成功。正式 `qt_app.py` 的 `QSettings("Kuro", "WorkCompanion")` 仍是其持久 `compact` 唯一 owner；本次 fixture 不 instantiate/read/write QSettings，不同步或競爭持久設定。W6 若要採用持久偏好，須明確由既有 Qt QSettings 單一 owner 對接並移除 transient override，不能開 persistent Web profile。

Qt LocalStorage API 依據：[Qt 官方 QWebEngineSettings](https://doc.qt.io/qtforpython-6/PySide6/QtWebEngineCore/QWebEngineSettings.html)。API 文件不是 native proof；bootstrap 相容層在此 sandbox 尚未跑進 QWebEngine。

新 native entry 使用 `create_candidate(... fixture=True)`，其 import 實測 BLOCKED，error/log 在 `native-W3/`。導航、下載、permission、filesystem、storage probe 必須看 native 實際 signal/回應；沒 signal 就 UNVERIFIED，不能以設定旗標代替負面測試。詳 [原生檢查](NativeCandidateReview-20261011.md)。

回滾：正式 UI 無採用；host/bootstrap/test 只按本輪 preimages/FinalAudit SHA 逐 hunk 回退；不能 reset／覆寫他人 WIP。
