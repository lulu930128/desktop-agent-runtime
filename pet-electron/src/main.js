const path = require("path");
const fs = require("fs");
const http = require("http");
const {
  app,
  BrowserWindow,
  Menu,
  Tray,
  desktopCapturer,
  ipcMain,
  nativeImage,
  screen
} = require("electron");

const { cloneDefaultState, loadState, mergeState, saveState } = require("./state");

const APP_NAME = "Kuro Pet Electron";
const MODE_CHANGE_TIMEOUT_MS = 2200;
const CONTROL_HOST = process.env.KURO_PET_CONTROL_HOST || "127.0.0.1";
const CONTROL_PORT = Number(process.env.KURO_PET_CONTROL_PORT || "23567");

const repoRoot = path.resolve(__dirname, "..", "..");
const frontendEntry = path.join(repoRoot, "Open-LLM-VTuber", "frontend", "index.html");
const rendererEntry = path.join(repoRoot, "pet-electron", "renderer-dist", "index.html");
const iconPath = path.join(repoRoot, "Open-LLM-VTuber", "frontend", "favicon.ico");
const readerEntry = path.join(__dirname, "reader-window.html");
const readerPreloadPath = path.join(__dirname, "reader-preload.js");

let mainWindow = null;
let readerWindow = null;
let tray = null;
let appState = cloneDefaultState();
let statePath = "";
let hoveredComponents = new Map();
let activeWindowDrag = null;
let controlServer = null;
let latestFrontendState = {
  wsConnected: false,
  aiState: "idle",
  latestAssistantText: "",
  latestUserText: "",
  wsUrl: process.env.KURO_BACKEND_WS_URL || "",
  baseUrl: process.env.KURO_BACKEND_BASE_URL || ""
};

function shouldUseCustomRenderer() {
  return fs.existsSync(rendererEntry);
}

function getRendererEntryPath() {
  return shouldUseCustomRenderer() ? rendererEntry : frontendEntry;
}

function petLog(...parts) {
  const line = `[${new Date().toISOString()}] ${parts
    .map((part) => {
      if (part instanceof Error) {
        return `${part.message}\n${part.stack || ""}`;
      }
      if (typeof part === "string") {
        return part;
      }
      try {
        return JSON.stringify(part);
      } catch {
        return String(part);
      }
    })
    .join(" ")}`;

  console.log(line);

  if (!app.isReady()) {
    return;
  }

  try {
    const logPath = path.join(app.getPath("userData"), "pet-shell.log");
    fs.appendFileSync(logPath, `${line}\n`, "utf8");
  } catch (error) {
    console.warn("[pet-electron] Failed to write log file:", error);
  }
}

function saveCurrentState() {
  if (!statePath) {
    return;
  }
  saveState(statePath, appState);
}

function setBoundsForCurrentMode(bounds) {
  appState.boundsByMode[appState.mode] = {
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height
  };
  saveCurrentState();
}

function getWindowBoundsForMode(mode) {
  return appState.boundsByMode[mode] || appState.boundsByMode.pet;
}

function getReaderBounds() {
  return appState.readerBounds || cloneDefaultState().readerBounds;
}

function setReaderBounds(bounds) {
  appState.readerBounds = {
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height
  };
  saveCurrentState();
}

function resetPetBoundsToDefault() {
  const defaults = cloneDefaultState().boundsByMode.pet;
  const primaryArea = screen.getPrimaryDisplay().workArea;

  appState.boundsByMode.pet = {
    x: primaryArea.x + defaults.x,
    y: primaryArea.y + defaults.y,
    width: defaults.width,
    height: defaults.height
  };
}

function getAllDisplays() {
  return screen.getAllDisplays().sort((a, b) => a.bounds.x - b.bounds.x || a.bounds.y - b.bounds.y);
}

function getVirtualWorkAreaBounds() {
  const displays = getAllDisplays();
  if (!displays.length) {
    return { x: 0, y: 0, width: 1280, height: 720 };
  }

  const areas = displays.map((display) => display.workArea);
  const left = Math.min(...areas.map((area) => area.x));
  const top = Math.min(...areas.map((area) => area.y));
  const right = Math.max(...areas.map((area) => area.x + area.width));
  const bottom = Math.max(...areas.map((area) => area.y + area.height));

  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top)
  };
}

function findDisplayForBounds(bounds) {
  const point = {
    x: bounds.x + Math.round(bounds.width / 2),
    y: bounds.y + Math.round(bounds.height / 2)
  };
  return screen.getDisplayNearestPoint(point);
}

function clampBoundsToDisplay(bounds, display) {
  const area = display.workArea;
  const width = Math.min(bounds.width, area.width);
  const height = Math.min(bounds.height, area.height);

  return {
    x: Math.min(Math.max(bounds.x, area.x), area.x + area.width - width),
    y: Math.min(Math.max(bounds.y, area.y), area.y + area.height - height),
    width,
    height
  };
}

