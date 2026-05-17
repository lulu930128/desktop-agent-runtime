import "./styles.css";
import { PetLive2DRenderer } from "./live2d/pet-live2d-renderer";

const RENDERER_BUILD_TAG = "custom-renderer-2026-05-17a";
console.info("[pet-renderer] boot", { build: RENDERER_BUILD_TAG });

const originalFetch = window.fetch.bind(window);
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const target =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
  try {
    const response = await originalFetch(input, init);
    console.info("[pet-renderer] fetch", {
      target,
      status: response.status,
      ok: response.ok
    });
    return response;
  } catch (error) {
    console.error("[pet-renderer] fetch failed", {
      target,
      error: error instanceof Error ? error.message : String(error)
    });
    throw error;
  }
};

type RendererState = {
  wsConnected: boolean;
  aiState: string;
  latestAssistantText: string;
  latestUserText: string;
  wsUrl: string;
  baseUrl: string;
  currentModelUrl: string;
};

type BackendConfig = {
  baseUrl: string;
  wsUrl: string;
};

function normalizeText(value: unknown): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function buildAbsoluteModelUrl(baseUrl: string, relativeOrAbsoluteUrl: string): string {
  try {
    return new URL(relativeOrAbsoluteUrl, baseUrl).toString();
  } catch {
    return relativeOrAbsoluteUrl;
  }
}

class BackendClient {
  private config: BackendConfig;
  private socket: WebSocket | null;
  private renderer: PetLive2DRenderer;
  private currentAudio: HTMLAudioElement | null;
  private readonly updateState: (patch: Partial<RendererState>) => void;
  private reconnectTimer: number | null;
  private reconnectAttempt: number;
  private shouldReconnect: boolean;

  public constructor(
    config: BackendConfig,
    renderer: PetLive2DRenderer,
    updateState: (patch: Partial<RendererState>) => void
  ) {
    this.config = config;
    this.renderer = renderer;
    this.socket = null;
    this.currentAudio = null;
    this.updateState = updateState;
    this.reconnectTimer = null;
    this.reconnectAttempt = 0;
    this.shouldReconnect = true;
  }

  public connect(): void {
    this.clearReconnectTimer();
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.updateState({
      wsConnected: false,
      aiState: "connecting",
      baseUrl: this.config.baseUrl,
      wsUrl: this.config.wsUrl
    });

    if (!this.config.wsUrl) {
      console.warn("[pet-renderer] Missing WebSocket URL, skipping connection.");
      this.updateState({
        aiState: "offline"
      });
      return;
    }

    console.info("[pet-renderer] Connecting to backend", this.config.wsUrl);

    let socket: WebSocket;
    try {
      socket = new WebSocket(this.config.wsUrl);
    } catch (error) {
      console.warn("[pet-renderer] Failed to create WebSocket", error);
      this.socket = null;
      this.updateState({
        wsConnected: false,
        aiState: "offline"
      });
      this.scheduleReconnect();
      return;
    }

    this.socket = socket;

    socket.addEventListener("open", () => {
      if (this.socket !== socket) {
        return;
      }
      this.reconnectAttempt = 0;
      console.info("[pet-renderer] Backend WebSocket connected");
      this.updateState({
        wsConnected: true,
        aiState: "idle"
      });
    });

    socket.addEventListener("close", () => {
      if (this.socket !== socket) {
        return;
      }
      console.warn("[pet-renderer] Backend WebSocket closed");
      this.socket = null;
      this.updateState({
        wsConnected: false,
        aiState: "offline"
      });
      this.scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      if (this.socket !== socket) {
        return;
      }
      console.warn("[pet-renderer] Backend WebSocket error");
      this.updateState({
        wsConnected: false,
        aiState: "offline"
      });
    });

    socket.addEventListener("message", (event) => {
      if (this.socket !== socket) {
        return;
      }
      try {
        const payload = JSON.parse(String(event.data || "{}"));
        this.handleMessage(payload);
      } catch (error) {
        console.warn("[pet-renderer] Failed to parse backend message", error);
      }
    });
  }

