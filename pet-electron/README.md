# Kuro Pet Electron

這個資料夾是我們自己可控的 Kuro 桌寵殼。Electron shell、custom renderer、Live2D runtime 與 Cubism framework 會放在這個專案內維護。

目前第一版做的事情：

- 用我們自己的 Electron `main/preload` 載入 `renderer-dist/index.html`
- 提供 renderer 目前需要的 `window.kuroPetElectron` / `window.api` 基礎接口
- 支援 `pet` mode
- 提供滑鼠穿透切換
- 提供系統匣控制
- 保留視窗位置與大小
- 可把桌寵移到下一個螢幕
- 透過 backend adapter 相容既有訊息協議

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
- 使用專案內的 custom renderer 進 `pet` mode
- 解掉原本主螢幕鎖定的架構問題

後續再往下接：

- launcher 直接啟動這個新 shell
- 更完整的桌寵拖曳/停靠體驗
- 更精細的多螢幕行為
- 專屬 pet UI 與自家 backend protocol