function clampBoundsToVirtualDesktop(bounds) {
  const area = getVirtualWorkAreaBounds();
  const width = Math.min(bounds.width, area.width);
  const height = Math.min(bounds.height, area.height);

  return {
    x: Math.min(Math.max(bounds.x, area.x), area.x + area.width - width),
    y: Math.min(Math.max(bounds.y, area.y), area.y + area.height - height),
    width,
    height
  };
}

function clampBoundsToVirtualDesktopWithOverflow(bounds, visibleMargin = 120) {
  const area = getVirtualWorkAreaBounds();
  const width = Math.min(bounds.width, area.width);
  const height = Math.min(bounds.height, area.height);
  const minVisibleX = Math.max(64, Math.min(visibleMargin, width));
  const minVisibleY = Math.max(64, Math.min(visibleMargin, height));

  return {
    x: Math.min(
      Math.max(bounds.x, area.x - width + minVisibleX),
      area.x + area.width - minVisibleX
    ),
    y: Math.min(
      Math.max(bounds.y, area.y - height + minVisibleY),
      area.y + area.height - minVisibleY
    ),
    width,
    height
  };
}

function clampReaderBounds(bounds) {
  return clampBoundsToVirtualDesktopWithOverflow(bounds, 160);
}

function resolveTargetBoundsForMode(mode) {
  if (mode === "pet" && appState.petSpanAllDisplays) {
    return getVirtualWorkAreaBounds();
  }

  const requestedBounds = getWindowBoundsForMode(mode);
  if (mode === "pet") {
    return clampBoundsToVirtualDesktopWithOverflow(requestedBounds);
  }

  return clampBoundsToDisplay(requestedBounds, findDisplayForBounds(requestedBounds));
}

function applyIgnoreMouseState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const shouldIgnore =
    appState.mode === "pet" &&
    appState.forceIgnoreMouse &&
    !Array.from(hoveredComponents.values()).some(Boolean);

  mainWindow.setIgnoreMouseEvents(shouldIgnore, { forward: true });
}

function getReaderStatePayload() {
  return {
    ok: true,
    aiState: latestFrontendState.aiState || "idle",
    wsConnected: Boolean(latestFrontendState.wsConnected),
    latestAssistantText: latestFrontendState.latestAssistantText || "",
    latestUserText: latestFrontendState.latestUserText || "",
    wsUrl: latestFrontendState.wsUrl || "",
    baseUrl: latestFrontendState.baseUrl || "",
    readerVisible: Boolean(readerWindow && !readerWindow.isDestroyed() && readerWindow.isVisible())
  };
}

function broadcastReaderState() {
  if (!readerWindow || readerWindow.isDestroyed()) {
    return;
  }
  try {
    readerWindow.webContents.send("reader-state", getReaderStatePayload());
  } catch (error) {
    petLog("reader-state-broadcast-failed", error);
  }
}

function updateFrontendState(patch = {}) {
  latestFrontendState = {
    ...latestFrontendState,
    ...(patch || {})
  };
  broadcastReaderState();
}

function broadcast(channel, payload) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send(channel, payload);
}

async function executeRenderer(code) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return null;
  }
  try {
    return await mainWindow.webContents.executeJavaScript(code, true);
  } catch (error) {
    petLog("execute-renderer-failed", error);
    return null;
  }
}

async function readRendererStatus() {
  return (
    (await executeRenderer(`(() => {
      if (window.__kuroPetRendererState) {
        return {
          mode: "custom-renderer",
          ...window.__kuroPetRendererState
        };
      }

      const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
      const parseStored = (key) => {
        const raw = window.localStorage.getItem(key);
        if (!raw) return "";
        try {
          return String(JSON.parse(raw) || "");
        } catch {
          return String(raw || "");
        }
      };

      const visibleTextNodes = Array.from(document.querySelectorAll("body *"))
        .map((node) => normalize(node.innerText || node.textContent || ""))
        .filter(Boolean);

      const buttonTexts = Array.from(document.querySelectorAll("button"))
        .map((button) => normalize(button.innerText || button.textContent || ""))
        .filter(Boolean)
        .slice(0, 24);

      const knownStates = new Set([
        "idle",
        "thinking/speaking",
        "interrupted",
        "loading",
        "listening",
        "waiting",
        "空闲",
        "空閒",
        "思考/说话中",
        "思考/說話中",
        "已打断",
        "已打斷",
        "加载中",
        "載入中",
        "聆听中",
        "聆聽中",
        "等待中"
      ]);

      const knownWs = new Set([
        "Connected",
        "Connecting",
        "Click to Reconnect",
        "已连接",
        "已連接",
        "连接中",
        "連線中",
        "点击重新连接",
        "點擊重新連線"
      ]);

      const aiState = visibleTextNodes.find((text) => knownStates.has(text)) || "";
      const wsBadge = visibleTextNodes.find((text) => knownWs.has(text)) || "";

      return {
        href: location.href,
        baseUrl: parseStored("baseUrl"),
        wsUrl: parseStored("wsUrl"),
        aiState,
        wsBadge,
        buttonTexts
      };
    })();`)) || {}
  );
}

