# W6 第二輪獨立工程複查

2026-10-11，read-only reviewer `/root/w6_boundary_review`。授權範圍為本輪 UI 接線、request／owner／隔離／native gate。Reviewer 沒有改檔、安裝、啟 native、停止程序或讀私人 state；其合成重現不等於使用者實機或外部最終 reviewer approval。

## Findings 與處理

| Finding | 修正與限定證據 |
| --- | --- |
| 快速 History response 先清 pending，失去 submitted correlation | 唯一 client 保留 submission ID；真同步回應及真 WS regression。 |
| timeout/disconnect 殘留 history/profile wait；late worker重建 wait/snapshot | 每個 request 的 cancellation Event、abandon及completion fence；expired worker、capture continuation、read retry 測試。 |
| Modal nested event loop Quit／queued signal在close後仍送結果 | Broker重核closed/pending，Port解除connection、queued callback guard；source Qt queue及native lifecycle檢查。 |
| stale frontend error丟unknown；profile lock busy仍改selection | 保留unknownResult；原lifecycle lock先取得才修改選取，busy時無mutation。 |
| manifest驗完後重讀存在TOCTOU | 解析同一份已驗bytes，asset對該digest核對；reviewer替換重現改為拒絕。 |
| 缺Live2D catalog／diagnostics阻斷Chat auto-connect | runtime status與各子狀態分離；truthful unavailable，真Qt queue及真Controller測試。 |
| Web branch丟棄owner/chat diagnostics | 接既有stdout tee與chat diagnostic signals，不傳HTML。 |
| native總PASS缺coverage、無效DNS網址誤算denied、second launch手動reveal | required coverage fail-closed、可達loopback200/hit count、共用正式activation timer；byte-identical helper隔離restart。 |
| GUI尚未delivery前，WS已更新identity，queued mutation仍執行 | 唯一Qt client以RLock原子提供identity/Event，transport改動前cancel；worker僅讀token，背景_on_message先於processEvents負例owner_calls=0。 |
| fixture太早恢復private root/network；partial-start漏cleanup | native child close(restore=False)保持隔離直到退出；unit先drain pool，分開create/start確保cleanup。 |

## Reviewer 末次原文摘錄

> 第二輪唯讀複查完成。本次末驗的 P1、P2 已修正，限定範圍內未留下未修正的 P1／P2。
>
> P1：WS identity 更新早於 GUI delivery。qt_chat_client.py 以同一個 RLock 原子取得 identity／Event，更新前取消前代 token。真 QtRuntimeChatClient._on_message 背景執行、尚未 processEvents() 就放行 queued worker 的重現結果：transport_cancelled=true、owner_calls=0。另驗 snapshot 在更新中阻塞，不會混用兩代 identity／token。
>
> P2：fixture teardown 過早解除隔離。一次性 native 路徑保留 process-local root／network 邊界直到退出；零落盤重驗確認在途 CharacterMemoryRepository.root() 仍取得 synthetic root。可重用測試先 drain pool，再依 cleanup 順序恢復環境。fixture 初始化已拆開賦值，partial-start failure 能進入 cleanup。
>
> RELEASE_PIN=None 已再確認。正式 Widgets、退役禁制及 W7 未啟動應維持。這份是 Codex 獨立讀碼與限定合成重驗紀錄；外部最終工程 reviewer、使用者實機及人工驗收仍未完成。

以上摘錄省略行號／連結，沒有改變結論。完整當次測試與 native 限制見 [W6FinalCheckpoint](W6FinalCheckpoint.md)。Reviewer 最初核對的是末次修正前 `native-final`；主 agent 修正後另跑 `native-reviewed`，兩次實際exit仍2、renderer49、BLOCKED，不能以它宣稱完整原生採用。

## Reviewer 對末次 receipts 的補充

> 補充核對完成：native-reviewed 父程序 53664、重啟子程序 53764 的兩份收據，各列 12 個 source SHA，均與現存檔案完全一致，且 sourceUnchangedDuringRun=true。兩者 OS／reported exit 都是 2、renderer exit 49、loadFinished=false、coverage 未通過；restartObserved=true，整體仍為 BLOCKED。productionAdoption=false、RELEASE_PIN=None、w7Started=false、humanApproval=UNVERIFIED 均已核實。此次僅讀取收據及計算檔案雜湊，未執行測試。
