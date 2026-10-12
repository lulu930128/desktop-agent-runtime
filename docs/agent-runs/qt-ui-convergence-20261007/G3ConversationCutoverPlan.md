# G3 — Qt conversation independence plan

日期：2026-10-09
狀態：Ready for implementation

## Goal

Qt 成為唯一 canonical conversation frontend；Electron Pet 僅作 presentation subscriber，不再是 text/history/turn owner。

Target：
```text
Qt qt-primary
  -> text/history/interrupt/attachments
  -> one runtime context / one turn owner
  <- text/status/history
  \-> presentation mirror -> Pet pet-presentation
                           <- playback completion only
```

## Roles

- `qt-primary`: controllable canonical frontend。
- `pet-presentation`: non-controllable presentation subscriber。
- `launcher-console`: diagnostics/compat non-controllable。
- legacy default `frontend`: compatibility only；canonical desktop path不得同時存在另一個 frontend。

`_controllable_client_uids()` 不得把 pet-presentation 算入 hot-switch target。

## Presentation fan-out

不要使用 ChatGroupManager 把 Qt/Pet組群，避免 group conversation/context/history semantics。

對 qt-primary individual conversation建立 send wrapper：
- 原訊息永遠送 Qt primary。
- presentation-safe payload mirror 到所有 pet-presentation：audio、full-text/display、presentation control、backend synth markers、Live2D actions。
- history-list/history-data/config/admin/error 不 mirror。
- Pet disconnect 不影響 primary turn。
- Pet不存在時 Qt文字聊天照常。

## Playback ack

Qt 不實際播放 Pet audio，因此 Qt client不能再在 `backend-synth-complete` 自動回 `frontend-playback-complete`。

Runtime規則：
- 若有 pet-presentation：等待 Pet 真實 `frontend-playback-complete`，並把該 ack轉給正在等待的 qt-primary client UID。
- 若沒有 presentation subscriber：runtime在 backend synthesis complete 時對 primary turn做內部 no-presentation completion，不能等30秒 timeout。
- pet-presentation 的 ack不能啟動/修改 conversation。

## Inbound restrictions

`pet-presentation` 禁止：
- text-input
- interrupt-signal
- history create/select/delete
- config switch
- ai-speak

必要 presentation protocol可允許 heartbeat/request-init-config/audio-play-start/frontend-playback-complete。
Mic/camera/screen capture ownership不在 G3 重構；canonical text session先完成，G4再處理 UI/perception parity。

## Qt cutover

- Qt WS URL -> `client_role=qt-primary`。
- `_send_chat_text()` 直接 `QtRuntimeChatClient.send_text()`。
- attachments直接走 Qt WS。
- create/select/delete history 優先直接走 QtRuntimeChatClient。
- `_interrupt_chat()` 直接 `send_interrupt()`。
- 不再呼叫 `controller.send_pet_text_for_chat()` / Pet `send-text` 作 Qt chat path。
- pending blank-history create後，收到 new-history-created 再送 pending submit，避免 duplicate turn。

## Pet

- canonical desktop env / URL把 Pet websocket role改成 `pet-presentation`。
- Pet仍取得 presentation/audio/Live2D output。
- Pet不成為 hot-switch target。

## Tests

- role normalize/controllable inventory。
- qt-primary + pet-presentation -> only Qt controllable。
- Pet text/history/interrupt rejected。
- presentation payload mirrored；history/admin不mirror。
- playback ack forward to primary；no Pet uses internal completion/no 30s wait。
- Qt client backend-synth-complete no false ack。
- Qt send/interrupt/history direct WS，controller Pet send path不被呼叫。
- attachments。
- Pet absent Qt text conversation unit/integration works。
- duplicate-turn guard。
- existing runtime/Qt/Node regressions。

## Stop conditions

- 以兩個 frontend/group替代 role split。
- Pet仍能直接 text-input 建立獨立 turn。
- Qt仍經 :23567/Electron send-text。
- Qt假裝完成實際 Pet playback。
- 修改 Today/DB/desktop startup（屬其他 Gate）。