async function applyRendererBackendConfig(baseUrl, wsUrl, reload = true) {
  const payload = await executeRenderer(`((baseUrlValue, wsUrlValue, shouldReconnect) => {
    if (typeof window.__kuroPetApplyBackendConfig === "function") {
      return window.__kuroPetApplyBackendConfig(baseUrlValue, wsUrlValue, shouldReconnect);
    }

    const writeValue = (key, value) => {
      if (!value) return;
      window.localStorage.setItem(key, JSON.stringify(String(value)));
    };
    writeValue("baseUrl", baseUrlValue);
    writeValue("wsUrl", wsUrlValue);
    return {
      baseUrl: baseUrlValue || "",
      wsUrl: wsUrlValue || ""
    };
  })(${JSON.stringify(baseUrl || "")}, ${JSON.stringify(wsUrl || "")}, ${JSON.stringify(Boolean(reload))});`);

  if (!shouldUseCustomRenderer() && reload && mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.reloadIgnoringCache();
  }
  updateFrontendState({
    baseUrl: baseUrl || latestFrontendState.baseUrl,
    wsUrl: wsUrl || latestFrontendState.wsUrl
  });
  return payload || {};
}

async function sendTextToFrontend(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return { ok: false, error: "empty-text" };
  }

  const result =
    (await executeRenderer(`((rawText) => {
      const text = String(rawText || "").trim();
      if (!text) {
        return { ok: false, error: "empty-text" };
      }

      if (typeof window.__kuroPetSendTextInput === "function") {
        return window.__kuroPetSendTextInput(text);
      }

      return { ok: false, error: "frontend-bridge-missing" };
    })(${JSON.stringify(normalized)});`)) || { ok: false, error: "renderer-unavailable" };

  if (result.ok) {
    updateFrontendState({
      latestUserText: normalized,
      aiState: "thinking"
    });
  }

  return result;
}

async function clickRendererButtonByText(candidates) {
  if (shouldUseCustomRenderer()) {
    return {
      ok: false,
      error: "unsupported-in-custom-renderer",
      candidates
    };
  }

  return (
    (await executeRenderer(`((candidates) => {
      const normalizedCandidates = (Array.isArray(candidates) ? candidates : [])
        .map((value) => String(value || "").toLowerCase().replace(/\\s+/g, " ").trim())
        .filter(Boolean);
      const buttons = Array.from(document.querySelectorAll("button"));
      const normalize = (value) => String(value || "").toLowerCase().replace(/\\s+/g, " ").trim();

      for (const button of buttons) {
        const text = normalize(button.innerText || button.textContent || "");
        if (!text) continue;
        if (normalizedCandidates.some((candidate) => text.includes(candidate))) {
          button.click();
          return { ok: true, text };
        }
      }

      return {
        ok: false,
        buttons: buttons
          .map((button) => normalize(button.innerText || button.textContent || ""))
          .filter(Boolean)
      };
    })(${JSON.stringify(candidates || [])});`)) || { ok: false }
  );
}

async function handleControlAction(action) {
  switch (action) {
    case "mic-toggle":
      broadcast("pet-command", { type: "mic-toggle" });
      return { ok: true, route: "ipc", action };
    case "interrupt":
      broadcast("pet-command", { type: "interrupt" });
      return { ok: true, route: "ipc", action };
    case "toggle-subtitle":
      if (!readerWindow || readerWindow.isDestroyed()) {
        appState.readerVisible = true;
        createReaderWindow();
      } else if (readerWindow.isVisible()) {
        readerWindow.hide();
      } else {
        readerWindow.show();
        readerWindow.focus();
      }
      updateTrayMenu();
      return { ok: true, route: "window", action };
    case "toggle-camera":
      return clickRendererButtonByText(["camera", "攝像頭", "摄像头", "攝影機"]);
    case "toggle-screen":
      return clickRendererButtonByText(["screen", "螢幕", "屏幕", "屏幕共享"]);
    case "toggle-browser":
      return clickRendererButtonByText(["browser", "瀏覽器", "浏览器"]);
    case "reload-frontend":
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.reloadIgnoringCache();
      }
      return { ok: true, action };
    case "show-pet":
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.show();
        mainWindow.focus();
      }
      return { ok: true, action };
    case "move-next-display":
      moveWindowToNextDisplay();
      return { ok: true, action };
    default:
      return { ok: false, error: `Unknown action: ${action}` };
  }
}

