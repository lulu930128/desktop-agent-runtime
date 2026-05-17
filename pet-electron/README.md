# Kuro Pet Electron

這個資料夾是我們自己可控的桌寵殼，目標是逐步取代現成的 `open-llm-vtuber-electron` 成品。

目前第一版做的事情：

- 用我們自己的 Electron `main/preload` 載入既有的 [`C:\kuro\Open-LLM-VTuber\frontend\index.html`](C:\kuro\Open-LLM-VTuber\frontend\index.html)
- 提供前端目前需要的 `window.api` / `window.electron.ipcRenderer` 基礎接口
- 支援 `pet` mode
- 提供滑鼠穿透切換
- 提供系統匣控制
- 保留視窗位置與大小
- 可把桌寵移到下一個螢幕

## 安裝

在 [`C:\kuro\pet-electron`](C:\kuro\pet-electron) 執行：

```powershell
npm install
```

## 啟動

```powershell
npm start
```

## 目前支援的控制

- 系統匣選單
  - 顯示桌寵
  - 切換滑鼠穿透
  - 移到下一個螢幕
  - 重新載入前端
  - 結束

## 第一版範圍

這一版先專注在：

- 自己控制 Electron shell
- 讓既有 frontend 能進 `pet` mode
- 解掉原本主螢幕鎖定的架構問題

後續再往下接：

- launcher 直接啟動這個新 shell
- 更完整的桌寵拖曳/停靠體驗
- 更精細的多螢幕行為
- 專屬 pet UI 與自家 renderer 調整
