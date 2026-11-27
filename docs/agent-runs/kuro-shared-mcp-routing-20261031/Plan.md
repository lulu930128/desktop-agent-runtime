# 實作與驗證計畫

1. 核對 13:09 正式 log、dirty baseline、既有 owner/config/schema；保存本輪 preimages，保留 SchemaError WIP。
2. 局部補齊 US 市場 routing 與 Node command；核對 shared adapter 的 env precedence，修正 Listening Trainer 接線。
3. 在既有 agent 內區分無呼叫、已嘗試但無證據、真實 error result；不改 executor/policy/schema owner。
4. 跑最接近的 fixture tests 與獨立 MCP session；已 PASS 且未受後續修改影響的檢查沿用，不重跑無關項。
5. 留下 task-only diff、精簡收據與正式 loaded identity 限制；不以 source/probe 成功宣稱部署。

遇到執行權限邊界停止；API 失敗不重試。收據不得保存 raw ToolArgs、prompt、完整 schema/reply 或詳細市場／學習資料。