async function configurePetShellRenderer() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  await mainWindow.webContents.insertCSS(`
    html,
    body,
    #root {
      background: transparent !important;
    }

    body {
      overflow: hidden !important;
    }

    img[alt="background"],
    video {
      display: none !important;
    }

    #live2d,
    #canvas,
    canvas {
      pointer-events: auto !important;
      cursor: grab !important;
    }
  `);

  await mainWindow.webContents.executeJavaScript(
    `(() => {
      document.documentElement.dataset.kuroPetShell = "1";

      if (!window.__kuroPetWindowDragBound) {
        window.__kuroPetWindowDragBound = true;

        let isDraggingWindow = false;

        const beginWindowDrag = (event) => {
          if (!window.api?.startWindowDrag || event.button !== 0) {
            return;
          }

          isDraggingWindow = true;
          event.preventDefault();
          event.stopPropagation();
          window.api.startWindowDrag(event.screenX, event.screenY);
        };

        const moveWindowDrag = (event) => {
          if (!isDraggingWindow) {
            return;
          }
          event.preventDefault();
          window.api.updateWindowDrag?.(event.screenX, event.screenY);
        };

        const endWindowDrag = () => {
          if (!isDraggingWindow) {
            return;
          }
          isDraggingWindow = false;
          window.api.endWindowDrag?.();
        };

        window.addEventListener("pointermove", moveWindowDrag, true);
        window.addEventListener("pointerup", endWindowDrag, true);
        window.addEventListener("pointercancel", endWindowDrag, true);
        window.addEventListener("blur", endWindowDrag, true);

        const bindStageDrag = () => {
          const live2dRoot =
            document.querySelector("#live2d canvas") ||
            document.getElementById("live2d") ||
            document.getElementById("canvas") ||
            document.querySelector("canvas");

          if (!live2dRoot || live2dRoot.dataset.kuroPetDragBound === "1") {
            return Boolean(live2dRoot);
          }

          live2dRoot.dataset.kuroPetDragBound = "1";
          live2dRoot.style.pointerEvents = "auto";
          live2dRoot.addEventListener("pointerdown", beginWindowDrag, true);
          return true;
        };

        const hideAncestorCard = (node, minWidth = 220, minHeight = 50, maxDepth = 8) => {
          let current = node;
          let chosen = null;
          for (let depth = 0; depth < maxDepth && current; depth += 1) {
            const rect = current.getBoundingClientRect();
            if (rect.width >= minWidth && rect.height >= minHeight) {
              chosen = current;
            }
            current = current.parentElement;
          }
          if (!chosen) {
            return false;
          }
          chosen.dataset.kuroPetLegacyOverlay = "1";
          chosen.style.display = "none";
          chosen.style.opacity = "0";
          chosen.style.pointerEvents = "none";
          return true;
        };

        const trimLegacyUi = () => {
          const candidates = Array.from(document.querySelectorAll("input, textarea"));
          for (const node of candidates) {
            const placeholder = String(node.getAttribute("placeholder") || "").toLowerCase();
            if (
              placeholder.includes("type your message") ||
              placeholder.includes("輸入") ||
              placeholder.includes("message")
            ) {
              hideAncestorCard(node, 260, 80, 8);
            }
          }

          const allNodes = Array.from(document.querySelectorAll("body *"));
          for (const node of allNodes) {
            const text = String(node.textContent || "").replace(/\s+/g, " ").trim();
            if (!text) {
              continue;
            }
            if (text === "Open LLM VTuber" || text === "Connected" || text === "已連接") {
              hideAncestorCard(node, 120, 24, 6);
            }
          }

          const live2dRoot = document.getElementById("live2d");
          if (live2dRoot) {
            live2dRoot.style.pointerEvents = "auto";
            live2dRoot.style.background = "transparent";
            live2dRoot.style.zIndex = "20";
          }

          const canvas = document.querySelector("#live2d canvas") || document.querySelector("canvas");
          if (canvas) {
            canvas.style.pointerEvents = "auto";
            canvas.style.cursor = "grab";
            canvas.style.zIndex = "20";
          }
        };

        if (!bindStageDrag()) {
          const retry = setInterval(() => {
            if (bindStageDrag()) {
              clearInterval(retry);
            }
            trimLegacyUi();
          }, 350);
        }
        trimLegacyUi();
      }

      if (!window.__kuroPetLegacyUiHidden) {
        window.__kuroPetLegacyUiHidden = true;

        const hideLegacyOverlay = () => {
          const targets = Array.from(document.querySelectorAll("input, textarea"))
            .filter((node) => {
              const placeholder = String(node.getAttribute("placeholder") || "").toLowerCase();
              return (
                placeholder.includes("type your message") ||
                placeholder.includes("message") ||
                placeholder.includes("輸入")
              );
            });

          for (const input of targets) {
            let candidate = input;
            let chosen = null;
            for (let depth = 0; depth < 8 && candidate; depth += 1) {
              const rect = candidate.getBoundingClientRect();
              if (rect.width >= 260 && rect.height >= 80) {
                chosen = candidate;
              }
              candidate = candidate.parentElement;
            }
            if (chosen) {
              chosen.dataset.kuroPetLegacyOverlay = "1";
              chosen.style.display = "none";
              chosen.style.opacity = "0";
              chosen.style.pointerEvents = "none";
            }
          }
        };

        hideLegacyOverlay();
        const overlayObserver = new MutationObserver(() => hideLegacyOverlay());
        overlayObserver.observe(document.body, {
          subtree: true,
          childList: true,
          attributes: true
        });
      }
    })();`,
    true
  );
}

