# Original Git Renderer／Qt Web Host 當輪證據

日期：2026-10-10（Asia/Taipei）。**隔離成果已交付；WebEngine／視覺驗收 BLOCKED，產品 NOT ACCEPTED。**

六檔精確 source／commit／SHA／destination／對照版本與逐 Gate 判定在 [PlanAddendum.md](PlanAddendum.md)。原計畫已完整讀取；本輪直接追加及 scope-only patch 都遇到 OS 寫入拒絕。最終核對時，該檔另有並行變更，新增一份文字不同的第 5 節 checkpoint，已涵蓋 source hashes、隔離目錄與 BLOCKED 狀態；本輪保留現況，沒有覆蓋或改 ACL。原 SHA 與最終 SHA 都記於 `SourceVerification.json`，不將該變更歸功於本輪成功寫入。

## 實際變更與邊界

本輪確認成功的寫入都在本新建 task 目錄。原計畫的並行 checkpoint 另行記錄。`frontend` 保存六個 Git 原檔，不重畫 Qt Widgets/QSS。新增 Vite entry transform、CSP、synthetic fixture、browser bootstrap 與 QWebChannel bootstrap；原始 `main.ts`、CSS、model、types、schedule、HTML 沒有改動。

`qt_preview_host.py` 是未經 WebEngine import/render 驗證的隔離候選 host。只有 synthetic read-only protocol；不讀正式 History/Memory/Mail/Study，不呼叫 provider/LLM/TTS，不連 Core／Conversation，不建立 tray 或第二個 production owner。production DTO mapping、async owner completion、native confirmation 與 context/identity fences **尚未接入**，不能宣稱正式 host 完成。

原計畫建議的 `kuro_launcher/work_companion_web` 導致現有 G8 production scan 失敗，因此把全部本輪新檔移到 `devtools`，保留原 G8 檢查。沒有改動既有測試、Controller、Conversation、Core、Memory、Policy、Today、Pet-only 或正式入口。

## 驗證與證據檔

| 驗證 | 結果 | 證據 |
| --- | --- | --- |
| Git commit、6 source raw/destination SHA | PASS | `SourceVerification.json` |
| G7 實體舊路徑 | 35/35 absent | 同上 |
| WIP preimage | 1202 檔基線；原計畫有並行變更，其餘 1201 檔無變更 | `WipBefore.json`／`SourceVerification.json` |
| TypeScript／Vite | exit 0／0 | `ValidationFollowup.json` |
| G3／G4／G5／G6／G8 | 27＋15＋17＋11＋3 tests PASS | `Validation.json`＋`ValidationFollowup.json` |
| Pet owner Node | 20 tests PASS | `Validation.json` |
| 新 Python protocol／TS bridge | 4＋3 tests PASS | `Validation.json`＋`ValidationFollowup.json` |
| 既有 Pet renderer typecheck／build | exit 0／0 | `Validation.json`，build 僅輸出 task `.runtime` |
| 新 Python helpers | syntax PASS | `FinalChecks.json` |
| 隔離 HTTP preview | HTTP／entry/CSP 檢查 | `PreviewHttp.json`，不能取代 render |
| Qt WebEngine import/render | BLOCKED | `WebEngineProbe.json` |
| Chromium screenshot | FAIL，無有效圖片 | `BrowserProbe.json` |
| 真正 Windows／UI parity | UNVERIFIED | `EnvironmentBlockers.json` |

共 **100 個 tests 通過**，計入 G8 修正目錄後最後通過版本。`Validation.json` 保留第一次 G8 失敗的原始輸出；`ValidationFollowup.json` 是移到 devtools 後的通過結果及最後 frontend/bridge 檢查。沒有更改或跳過 G8 assertion。

正式 Python 只有 read-only import probe；probe 程式 exit 0 表示結果已記錄，`import: false` 才是依賴判定。PySide6 6.11.1 缺 `QtWebChannel` 與 `QtWebEngineWidgets`；task venv 建立成功但安裝因 socket OS error 10013 失敗，host capture exit 2。

內建 browser 工具缺可用 Windows sandbox backend；隔離 Chrome exit 2147483651、GPU child exit -1073741790，無 screenshot。没有套用停用 sandbox／GPU 的 flags。`capture_parity.py` 目前只有 syntax check，未產生 DOM geometry、DPI 或像素差異結果。

原 renderer build 使用既有 Vite config，僅變更 output 到 task `.runtime/validation/pet-renderer-dist`；未呼叫 prepare script、未複製或修改 Live2D assets、未覆蓋原 `renderer-dist`。現有 Cubism classic script warning 保留於輸出，build exit 0。

## 剩餘阻礙與接力

1. 依 [README 的 PowerShell 步驟](README.md) 在有權限本機環境完成 isolated dependency install、真實 import、render 與 capture。禁止正式 venv 安裝、改 OS 安全設定或程序重啟。
2. 同態圖須由 Reviewer 比較；geometry/token mismatch 會阻止 helper 繼續，pixel metrics 不設定虛構的完美門檻。History、六類 Settings、Chat model/thinking/role、composer、Today/Schedule、loading/error/disabled、responsive、keyboard/IME/a11y 仍需實際 UI 驗證。
3. 使用者舊 Settings／Chat 原圖檔本輪未取得。Git byte equality 不代替舊圖及新版實際畫面驗收。
4. 只有前述 Gate 通過後才規劃正式 owner adapter 與單一 Qt window source adoption。正式程序是否健康本輪未做 live probe；source unchanged 與測試通過不能報 runtime PASS。

沒有 commit/push；沒有觸碰或重啟既有 Kuro／Core／Conversation／Pet／shared voice 程序。本轮啟動的 preview server 已停止。
