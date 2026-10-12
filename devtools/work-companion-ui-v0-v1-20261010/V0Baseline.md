# Work Companion V0 視覺基準

日期：2026-10-10。範圍：使用者指定的 2026-08-23 兩張 Work Companion 畫面，轉成可檢查的 Qt Widgets / QSS 視覺規格。
本輪僅建立 opt-in synthetic preview；`launcher_qt.py` / `KuroQtLauncherWindow` 仍是正式唯一主視窗。

## 證據與版本優先順序

1. **使用者本輪提供的截圖描述是視覺基準**。原始兩張圖片未以附件出現在本輪，沒有重新取樣原始像素，也沒有逐像素對圖驗收。
2. 圖 A：2026-08-23 17:03，**1280 × 714**。寬 rail、金色 Chat active、平面逐回合訊息。
3. 圖 B：2026-08-23 20:18，**1280 × 723**。窄 icon rail、青綠 Settings subnav、左文右選單。
4. Git 參考：`3baf05728921607d71306c98d43eaad155b0dbc1`，`feat: add unified Kuro work panel`，2026-08-23 22:19:22 +08:00。
   純視覺參考檔案：
   - `pet-electron/renderer/src/work-panel/main.ts`：`rail`、`chat-frame`、`message-list`、`composer`、`settings-shell` 的資訊結構。
   - `pet-electron/renderer/src/work-panel/styles.css`：間距、文字層級、訊息與設定列的分隔線。
5. 該 commit 是 **Electron 純視覺參考，不是 Qt source**。其中 rail 78、chrome 50、active `#65B3A6` 與使用者指定的圖 A/B 有差異；採用本輪的 180/73、48/52、金色/青綠。
6. **圖 A 的寬 rail 金色版本沒有已確認的完整 Git 對應**，可能是當日未提交迭代。不能將 `3baf057` 宣稱成圖 A 的精確還原。
7. Today 沒有獨立截圖基準；延伸圖 A 的共用 tokens，以「摘要 → 原因 → 下一步 → 來源限制」建立 V1 提案，仍待使用者審核。

參考讀取只使用 `git show`；沒有 restore、checkout、重新建立 G7 已刪 source，沒有移植 service / IPC / bridge / localStorage。

## 圖 A：Chat 幾何

座標以原圖左上為 (0, 0)，以下為使用者描述中的基準值。V1 render 統一使用 1280 × 720 logical pixels。

| 元素 | 圖 A 基準 | Qt 實作約束 |
| --- | --- | --- |
| 主底色 | `#10141D` | 平面 near-black blue，無漸層 |
| 左 rail | x=0..179，寬 180，`#131823` | 固定 180；Kuro / WORK COMPANION |
| 導覽 | 普通對話、今天，底部狀態／設定 | Chat active 金色描邊；不增加 History 固定大欄 |
| Chrome | 高 48 | 位於主工作區頂端 |
| Chat header | y≈48..151 | 103 高，含 History toggle、標題及簡短說明 |
| 訊息正文 | max 760，x≈346..1106 | 760 text measure；YOU / KURO 在左側 69px gutter，時間戳在正文上方 |
| 訊息回合 | 平面、逐回合細線 | 不使用 chat bubble 或大卡片 |
| Composer | max 820，x≈320..1140，y≈614 | 中央對齊；paperclip、輸入、金色送出在同行 |
| Composer 鍵盤 | Enter 送出，Shift+Enter 換行 | IME preedit 不提前送出，空白不可送出 |
| History | 按需開／關 | 320px overlay drawer，關閉不佔正文寬度 |

正文 gutter 不是新的主導覽或 History 欄。長文字保留可捲動與任意長字串換行；composer 多行時在 44..92px 間增高。

## 圖 B：Settings 幾何

| 元素 | 圖 B 基準 | Qt 實作約束 |
| --- | --- | --- |
| 主底色 | `#101319` | 與 Chat 分模式，但共用文字／分隔線 tokens |
| Icon rail | 約 73 | 固定 73，圖示含 tooltip / accessible name |
| Chrome | 高 52 | 固定 52 |
| 頁首 | CONTROL & PRIVACY、設定，x≈125 | rail 73 + 左 margin 52 |
| Subnav | x=125..351，寬 226 | 226 固定，active 青綠 `#61AB9F` |
| 主內容 | x=393..1230 | subnav 後 gap 42，右 margin 50 |
| 助理設定 | LAUNCHER OWNED | 角色／目前專案／LLM 模型／推理深度 |
| 設定列 | 左文右 dropdown，細分隔線 | dropdown 220，文字自動換行 |
| 動作 | 淺藍按鈕 | `#87A0CE`；V1 動作僅還原示範值 |