function waitForRendererSignal(channel, predicate = () => true) {
  return new Promise((resolve) => {
    let finished = false;

    const cleanup = (result) => {
      if (finished) {
        return;
      }
      finished = true;
      clearTimeout(timer);
      ipcMain.removeListener(channel, handler);
      resolve(result);
    };

    const handler = (_event, ...args) => {
      if (predicate(...args)) {
        cleanup(true);
      }
    };

    const timer = setTimeout(() => cleanup(false), MODE_CHANGE_TIMEOUT_MS);
    ipcMain.on(channel, handler);
  });
}

async function syncRendererMode(mode) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  hoveredComponents = new Map();
  mainWindow.webContents.send("pre-mode-changed", mode);
  await waitForRendererSignal("renderer-ready-for-mode-change", (incomingMode) => incomingMode === mode);

  mainWindow.webContents.send("mode-changed", mode);
  await waitForRendererSignal("mode-change-rendered");

  mainWindow.webContents.send("force-ignore-mouse-changed", appState.forceIgnoreMouse);
  applyIgnoreMouseState();
}

function applyWindowMode(mode, { force = false } = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const nextMode = mode === "window" ? "window" : "pet";
  if (!force && appState.mode === nextMode) {
    return;
  }

  appState.mode = nextMode;
  const targetBounds = resolveTargetBoundsForMode(nextMode);

  if (nextMode === "pet") {
    mainWindow.setAlwaysOnTop(true, "screen-saver");
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    mainWindow.setSkipTaskbar(true);
    mainWindow.setResizable(false);
    mainWindow.setMinimumSize(320, 520);
  } else {
    mainWindow.setAlwaysOnTop(false);
    mainWindow.setVisibleOnAllWorkspaces(false);
    mainWindow.setSkipTaskbar(false);
    mainWindow.setResizable(true);
    mainWindow.setMinimumSize(960, 640);
  }

  mainWindow.setBounds(targetBounds, false);
  saveCurrentState();
  applyIgnoreMouseState();
  updateTrayMenu();
}

function refreshLayoutForDisplayTopology(reason = "display-metrics-changed") {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const targetBounds = resolveTargetBoundsForMode(appState.mode);
  mainWindow.setBounds(targetBounds, false);
  setBoundsForCurrentMode(targetBounds);
  petLog("display-topology-refresh", { reason, mode: appState.mode, targetBounds });
}

function moveWindowToNextDisplay() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  if (appState.mode === "pet" && appState.petSpanAllDisplays) {
    refreshLayoutForDisplayTopology("move-to-next-display-while-spanned");
    return;
  }

  const displays = getAllDisplays();
  if (displays.length < 2) {
    return;
  }

  const currentDisplay = findDisplayForBounds(mainWindow.getBounds());
  const currentIndex = displays.findIndex((item) => item.id === currentDisplay.id);
  const nextDisplay = displays[(currentIndex + 1) % displays.length];
  const currentBounds = mainWindow.getBounds();

  const offsetX = currentBounds.x - currentDisplay.workArea.x;
  const offsetY = currentBounds.y - currentDisplay.workArea.y;
  const nextBounds = clampBoundsToDisplay(
    {
      x: nextDisplay.workArea.x + offsetX,
      y: nextDisplay.workArea.y + offsetY,
      width: currentBounds.width,
      height: currentBounds.height
    },
    nextDisplay
  );

  mainWindow.setBounds(nextBounds, false);
  setBoundsForCurrentMode(nextBounds);
}

function updateTrayMenu() {
  if (!tray) {
    return;
  }

  const menu = Menu.buildFromTemplate([
    {
      label: "顯示桌寵",
      click: () => {
        if (!mainWindow) {
          return;
        }
        mainWindow.show();
        mainWindow.focus();
      }
    },
    {
      label: appState.forceIgnoreMouse ? "關閉滑鼠穿透" : "開啟滑鼠穿透",
      click: () => {
        appState.forceIgnoreMouse = !appState.forceIgnoreMouse;
        saveCurrentState();
        applyIgnoreMouseState();
        broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
        updateTrayMenu();
      }
    },
    {
      label: appState.readerVisible ? "隱藏閱讀框" : "顯示閱讀框",
      click: () => {
        if (!readerWindow || readerWindow.isDestroyed()) {
          appState.readerVisible = true;
          createReaderWindow();
          return;
        }
        if (readerWindow.isVisible()) {
          readerWindow.hide();
        } else {
          readerWindow.show();
          readerWindow.focus();
        }
      }
    },
    {
      label: "移到下一個螢幕",
      click: () => moveWindowToNextDisplay()
    },
    {
      label: "重新載入前端",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.reloadIgnoringCache();
        }
      }
    },
    { type: "separator" },
    {
      label: "結束",
      click: () => {
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(menu);
  tray.setToolTip(`${APP_NAME} (${appState.mode})`);
}

function showPetContextMenu() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const menu = Menu.buildFromTemplate([
    {
      label: appState.forceIgnoreMouse ? "關閉滑鼠穿透" : "開啟滑鼠穿透",
      click: () => {
        appState.forceIgnoreMouse = !appState.forceIgnoreMouse;
        saveCurrentState();
        applyIgnoreMouseState();
        broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
        updateTrayMenu();
      }
    },
    {
      label: appState.readerVisible ? "隱藏閱讀框" : "顯示閱讀框",
      click: () => {
        if (!readerWindow || readerWindow.isDestroyed()) {
          appState.readerVisible = true;
          createReaderWindow();
          return;
        }
        if (readerWindow.isVisible()) {
          readerWindow.hide();
        } else {
          readerWindow.show();
          readerWindow.focus();
        }
      }
    },
    {
      label: "移到下一個螢幕",
      click: () => moveWindowToNextDisplay()
    },
    {
      label: "重新載入前端",
      click: () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.reloadIgnoringCache();
        }
      }
    },
    { type: "separator" },
    {
      label: "結束",
      click: () => {
        app.quit();
      }
    }
  ]);

  menu.popup({ window: mainWindow });
}

function writeJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(payload));
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > 1024 * 256) {
        reject(new Error("Request body too large."));
        req.destroy();
      }
    });
    req.on("end", () => resolve(raw));
    req.on("error", reject);
  });
}

function startControlServer() {
  if (controlServer) {
    return;
  }

  controlServer = http.createServer(async (req, res) => {
    const requestUrl = new URL(req.url || "/", `http://${CONTROL_HOST}:${CONTROL_PORT}`);

    try {
      if (req.method === "GET" && requestUrl.pathname === "/status") {
        const renderer = await readRendererStatus();
        writeJson(res, 200, {
          ok: true,
          mode: appState.mode,
          forceIgnoreMouse: appState.forceIgnoreMouse,
          petSpanAllDisplays: appState.petSpanAllDisplays,
          bounds: mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : null,
          renderer
        });
        return;
      }

      if (req.method === "POST" && requestUrl.pathname === "/command") {
        const raw = await readRequestBody(req);
        const payload = raw ? JSON.parse(raw) : {};
        const action = String(payload.action || "").trim();
        const result = await handleControlAction(action);
        const renderer = await readRendererStatus();
        writeJson(res, 200, {
          ok: Boolean(result && result.ok),
          message: result && result.ok ? `command ${action} dispatched` : result.error || "command failed",
          action,
          result,
          renderer
        });
        return;
      }

      if (req.method === "POST" && requestUrl.pathname === "/backend-config") {
        const raw = await readRequestBody(req);
        const payload = raw ? JSON.parse(raw) : {};
        const baseUrl = String(payload.baseUrl || "").trim();
        const wsUrl = String(payload.wsUrl || "").trim();
        const reload = payload.reload !== false;
        const result = await applyRendererBackendConfig(baseUrl, wsUrl, reload);
        const renderer = await readRendererStatus();
        writeJson(res, 200, {
          ok: true,
          message: reload ? "backend config updated and frontend reloaded" : "backend config updated",
          result,
          renderer
        });
        return;
      }

      writeJson(res, 404, {
        ok: false,
        error: "Not found"
      });
    } catch (error) {
      petLog("control-server-error", error);
      writeJson(res, 500, {
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  });

  controlServer.on("error", (error) => {
    petLog("control-server-listen-error", error);
  });

  controlServer.listen(CONTROL_PORT, CONTROL_HOST, () => {
    petLog("control-server-ready", {
      host: CONTROL_HOST,
      port: CONTROL_PORT
    });
  });
}

function createTray() {
  if (tray) {
    return;
  }

  const trayIcon = nativeImage.createFromPath(iconPath);
  tray = new Tray(trayIcon);
  tray.on("double-click", () => {
    if (!mainWindow) {
      return;
    }
    mainWindow.show();
    mainWindow.focus();
  });
  updateTrayMenu();
}

function createReaderWindow() {
  if (readerWindow && !readerWindow.isDestroyed()) {
    if (appState.readerVisible) {
      readerWindow.show();
      readerWindow.focus();
    }
    return;
  }

  const bounds = clampReaderBounds(getReaderBounds());
  readerWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    minWidth: 340,
    minHeight: 180,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    resizable: true,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    alwaysOnTop: true,
    title: `${APP_NAME} Reader`,
    icon: iconPath,
    autoHideMenuBar: true,
    webPreferences: {
      preload: readerPreloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false
    }
  });

  readerWindow.setMenuBarVisibility(false);
  readerWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  readerWindow.setSkipTaskbar(true);

  readerWindow.on("move", () => {
    if (!readerWindow || readerWindow.isDestroyed()) {
      return;
    }
    setReaderBounds(readerWindow.getBounds());
  });

  readerWindow.on("resize", () => {
    if (!readerWindow || readerWindow.isDestroyed()) {
      return;
    }
    setReaderBounds(readerWindow.getBounds());
  });

  readerWindow.on("show", () => {
    appState.readerVisible = true;
    saveCurrentState();
    broadcastReaderState();
    updateTrayMenu();
  });

  readerWindow.on("hide", () => {
    appState.readerVisible = false;
    saveCurrentState();
    broadcastReaderState();
    updateTrayMenu();
  });

  readerWindow.on("closed", () => {
    readerWindow = null;
  });

  readerWindow.webContents.on("did-finish-load", () => {
    broadcastReaderState();
    if (appState.readerVisible) {
      readerWindow.show();
      readerWindow.focus();
    }
  });

  readerWindow.loadFile(readerEntry).catch((error) => {
    petLog("Failed to load reader window", error);
  });
}

function createWindow() {
  const bounds = resolveTargetBoundsForMode(appState.mode);
  const entryPath = getRendererEntryPath();
  const usingCustomRenderer = shouldUseCustomRenderer();

  mainWindow = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    minWidth: 320,
    minHeight: 520,
    transparent: true,
    backgroundColor: "#00000000",
    frame: false,
    show: false,
    resizable: false,
    fullscreenable: false,
    title: APP_NAME,
    icon: iconPath,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false
    }
  });

  petLog("Creating window", {
    entryPath,
    usingCustomRenderer,
    mode: appState.mode,
    bounds,
    petSpanAllDisplays: appState.petSpanAllDisplays,
    backendBaseUrl: process.env.KURO_BACKEND_BASE_URL || null,
    backendWsUrl: process.env.KURO_BACKEND_WS_URL || null
  });

  mainWindow.setMenuBarVisibility(false);
  applyWindowMode(appState.mode, { force: true });

  mainWindow.on("move", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      setBoundsForCurrentMode(mainWindow.getBounds());
    }
  });

  mainWindow.on("resize", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      setBoundsForCurrentMode(mainWindow.getBounds());
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.on("maximize", () => broadcast("window-maximized-change", true));
  mainWindow.on("unmaximize", () => broadcast("window-maximized-change", false));
  mainWindow.on("enter-full-screen", () => broadcast("window-fullscreen-change", true));
  mainWindow.on("leave-full-screen", () => broadcast("window-fullscreen-change", false));

  mainWindow.webContents.on("did-finish-load", () => {
    petLog("did-finish-load");
    mainWindow.webContents
      .executeJavaScript(
        `JSON.stringify({
          href: location.href,
          readyState: document.readyState,
          hasApi: !!window.api,
          hasElectron: !!window.electron,
          wsUrl: window.localStorage.getItem("wsUrl"),
          baseUrl: window.localStorage.getItem("baseUrl")
        })`,
        true
      )
      .then((result) => petLog("renderer-diagnostics", result))
      .catch((error) => petLog("renderer-diagnostics-failed", error));

    if (usingCustomRenderer) {
      appState.mode = "pet";
      applyWindowMode("pet", { force: true });
      setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.show();
        }
      }, 180);
      return;
    }

    setTimeout(async () => {
      try {
        appState.mode = "pet";
        applyWindowMode("pet", { force: true });
        await syncRendererMode("pet");
        await configurePetShellRenderer();
      } catch (error) {
        petLog("Initial pet-shell sync failed", error);
      } finally {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.show();
        }
      }
    }, 900);
  });

  mainWindow.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    petLog("renderer-console", { level, message, line, sourceId });
  });

  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL) => {
    petLog("did-fail-load", { errorCode, errorDescription, validatedURL });
  });

  mainWindow.webContents.on(
    "did-fail-provisional-load",
    (_event, errorCode, errorDescription, validatedURL) => {
      petLog("did-fail-provisional-load", { errorCode, errorDescription, validatedURL });
    }
  );

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    petLog("render-process-gone", details);
  });

  mainWindow.webContents.on("unresponsive", () => {
    petLog("renderer-unresponsive");
  });

  mainWindow.webContents.on("before-input-event", (_event, input) => {
    if (input.type !== "keyDown") {
      return;
    }

    if (input.key === "F10") {
      appState.forceIgnoreMouse = !appState.forceIgnoreMouse;
      saveCurrentState();
      applyIgnoreMouseState();
      broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
      updateTrayMenu();
    }

    if (input.key === "F11") {
      moveWindowToNextDisplay();
    }
  });

  mainWindow.loadFile(entryPath).catch((error) => {
    petLog("Failed to load renderer entry", error);
  });
}

