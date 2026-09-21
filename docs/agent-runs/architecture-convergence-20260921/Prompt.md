# 架構收斂與整合提交

## 目標與授權

使用者要求依附件協助整合本 repo 並 commit；後續明確選擇「先完成本 repo 與研究隔離規範」。附件是待核對的盤點／建議，source、settings、產品文件及本次授權共同界定範圍。

- 修正 Schedule Production／Observation Shadow 的文件漂移，整理 owner、read/write、process、persistence 與 consumer。
- 固定共享 schema／migration 邊界，盤點 Electron legacy primary 的 target owner 與 cutover 門檻。
- 制定研究 isolation 與 baseline evidence contract，保存可重現的來源 checkpoint。
- 審查既有 TTS lifecycle dirty work，獨立驗證與提交。

## 限制

- 不改 Core API、schema、public imports 或正式資料；不新增平行 Core／MCP executor。
- 本輪不實作 Today／Briefing cutover，不建立外部研究集中區／worktree，不跑研究攻擊。
- 不啟停正式桌寵、Central Voice 或 provider；不新增外部 side effect、不 push。
- Private state、logs、generated config、DB、音訊、模型、dependency/build output 不進 Git。

## 完成條件

- 架構五個主題（runtime、ownership、lineage、services、research）與獨立 persistence contract 可交叉導航並符合 source。
- TTS 與架構分開 commit；所有候選路徑精確 staging、private audit、diff check。
- 文件通過 strict UTF-8／local links／whitespace；TTS 通過 targeted tests、compile、renderer check/build。
- Source baseline 有 commit／policy／source hashes；runtime discovery、provider、desktop 未驗證範圍保持明示。
