# G1 未開放能力與 G2 起點

| 能力 | 本輪處理 | 未完成原因／下一個 gate |
| --- | --- | --- |
| OMI 自動觀測 | 保存偏好、間隔、預算；Core admission 永遠拒絕執行 | 尚無已核准的 canonical cached-result consumer、排程執行、quota ledger、freshness／失敗處理 contract。不可由 UI 或 prompt 自行查詢 provider。 |
| 主動語音 | 獨立偏好且預設 off；與聊天 TTS 分離 | 尚無通知去重、語音佇列／取消、quiet hours 與中央 Voice consumer contract 的完整交付。不得把 enabled 當成已播報。 |
| Mail read/detail | Core Today handoff metadata 保留；refresh/detail 拒絕 | 現有 mail detail 路徑直接接 Gmail provider／credentials，沒有受控 Core detail contract；不讀私人郵件、不接替代 MCP owner。 |
| Pet outfit/expression | overlay 除去參數提示，只傳 canonical ID；既有 owner 產生 preset | transport 成功不是視覺呈現證明。實際 Live2D/原生呈現 UNVERIFIED。 |
| Pet show/idle-motion | 保持停用 | 既有 handler 無實際 window/frame completion ack，不可宣稱已顯示或已播放。 |
| 附件 | 與既有 native/backend caps 一致：6 個、每個 4 MiB、合計 8 MiB；PNG/JPEG/WebP/TXT/PDF/WAV | 其他原始 renderer 提示格式保持拒絕；未測任何私人檔或付費模型解讀。 |
| Native desktop／cold-start | 不執行正式 Kuro | G0 阻擋仍有效；正式啟動讀私人設定／DB。offscreen D3D 失敗使像素驗收 UNVERIFIED。 |

G2 下一 turn 的既有授權範圍：日文 Study Hub、英文 Study Hub、OMI、Mail 四個獨立只讀正式 Integration；Core Observation／Today 有界投影；Source Contract／Freshness／Offline／Policy 真實接線。現有 Core Today metadata 與 G1 設定不能替代這些交付。本輪沒有實作 G2；也不把 G6 主動語音混入 G2。

G2 不改其他 repo、不接觸正式 DB／個資、不刷新 provider、不呼叫付費 LLM、不更改 sandbox/GPU flags。沿用 G1 signed owner 與 Core owner；來源缺契約時維持 fail-closed 並列缺口。