  public disconnect(): void {
    this.shouldReconnect = false;
    this.clearReconnectTimer();
    this.stopAudioPlayback();
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  public applyConfig(baseUrl: string, wsUrl: string, reconnect = true): BackendConfig {
    this.config = {
      baseUrl: String(baseUrl || "").trim(),
      wsUrl: String(wsUrl || "").trim()
    };
    this.shouldReconnect = true;

    this.updateState({
      baseUrl: this.config.baseUrl,
      wsUrl: this.config.wsUrl
    });

    if (reconnect) {
      this.connect();
    }

    return { ...this.config };
  }

  public sendText(text: string): { ok: boolean; error?: string; text?: string } {
    const normalized = normalizeText(text);
    if (!normalized) {
      return { ok: false, error: "empty-text" };
    }

    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return { ok: false, error: "websocket-not-open" };
    }

    this.socket.send(
      JSON.stringify({
        type: "text-input",
        text: normalized
      })
    );
    this.updateState({
      latestUserText: normalized,
      aiState: "thinking"
    });
    return { ok: true, text: normalized };
  }

  public sendInterrupt(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(
      JSON.stringify({
        type: "interrupt-signal",
        text: "launcher-interrupt"
      })
    );
    this.updateState({
      aiState: "interrupted"
    });
  }

  private sendPlaybackComplete(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(
      JSON.stringify({
        type: "frontend-playback-complete"
      })
    );
  }

  private stopAudioPlayback(): void {
    if (!this.currentAudio) {
      return;
    }
    this.currentAudio.pause();
    this.currentAudio.src = "";
    this.currentAudio = null;
  }

  private playAudioPayload(audioBase64: string | null, displayText: string): void {
    if (!audioBase64) {
      this.updateState({
        latestAssistantText: displayText,
        aiState: "idle"
      });
      this.sendPlaybackComplete();
      return;
    }

    this.stopAudioPlayback();
    const audio = new Audio(`data:audio/wav;base64,${audioBase64}`);
    this.currentAudio = audio;

    audio.addEventListener("ended", () => {
      if (this.currentAudio === audio) {
        this.currentAudio = null;
      }
      this.updateState({
        aiState: "idle"
      });
      this.sendPlaybackComplete();
    });

    audio.addEventListener("error", () => {
      if (this.currentAudio === audio) {
        this.currentAudio = null;
      }
      this.updateState({
        aiState: "idle"
      });
      this.sendPlaybackComplete();
    });

    void audio.play().catch((error) => {
      console.warn("[pet-renderer] Audio playback failed", error);
      if (this.currentAudio === audio) {
        this.currentAudio = null;
      }
      this.updateState({
        aiState: "idle"
      });
      this.sendPlaybackComplete();
    });
  }

