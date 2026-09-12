# Kuro Electron 桌面介面

本目錄負責工作面板、Live2D 桌寵、Reader／Briefing 相容介面、tray、視窗與本機 control server。日常透過根目錄 VBS 與 Launcher 協同啟動，不再只是第一版 pet mode shell。

## 開發

在本目錄執行，先確認既有 Node.js／npm：

```powershell
npm ci
npm run check:renderer
npm run build:renderer
```

單獨啟動 shell：

```powershell
npm start
```

此命令先 build 再啟動 Electron，不會準備 Launcher、LLM、Bridge 或中央語音。日常操作見[入門指南](../docs/guides/getting-started.md)。

## 責任與資料

- `src/main.js`：視窗、tray、IPC、backend wiring 與生命週期。
- `src/main-process/control-server.js`：Pet control API。
- `src/main-process/briefing-store.js`：snapshot 與 memory candidates。
- `renderer/`：TypeScript／Vite renderer。
- Electron `userData` 保存 local state，`renderer-dist/` 是生成檔。

展示層不擁有市場、記憶政策或工具授權。Mail／study integration 仍有架構債，不能宣稱 Core 已接管。Launcher session token 只留在 main process，不交給 renderer。

不提交 `node_modules/`、`renderer-dist/`、`.tmp/`、userData、模型或私人內容。產品版本以根目錄 `VERSION` 為準，本目錄 package 版本另有用途。

更多見[現況架構](../docs/architecture/RuntimeArchitecture.md)、[開發指南](../docs/guides/development.md)與[故障排查](../docs/guides/troubleshooting.md)。