六分類依序為：助理、對話與記憶、語音與感知、工具與權限、桌寵與外觀、進階診斷。
保留大片留白；不用 JSON editor 作為主要內容。

## 共用 design tokens

色彩以使用者指定值為優先；其餘從歷史 CSS 與本輪需要的安全狀態衍生，不冒充原圖取樣。

| Token | 精確值 | 用途／來源 |
| --- | --- | --- |
| chat_background | `#10141D` | 圖 A 指定 |
| settings_background | `#101319` | 圖 B 指定／歷史 ink |
| rail_background | `#131823` | 圖 A 指定／歷史 rail |
| chrome_background | `#141924` | 歷史 chrome |
| surface | `#171D28` | 歷史 composer／drawer |
| text | `#E7EAF0` | 歷史 paper |
| muted | `#929BAD` | 歷史 muted |
| quiet | `#727C8D` | 歷史 placeholder |
| line | `#303846` | 歷史 line |
| turn_line | `#252C39` | 歷史 message／setting 分隔線 |
| gold | `#D7B66F` | 圖 A active／送出 |
| teal | `#61AB9F` | 圖 B active |
| blue | `#87A0CE` | 歷史 moon／圖 B 淺藍按鈕 |
| error | `#D99B96` | 歷史錯誤 notice |

排版：主文字 Microsoft JhengHei UI／Segoe UI，品牌 Segoe UI，caption Consolas／Cascadia Mono；全為既有本機字型。
字級：頁標題 25px、品牌 23px、section 18px、訊息 15px、一般控制 14px、輔助 12px、speaker 11px、caption 10px。
邊界：1px 細線、button／dropdown 3px radius、composer 4px radius；無陰影卡片牆。
間距：Chat header 38px、Settings 左 52／右 50、subnav gap 42、一般列 gap 22、speaker gutter 54+15。

所有 QSS 限於 `QWidget#WorkCompanionView` 後代。正式 QApplication theme 不由這個 view 修改。
原生 icon 以 QPainter 本機線條繪製；不用遠端圖片、WebEngine、QtWebChannel、SVG 額外套件或新 UI library。

## 動作與狀態 contract

| 動作／狀態 | V1 行為 |
| --- | --- |
| Chat / Today / Settings | 本機切換頁面，Chat/Today 180 rail，Settings 73 rail |
| History | toggle、關閉、Escape、選合成對話；回到 toggle 焦點 |
| Today | 三筆匿名摘要；點一筆展開原因、下一步、來源與明確合成時間 |
| Settings | 六分類、可用示範 combo、永久 disabled 的未提供能力；選擇只在記憶體 |
| 送出 | 加入本機回合；1.2 秒後固定回覆，不執行文字中的指令 |
| 停止 | 取消本機 QTimer；保留已輸入的回合，不產生遲到回覆 |
| 附件 | 只顯示固定 sample-note.txt 名稱；沒有檔案選取／讀取 |
| loading | 明示示範等待，輸入及設定操作停用，導覽仍可用 |
| partial | 明示不完整並保留現有內容，不補資料 |
| error | 明示示範失敗及恢復入口，不清除可讀內容 |
| disabled | 明示操作停用，頁面仍可閱讀 |
| empty | 顯示空狀態；Chat 可在空白合成 thread 開始一回合 |

三頁常駐 `DEMO / PREVIEW`，並標示 SYNTHETIC／不連線／不保存；沒有「online」或假連線成功。
上述狀態是視覺情境，不是 Core／Conversation／Pet／模型或 provider 的狀態。

## 執行邊界、步驟與完成條件

- V0：讀取 repo AGENTS、四份產品文件、README、Qt source、既有測試與指定 Git 視覺 source；以本檔固定基準與未知項目。
- V1：只新增 view／theme、devtools host／fixtures、tests、任務文件及 synthetic PNG。
- 驗證：syntax、offscreen 互動／版面／狀態／import boundary、373 個既有 source SHA-256、G7 35 路徑不存在、Git tracked diff／index／status 比對。
- 失敗先修復預覽範圍；正式 source／服務／私人 state 不作為繞過方式。
- 原定 docs/agent-runs 新目錄在 sandbox 與審核後命令均被 Windows 拒絕建立；文件與圖片因此改存本任務的 devtools 目錄，沒有變更 ACL。
- V1 source ready 只代表可審核的合成預覽。圖 A/B 的人眼視覺接受、Windows 實機輸入與多螢幕 DPI、正式產品 acceptance、V2 controller 接線均未完成。

成果與指令見 [V1Checkpoint](V1Checkpoint.md)。
