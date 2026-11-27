# 長期記憶實作紀錄

本次依 2026-11-25 Plan 原件實施；原件保留供逐條核對。正式使用者模式、私人歷史回填與 Launcher 部署尚待個別決策。

| 階段 | 已進入的原有路徑 | 驗證與範圍 |
| --- | --- | --- |
| M0 | 檢查 HEAD、既有改動、History、Repository、Index、Runtime、Qt、信任契約 | SourceBaseline.json 只保存正式來源的計數。正式載入模型和程式 SHA 未取得。 |
| M1 | 移除 80 筆裁切；History 原子替換、寫入意圖、逐來源水位；SQLite L3 投影 | replay.py 同一組 1k、10k、100k 資料。冷建庫和熱查詢分開。 |
| M2 | 共用 user 與 project namespace、角色與 thread 過濾、來源 turn、版本與撤回 | test_companion_memory.py 使用獨立資料根，覆蓋角色與專案界線。 |
| M3 | 同對話取回、FTS、多語向量、原有 prompt 編譯與預算 | Quality.json 用相同本機模型比較四條路徑。LoCoMo 公開資料另測來源定位。 |
| M4 | 在 History 投影衍生有 speaker、turn 及 span 的抽取式情節 | 可由 History 重建。情節以完成回合為單位，明確相鄰追問可連結前回合並保存兩個來源；跨回合推理表現由公開語料的 evidence recall 衡量。 |
| M5 | 已完成的使用者回合進入本機語意分類，經授權寫回 Repository 或成為候選 | Content/source digest、授權變更、政策撤銷、失敗重試均沿用原生命週期。正式資料沒有設定新授權。 |
| M6 | Qt 既有 Memory 視圖擴充、原生確認、來源跳轉；CLI 維護與讀回 | 發行物、正式 runtime 與實際桌面操作各自驗收。Qt 可依內容篩選、批次審閱、建立修訂版本、查看來源摘錄及處理數與失敗原因、核對目前對話、透過原生選檔匯出及還原至新目錄。Runbook 提供同一 owner 的 CLI 操作。 |
| M7 | 依來源 revision 續跑回填、封存、驗證後還原至全新根 | synthetic rehearsal；正式回填、切版與部署均待授權。 |

測量與未驗收項目見 [Evidence.md](Evidence.md)，操作順序見 [Runbook.md](Runbook.md)。

## 第 0 節逐項驗收

| 條件 | 已驗證 | 還缺的證據 |
| --- | --- | --- |
| 1 同 thread、跨對話／日／角色 | 隔離 Chat 讀回共享偏好；長 thread 與跨語來源、多跳逐題比較 | 正式桌面讀回、自然使用品質；公開語料仍有漏召回與非 gold 片段 |
| 2 版本、時間、來源 | 過期／as-of／superseded、跨角色與專案隔離、缺明確 project 的舊資料供管理、撤回／改名不復活；沿用既有工具與 Memory Core 契約 | 正式連線的外部 owner 與工具結果、自然語言未涵蓋的關係與事件 |
| 3 自動形成與更正 | 明示、人工和 scoped_auto 皆以 synthetic profile 驗證，包含政策失效、重送、助手 claim、來源綁定 | 正式自動保存模式與自然語料的誤存率 |
| 4 容量與增量處理 | 95 筆 active 全保留，停用一筆後仍為 94；1k／10k／100k、來源 revision、checkpoint、錯誤、中斷與重建 | 正式私人歷史的回填範圍與批准 |
| 5 可攜、重啟與替換 | 雙程序雙模型 Qt 聊天；366 個合成日期、26 個歷史來源、跨角色／專案、重建及切版後新增資料對帳 | 第二台實體電腦、正式角色與真實維護時段 |
| 6 正式路徑與較舊版改善 | 既有 Qt chat client、WebSocket、Runtime、LLM 實際往返；實際 Qt WebEngine 在隔離 profile 操作候選面板；相同 corpus 和模型比較 | 正式 Launcher 採用、真人桌面、語音硬體、Live2D 與正式工具 E2E；獨立 reviewer 的正式發布判定待辦 |

MEM-01／05／08／09 對應 M2、M5 的 scope、形成、版本與撤回測試；MEM-02／04／10 對應 M1、M7 的容量、寫入與恢復；MEM-03／06／07 對應 M3、M4 的 L2 及檢索；MEM-11／12 對應 M6、M7 的 Qt 管理、可觀測性與重放。

**交付判定**　M0–M6 已有來源實作及隔離驗證。M7 的可攜性、長期模擬、備份及回復部分已實測；正式採用與第 0 節端對端產品驗收待授權。Program/Runtime 採用身份、正式模型與真機行為均不能從候選指紋或 benchmark 推定。