function registerIpc() {
  ipcMain.on("pet-frontend-state", (_event, payload) => {
    if (!payload || typeof payload !== "object") {
      return;
    }
    updateFrontendState(payload);
  });

  ipcMain.on("set-mode", async (_event, mode) => {
    const nextMode = mode === "window" ? "window" : "pet";
    applyWindowMode(nextMode);
    saveCurrentState();
    if (!shouldUseCustomRenderer()) {
      await syncRendererMode(nextMode);
    }
  });

  ipcMain.on("toggle-force-ignore-mouse", () => {
    appState.forceIgnoreMouse = !appState.forceIgnoreMouse;
    saveCurrentState();
    applyIgnoreMouseState();
    broadcast("force-ignore-mouse-changed", appState.forceIgnoreMouse);
    updateTrayMenu();
  });

  ipcMain.on("set-ignore-mouse-event", (_event, ignore) => {
    hoveredComponents.set("live2d-hit-test", !ignore);
    applyIgnoreMouseState();
  });

  ipcMain.on("window-close", () => {
    mainWindow?.close();
  });

  ipcMain.on("window-minimize", () => {
    mainWindow?.minimize();
  });

  ipcMain.on("window-maximize", () => {
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  });

  ipcMain.on("window-unfullscreen", () => {
    mainWindow?.setFullScreen(false);
  });

  ipcMain.on("show-context-menu", () => {
    showPetContextMenu();
  });

  ipcMain.handle("reader-get-state", () => getReaderStatePayload());

  ipcMain.handle("reader-send-text", async (_event, text) => {
    return sendTextToFrontend(text);
  });

  ipcMain.on("reader-close", () => {
    if (readerWindow && !readerWindow.isDestroyed()) {
      readerWindow.hide();
    }
  });

  ipcMain.on("update-component-hover", (_event, componentName, hovered) => {
    if (typeof componentName !== "string" || !componentName) {
      return;
    }
    hoveredComponents.set(componentName, Boolean(hovered));
    applyIgnoreMouseState();
  });

  ipcMain.on("start-window-drag", (_event, payload) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    if (!hoveredComponents.get("live2d-model")) {
      return;
    }

    const screenX = Number(payload?.screenX);
    const screenY = Number(payload?.screenY);
    if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) {
      return;
    }

    activeWindowDrag = {
      startCursor: { x: screenX, y: screenY },
      startBounds: mainWindow.getBounds()
    };

    hoveredComponents.set("pet-window-drag", true);
    applyIgnoreMouseState();
  });

  ipcMain.on("update-window-drag", (_event, payload) => {
    if (!mainWindow || mainWindow.isDestroyed() || !activeWindowDrag) {
      return;
    }

    const screenX = Number(payload?.screenX);
    const screenY = Number(payload?.screenY);
    if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) {
      return;
    }

    const deltaX = screenX - activeWindowDrag.startCursor.x;
    const deltaY = screenY - activeWindowDrag.startCursor.y;
    const startBounds = activeWindowDrag.startBounds;

    const nextBounds = clampBoundsToVirtualDesktopWithOverflow({
      x: startBounds.x + deltaX,
      y: startBounds.y + deltaY,
      width: startBounds.width,
      height: startBounds.height
    });

    mainWindow.setBounds(nextBounds, false);
    setBoundsForCurrentMode(nextBounds);
  });

  ipcMain.on("end-window-drag", () => {
    activeWindowDrag = null;
    hoveredComponents.set("pet-window-drag", false);
    applyIgnoreMouseState();
  });

  ipcMain.handle("get-screen-capture", async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender) || mainWindow;
    const bounds = win ? win.getBounds() : getWindowBoundsForMode(appState.mode);
    const currentDisplay =
      appState.mode === "pet" && appState.petSpanAllDisplays
        ? screen.getDisplayNearestPoint(screen.getCursorScreenPoint())
        : findDisplayForBounds(bounds);
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: { width: 0, height: 0 }
    });

    const exactMatch = sources.find((source) => {
      if (source.display_id && Number(source.display_id) === currentDisplay.id) {
        return true;
      }
      return false;
    });

    return (exactMatch || sources[0] || {}).id || "";
  });
}

