
## 2026-10-10 原始 Git Renderer 還原 checkpoint

總狀態：**BLOCKED；產品 NOT ACCEPTED**。本輪未替換正式 Qt 主 UI，也未重啟既有程序。

已重新驗證 `git rev-parse HEAD`、六個 `git cat-file -e` 與原始 blob bytes：commit = `995c23c7c8d1be62000229d58610d2214f3bb745`。六檔 SHA 全部吻合；五個 recorded SHA 與 `GitSourceInventory.json` 一致，HTML SHA 也與 G7 manifest 一致。

**目錄決策修正**：原計畫的 `kuro_launcher/work_companion_web` 是提議位置。G8 production consumer scan 證實此位置會被視為 production tree；本輪全部新檔改放 `devtools/original-git-web-host-20261010/frontend`。G8 assertion 未修改，G7 舊路徑未恢復，production entry 未接入。

下表 destination 均相對於 repo 的 `devtools/original-git-web-host-20261010/frontend/`。

| 原始 Git 路徑 | SHA-256 | Destination | 本輪結果 |
| --- | --- | --- | --- |
| `pet-electron/renderer/src/work-panel/main.ts` | `9f0b8eb99c7f1e0435b0b85eaf46222edce1215c6cf89dce91be1105d9cdbbc5` | `src/work-panel/main.ts` | PASS，91835 bytes |
| `pet-electron/renderer/src/work-panel/styles.css` | `d6c5bbf9bd49609300f8675061b4acbf4639d3dd08940cf70b79b4054715020f` | `src/work-panel/styles.css` | PASS，39429 bytes |
| `pet-electron/renderer/src/work-panel/model.ts` | `25b91217df1a805160b92f6215878b16f9ee49af7ed10d9a128b7f15093d0792` | `src/work-panel/model.ts` | PASS，6874 bytes |
| `pet-electron/renderer/src/work-panel/types.ts` | `c06528df69736b5338911b793e6c0fc83ba702e61c6505742ff12b60b1949e52` | `src/work-panel/types.ts` | PASS，7049 bytes |
| `pet-electron/renderer/src/work-panel/schedule.ts` | `695bf308ecc1ba010839a3d50703c6696f6e154457c1346874f8fd3a57f66e99` | `src/work-panel/schedule.ts` | PASS，20274 bytes |
| `pet-electron/renderer/work-panel.html` | `35f01f7e3f8cd449e81a7ec6d119cfe88d996f96c72415537fa0f1385dc74acb` | `work-panel.html` | PASS，367 bytes |

本機 Git 對照版本 `94065af5cfbaa3b5acbd5e7e19417a803cdaa122` 只有 main.ts 不同（SHA `1405303b6e0e0d95962697efa8a35dd9b2e53f54731ac4d9aedd6e1148201755`）；其餘五檔相同。`3baf05728921607d71306c98d43eaad155b0dbc1` 的 main/styles/model/types 不同、schedule 不存在、HTML 相同。完整版本 SHA/blob 對照在 `devtools/original-git-web-host-20261010/SourceVerification.json`。未以 remote／QSS 取代指定 995c23c。

| Gate | 本輪結果 | 限制 |
| --- | --- | --- |
| 1 Git / WIP | PASS | 六檔位元一致；1202 檔基線；35/35 G7 舊路徑不存在 |
| 2 Original preview | source/build PASS；互動 UNVERIFIED | 原 Vite 8.0.13／TS 6.0.3 check/build exit 0；localhost preview 可啟動；瀏覽器 render 受 OS 阻擋 |
| 3 WebEngine | BLOCKED | 正式 Python 真正 import 缺 QtWebChannel／QtWebEngineWidgets；隔離安裝失敗：OS error 10013 |
| 4 Qt host / bridge | 隔離 source only；runtime BLOCKED | devtools 候選 host、最小 read-only WebChannel；4 Python protocol＋3 TS bridge tests 通過；未接入正式 owner |
| 5 Parity / release | UNVERIFIED / NOT ACCEPTED | Browser sandbox backend／Chrome GPU process failure；0 張有效截圖，無 DOM／pixel 實測 |
| 6 Regression / adoption | targeted source PASS；adoption BLOCKED | G3/G4/G5/G6/G8：73 Python；Pet owner：20 Node；原 renderer check/build exit 0，build 為隔離輸出 |

完整交付見 repo `devtools/original-git-web-host-20261010/Checkpoint.md` 與 `README.md`。capture helper 已準備同 fixture／同 viewport 的 Chat、Settings、Today/Schedule、geometry、tokens、MAE/RMS／pixel fraction，但本輪未跑通。真正 Windows visible desktop、IME、125%/200% DPI、舊圖人工比對及正式 adapter owner integration 仍 UNVERIFIED。

正式主 UI／程序未替換或重啟；沒有改正式 venv、私人 DB/config、Live2D、shared voice、sandbox/GPU 策略；沒有 commit/push。
