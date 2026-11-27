# Qt Web 呈現收斂

狀態：**Source PASS／Isolated Qt PASS／正式 Runtime Pending／Native UNVERIFIED**。待 Reviewer 獨立確認。OMI 自動觀測仍 BLOCKED，不因本輪 UI 改動取得執行權。

基線：`main`、`c2b3e64c27caaec8c2cba5b213444ddce0d79e03`，使用者 checkpoint 後 clean。沿用 G1/G2 有效證據，未重跑 G0/G1 全 gate。本輪命令未遇 sandbox／ACL 拒絕。

## 實際變更

- Today：標題下方只放來源短狀態，下一區是原優先清單；完整來源資訊收合在清單後。來源時間、限制、raw JSON 可展開，polling 不重置展開狀態。英文零項且 partial 顯示「本次無待辦 · 資料有限制」，時效未知仍標示；missing／auth／offline 不推定零項。
- 工作列保留來源摘要、真正提供的期限與有用 meta；不展示 raw reason codes，不新增工作、不改排序。完整 evidence 保留。
- 工具：四群組預設收合，顯示啟用數／總數。展開後顯示名稱、短用途、政策狀態、開關與按需診斷。原 native confirmation、CAS、atomic persistence、GET readback 與未採用警告保留；未修改政策 owner 或權限上限。
- 對話：移除常駐附件限制段落，改為附件按鈕 title／ARIA description 與原生 details 說明。未修改附件驗證、Offline、模型或輸入操作。
- 採既有深色 CSS variables、13–15px 主要新增文字、原生 details／summary／checkbox 和可見鍵盤焦點。無新 UI library、字體下載或新 rendering owner。

精確產品路徑：`frontend/src/owner-presentation.ts`、`canonical-model.ts`、`owner-bootstrap.ts`、新增 `owner-presentation.css`（皆在 `devtools/original-git-web-host-20261010/` 下）；同目錄 `build_owner_bundle.py` 僅把 CSS 加入 lineage；`kuro_launcher/qt_web_release.py` 僅更新 pin。測試：新增 `tests/kuro_ui_refinement.test.cjs`、擴充 `tests/g2_tools_today_surface.py` 的 opt-in `--refinement`。

## 定點證據

- TypeScript `tsc --noEmit` PASS。
- Node：3 個新呈現 tests＋4 個既有受影響 policy/readback/source tests，**7/7 PASS**。附件驗證精確 name-pattern **1/1 PASS**。
- 最終 signed bundle 經真實隔離 Qt／合成 Core HTTP／合成 policy 驗證 **26/26 PASS**：21 個工具、4 群組、確認／取消／讀回、無 hot-adoption 假象、strip → primary → folded detail、鍵盤空白鍵／focus、polling、原始時間、附件 ARIA 與來源篩選。
- 1100×820 視窗、五筆合成工作，Web zoom 100／125／150%：來源列高度 19.5／45／45 CSS px，字級 13px，無水平溢出。已人工檢視 Today、工具折疊／展開、Chat 附件說明截圖。150% 時工具導航沿用原本水平捲動、內容需向下捲動；不是 Windows 實際 DPI 或實體輔助技術驗收。
- Python syntax、Git diff check、六份 immutable originals、CSS lineage／簽章及舊版回退資產核對見 `Status.json`。

所有本輪收據及合成截圖在 `.tmp/kuro-ui-refinement-20261023/`。`SurfaceFinal.json`／`surface-final/Result.json` 為最後結果。初次 Surface 的收合斷言失敗是 fixture 把 Core raw 當成 Qt onData；改用正式 `today_projection` 後通過，保留原失敗。最初 log 印出遇 cp950 勾號編碼錯誤，Node／Build 子程序 exit 0 與 UTF-8 原始收據保留，未把輸出器錯誤偽稱產品失敗或刪除失敗證據。

## 簽章與回退

新 fingerprint：`2ec66143d6aca11dacc9c55a766039a19d86d275f2df91acfd6a63e334566876`。
Manifest SHA：`0a96c6e60e52c9d56e485ca8f7a915863681bd8a6bceffcfb2f8156625b6f910`。
Builder／verify receipts：`devtools/original-git-web-host-20261010/.runtime/kuro-ui-refinement-20261023-final-build.json`、`kuro-ui-refinement-20261023-verify.json`。

舊 fingerprint `159c5832bca59216ceb3a4bb96f92ea031b9437a969700786c4b9ca29cf27811` 已保留並驗簽。若需回退，由操作者以 checkpoint 還原本輪 owner presentation／model／bootstrap／builder／pin 這組變更，移除新增 owner CSS import 與檔案，核對舊 pin 後再自行採用；不動 DB／policy／YAML。此輪沒有執行回退或重啟。

本輪不改 Core／OMI／Hub／Mail／正式設定、policy、六份 immutable originals、私人資料或安全 flags；沒有 provider／LLM 呼叫、commit／push、正式服務啟停或中央 Voice 操作。下一步先由 Reviewer 核對 diff 與收據，再由使用者自行重新開啟正式 Kuro，驗證實際 DPI、螢幕閱讀器及現役資料呈現。
