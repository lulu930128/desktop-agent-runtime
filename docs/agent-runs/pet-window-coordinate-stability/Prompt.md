# Pet Window Coordinate Stability

## Goal

- 將 Live2D 桌寵收斂成固定 virtual-desktop native shell 與可移動 compact render surface；角色互動只移動 surface／model，不再搬動 BrowserWindow。
- 讓角色位置、臉部游標追蹤、互動命中與螢幕邊界共用一致的 screen / window / model 座標 contract。
- 在雙螢幕排列、拖曳、滑鼠穿透與 runtime 重啟後維持可操作且不阻塞其他桌面視窗。
- 讓滾輪縮放以游標所在的 screen-space 點為固定 pivot，不再只固定腳底而造成視覺中心漂移。

## Non-goals

- 不改 Work Panel、Reader、Briefing、LLM、TTS、角色人格或外部工具 contract。
- 不修改 Live2D moc、texture、physics 或私人 runtime state。
- 不進行新的 Live2D 視覺設計或大型 Electron shell 重寫。

## Hard constraints

- Pet 仍維持 transparent、topmost、non-focusable，且透明區域預設穿透。
- 多螢幕幾何必須依實際 display work-area 集合選擇最近 host sizing context；anchor 本身允許進入實體螢幕外與顯示器間空洞。
- 主程序是 canonical anchor／zoom 與 fixed shell bounds 的唯一 owner；renderer surface bounds 只能由 canonical transform、dynamic visual bounds 與 shell origin 衍生，不能成為第二個 authoritative writer。
- 正常 drag、zoom、motion、expression、outfit 與 model envelope 不得觸發 native BrowserWindow relocation；只有 startup、mode switch、display topology 與 recovery 可改 fixed shell bounds。
- 主程序持有唯一的 `PetTransformState { revision, anchor, zoomScale }`；renderer 只送操作意圖，不能先行提交 canonical transform。
- transform、host viewport 與 model envelope 必須攜帶 revision；缺少、過期或不相符的訊息一律不得覆寫較新的幾何狀態。
- 角色 placement 使用不隨 motion／expression／outfit 改變的 stable bounds；dynamic visual bounds 只可調整透明 host envelope。
- 同一 render frame 的 anchor placement、model screen bounds 與 debug overlay 必須共用同一份 actual canvas viewport snapshot；pointer event 也必須每次只取得一份 observation。
- 模型互動區不得回退成所有可見 drawable 的外接矩形聯集。
- 實際 runtime 驗收只重啟 Pet shell，不影響 LLM、TTS 或其他服務。

## Context

- Repo: `C:\project\kuro`
- Related systems: Electron main process、custom renderer、Live2D Cubism runtime、Pet control endpoint `127.0.0.1:23567`
- Current known state: 舊 runtime 使用 `5120 x 1526` 全虛擬桌面 host；主程序與 renderer anchor 曾分叉 66 px；小黑模型沒有 model3 `HitAreas`。

## Deliverables

- 可單元測試的 display / anchor / model-bounds host envelope geometry helper。
- 小型跟隨式 Pet host window 與主程序 authoritative anchor round-trip。
- main-process 全域游標 feed，以及 renderer 的 model-relative 單一路徑 look tracking。
- main-owned transform request／revision contract，以及 host-only command path。
- stable placement bounds 與 dynamic visual envelope 的雙軌幾何 contract。
- 可單元測試的 actual canvas viewport geometry helper，以及 expected／actual／native bounds diagnostics。
- 可透過 process-scoped environment flag 啟閉的 native host relocation freeze A/B proof 與 status telemetry。
- fixed desktop shell geometry／native write guard，以及不等於 shell 尺寸的 compact WebGL surface。
- transparent click-through interaction lease；renderer 卡死、load failure 或 lease 過期時必須 fail closed 回 passthrough。
- Kuro-owned face-look profile 與 visible drawable mesh hit test。
- mouse recovery、geometry、typecheck、build 與 live runtime 驗收證據。

## Done criteria

- Pet native shell 固定為 physical display bounds union；Live2D canvas 維持 compact，不能等於整個 virtual desktop framebuffer。
- 不同高度顯示器的外接矩形空洞不得被誤認為 display，但可作為使用者主動移入的 offscreen anchor。
- 主程序 `/status.petAnchor` 與 `/live2d-inspector.snapshot.anchorScreenPoint` 一致。
- 透明區域不會長期阻塞底下視窗；拖曳結束或失去 pointer 時能恢復穩定狀態。
- 臉部追蹤以模型臉部中心為基準，且不再同時疊加兩套 look controller。
- 平常不追蹤游標；只有按住／拖曳角色時才看向游標，放開後回正。
- 角色向下拖曳不受 work-area 底部限制；tray 與工作面板必須提供可用的重置位置救援入口。
- 放大時 compact render surface 依模型實際邊界與 safety padding 擴張，不設 display 尺寸上限；fixed native shell 不隨角色互動改變，透明區仍維持 click-through。
- 滾輪縮放時，renderer 與 main process 必須用同一筆 zoom／anchor 幾何更新維持游標 pivot；角色仍可依使用者操作部分移出 work area。
- 快速連續縮放、反向縮放與 host resize 訊息交錯時，revision 必須保持單調，過期回覆不得造成位置回跳。
- motion、expression 與 outfit 的可見邊界變化可以改變 host envelope，但不能改變角色腳底與水平中心 placement。
- cached expected host 更新、native host move／resize 與 lazy shrink 都不能改變相同 canonical transform 的 global stable anchor。
- anchor、pointer、screen hit test、canvas→screen 與 model screen bounds 必須走唯一 actual canvas viewport source；DIP path 不二次套用 DPR／display scaleFactor。
- targeted tests、Electron syntax、renderer typecheck/build 與 scoped live acceptance 通過。
- Freeze OFF／ON 使用相同 renderer、模型與幾何 contract；唯一變因是互動期間是否允許 native `BrowserWindow.setBounds()`。
- `KURO_PET_FIXED_DESKTOP_SHELL=0` 保留 v6 rollback；完成 Q3／Q4 live acceptance 前不得刪除舊 relocation／Freeze 路徑。

## Open questions / assumptions

- 本輪以 current Kuro 模型比例提供 face-look profile；碰撞命中改由各模型自己的可見 drawable 三角 mesh 決定。
- 當角色在極端 zoom 下大於實體螢幕時，允許模型自然穿出實體螢幕；BrowserWindow 可大於單一 display，但不可在螢幕內留下 host 自身造成的硬裁切線。