const singleInstanceLock = app.requestSingleInstanceLock();
if (!singleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    app.setAppUserModelId(APP_NAME);
    statePath = path.join(app.getPath("userData"), "pet-shell-state.json");
    appState = mergeState(loadState(statePath));
    appState.mode = "pet";
    appState.forceIgnoreMouse = true;
    appState.petSpanAllDisplays = false;
    const virtualArea = getVirtualWorkAreaBounds();
    const petBounds = appState.boundsByMode.pet;
    if (
      petBounds.width > 1200 ||
      petBounds.height > 1200 ||
      petBounds.width >= virtualArea.width * 0.85 ||
      petBounds.height >= virtualArea.height * 0.85
    ) {
      resetPetBoundsToDefault();
    }
    saveCurrentState();
    petLog("app-ready", { statePath, appState });

    registerIpc();
    startControlServer();
    createTray();
    createWindow();
    createReaderWindow();

    screen.on("display-added", () => refreshLayoutForDisplayTopology("display-added"));
    screen.on("display-removed", () => refreshLayoutForDisplayTopology("display-removed"));
    screen.on("display-metrics-changed", () =>
      refreshLayoutForDisplayTopology("display-metrics-changed")
    );
  });

  app.on("activate", () => {
    if (!mainWindow) {
      createWindow();
    }
    if (!readerWindow) {
      createReaderWindow();
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("before-quit", () => {
    if (controlServer) {
      try {
        controlServer.close();
      } catch (error) {
        petLog("control-server-close-error", error);
      }
      controlServer = null;
    }
  });
}