  private handleMessage(payload: Record<string, any>): void {
    const messageType = String(payload.type || "");

    if (messageType === "set-model-and-conf") {
      const modelInfo = payload.model_info || {};
      const rawUrl = String(modelInfo.url || "").trim();
      if (rawUrl) {
        const absoluteUrl = buildAbsoluteModelUrl(this.config.baseUrl, rawUrl);
        const scaleWidth = Math.max(0.8, Number(modelInfo.kScale || 0.45) * 2);
        console.info("[pet-renderer] Loading model", {
          modelUrl: absoluteUrl,
          scaleWidth
        });
        this.renderer.loadModel(absoluteUrl, scaleWidth);
        this.updateState({
          currentModelUrl: absoluteUrl
        });
      }
      return;
    }

    if (messageType === "audio") {
      const displayText = normalizeText(payload.display_text?.text || "");
      if (displayText) {
        this.updateState({
          latestAssistantText: displayText,
          aiState: payload.audio ? "speaking" : "idle"
        });
      }
      this.playAudioPayload(payload.audio || null, displayText);
      return;
    }

    if (messageType === "control") {
      const text = String(payload.text || "");
      if (text === "conversation-chain-start") {
        this.updateState({ aiState: "thinking" });
      } else if (text === "conversation-chain-end") {
        this.updateState({ aiState: "idle" });
      } else if (text === "interrupt" || text === "interrupt-signal") {
        this.updateState({ aiState: "interrupted" });
      } else if (text === "audio-play-start") {
        this.updateState({ aiState: "speaking" });
      }
      return;
    }

    if (messageType === "full-text") {
      const text = normalizeText(payload.text || "");
      if (text && text !== "Connection established") {
        this.updateState({
          latestAssistantText: text
        });
      }
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private scheduleReconnect(): void {
    if (!this.shouldReconnect) {
      return;
    }
    this.clearReconnectTimer();
    const delayMs = Math.min(8000, 1000 + this.reconnectAttempt * 1000);
    this.reconnectAttempt += 1;
    console.info("[pet-renderer] Scheduling reconnect", {
      attempt: this.reconnectAttempt,
      delayMs
    });
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delayMs);
  }
}

const root = document.getElementById("app");
if (!root) {
  throw new Error("Renderer root not found.");
}

root.innerHTML = `
  <div class="pet-renderer">
    <canvas id="live2d-canvas"></canvas>
    <div class="pet-status" id="pet-status">idle</div>
  </div>
`;

const canvas = document.getElementById("live2d-canvas");
const status = document.getElementById("pet-status");
if (!(canvas instanceof HTMLCanvasElement) || !(status instanceof HTMLDivElement)) {
  throw new Error("Renderer DOM bootstrap failed.");
}

const rendererState: RendererState = {
  wsConnected: false,
  aiState: "idle",
  latestAssistantText: "",
  latestUserText: "",
  wsUrl: "",
  baseUrl: "",
  currentModelUrl: ""
};

const reportState = (patch: Partial<RendererState>) => {
  Object.assign(rendererState, patch);
  status.textContent = rendererState.aiState;
  window.__kuroPetRendererState = { ...rendererState };
  window.kuroPetElectron.reportFrontendState({ ...rendererState });
};

const renderer = new PetLive2DRenderer(canvas);
const initialConfig = window.kuroPetElectron.getInitialConfig();
const client = new BackendClient(
  {
    baseUrl: initialConfig.baseUrl,
    wsUrl: initialConfig.wsUrl
  },
  renderer,
  reportState
);

window.__kuroPetSendTextInput = (text: string) => client.sendText(text);
window.__kuroPetApplyBackendConfig = (baseUrl: string, wsUrl: string, reconnect = true) =>
  client.applyConfig(baseUrl, wsUrl, reconnect);

reportState({
  baseUrl: initialConfig.baseUrl,
  wsUrl: initialConfig.wsUrl
});
client.connect();

canvas.addEventListener("pointerenter", () => {
  window.kuroPetElectron.updateComponentHover("live2d-model", true);
});

canvas.addEventListener("pointerleave", () => {
  window.kuroPetElectron.updateComponentHover("live2d-model", false);
});

canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) {
    return;
  }
  event.preventDefault();
  window.kuroPetElectron.startWindowDrag(event.screenX, event.screenY);
});

window.addEventListener("pointermove", (event) => {
  window.kuroPetElectron.updateWindowDrag(event.screenX, event.screenY);
});

window.addEventListener("pointerup", () => {
  window.kuroPetElectron.endWindowDrag();
});

window.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  window.kuroPetElectron.showContextMenu();
});

window.addEventListener("resize", () => {
  renderer.resize();
});

const unsubscribe = window.kuroPetElectron.onCommand((payload) => {
  if (!payload || typeof payload.type !== "string") {
    return;
  }

  if (payload.type === "interrupt") {
    client.sendInterrupt();
  }
});

window.addEventListener(
  "beforeunload",
  () => {
    unsubscribe();
    client.disconnect();
    renderer.dispose();
  },
  { passive: true }
);

window.addEventListener("error", (event) => {
  console.error("[pet-renderer] Unhandled window error", event.error || event.message);
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason as any;
  console.error("[pet-renderer] Unhandled promise rejection", {
    message: reason?.message || String(reason),
    stack: reason?.stack || null
  });
});
