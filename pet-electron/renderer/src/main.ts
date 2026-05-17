import "./styles.css";
import { PetLive2DRenderer } from "./live2d/pet-live2d-renderer";

const RENDERER_BUILD_TAG = "custom-renderer-2026-05-17b";
const MODEL_ZOOM_STORAGE_KEY = "kuroPetModelZoomScale";
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
  confName: string;
  confUid: string;
  currentHistoryUid: string;
  currentHistoryTitle: string;
  micEnabled: boolean;
  cameraEnabled: boolean;
  screenEnabled: boolean;
  browserPanelEnabled: boolean;
};

type BackendConfig = {
  baseUrl: string;
  wsUrl: string;
};

type BackendImagePayload = {
  source: "camera" | "screen";
  data: string;
  mime_type: string;
};

function normalizeText(value: unknown): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function mergeTextFragments(parts: string[]): string {
  let merged = "";
  for (const part of parts) {
    if (!part) {
      continue;
    }
    if (!merged) {
      merged = part;
      continue;
    }
    const needsSpace = /[A-Za-z0-9]$/.test(merged) && /^[A-Za-z0-9]/.test(part);
    merged += needsSpace ? ` ${part}` : part;
  }
  return merged;
}

function buildAbsoluteModelUrl(baseUrl: string, relativeOrAbsoluteUrl: string): string {
  try {
    return new URL(relativeOrAbsoluteUrl, baseUrl).toString();
  } catch {
    return relativeOrAbsoluteUrl;
  }
}

function loadStoredModelZoomScale(): number {
  try {
    const raw = window.localStorage.getItem(MODEL_ZOOM_STORAGE_KEY);
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : 1.0;
  } catch {
    return 1.0;
  }
}

function storeModelZoomScale(zoomScale: number): void {
  try {
    window.localStorage.setItem(MODEL_ZOOM_STORAGE_KEY, String(zoomScale));
  } catch {
    // Ignore localStorage write failures.
  }
}

function resolveInitialZoomScale(configZoomScale: unknown): number {
  const normalized = Number(configZoomScale);
  const stored = loadStoredModelZoomScale();
  if (Number.isFinite(stored) && Math.abs(stored - 1.0) > 0.0001) {
    if (!Number.isFinite(normalized) || Math.abs(normalized - 1.0) <= 0.0001) {
      return stored;
    }
  }
  if (Number.isFinite(normalized)) {
    return normalized;
  }
  return stored;
}

function downsampleFloat32(input: Float32Array, inputSampleRate: number, outputSampleRate: number): number[] {
  if (!input.length) {
    return [];
  }
  if (!Number.isFinite(inputSampleRate) || inputSampleRate <= 0 || inputSampleRate === outputSampleRate) {
    return Array.from(input);
  }

  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.max(1, Math.floor(input.length / ratio));
  const output: number[] = [];
  for (let i = 0; i < outputLength; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let total = 0;
    let count = 0;
    for (let j = start; j < end; j += 1) {
      total += input[j] || 0;
      count += 1;
    }
    output.push(count ? total / count : input[start] || 0);
  }
  return output;
}

class BackendClient {
  private config: BackendConfig;
  private socket: WebSocket | null;
  private renderer: PetLive2DRenderer;
  private currentAudio: HTMLAudioElement | null;
  private audioQueue: string[];
  private readonly updateState: (patch: Partial<RendererState>) => void;
  private reconnectTimer: number | null;
  private reconnectAttempt: number;
  private shouldReconnect: boolean;
  private assistantTurnParts: string[];
  private assistantTurnText: string;
  private backendSynthComplete: boolean;
  private playbackCompleteSent: boolean;
  private micStream: MediaStream | null;
  private micAudioContext: AudioContext | null;
  private micSource: MediaStreamAudioSourceNode | null;
  private micProcessor: ScriptProcessorNode | null;
  private micSamples: number[];
  private cameraStream: MediaStream | null;
  private screenStream: MediaStream | null;
  private cameraVideo: HTMLVideoElement | null;
  private screenVideo: HTMLVideoElement | null;

  public constructor(
    config: BackendConfig,
    renderer: PetLive2DRenderer,
    updateState: (patch: Partial<RendererState>) => void
  ) {
    this.config = config;
    this.renderer = renderer;
    this.socket = null;
    this.currentAudio = null;
    this.audioQueue = [];
    this.updateState = updateState;
    this.reconnectTimer = null;
    this.reconnectAttempt = 0;
    this.shouldReconnect = true;
    this.assistantTurnParts = [];
    this.assistantTurnText = "";
    this.backendSynthComplete = false;
    this.playbackCompleteSent = false;
    this.micStream = null;
    this.micAudioContext = null;
    this.micSource = null;
    this.micProcessor = null;
    this.micSamples = [];
    this.cameraStream = null;
    this.screenStream = null;
    this.cameraVideo = null;
    this.screenVideo = null;
  }

  public connect(): void {
    this.clearReconnectTimer();
    this.stopAudioPlayback(true);
    this.resetPlaybackTurn();
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
      socket.send(
        JSON.stringify({
          type: "create-new-history"
        })
      );
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
    this.stopAudioPlayback(true);
    void this.stopMicrophoneCapture(false);
    this.stopMediaStream(this.cameraStream);
    this.stopMediaStream(this.screenStream);
    this.cameraStream = null;
    this.screenStream = null;
    this.removePreviewVideo(this.cameraVideo);
    this.removePreviewVideo(this.screenVideo);
    this.cameraVideo = null;
    this.screenVideo = null;
    this.updateState({ cameraEnabled: false, screenEnabled: false });
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

  public async sendText(text: string): Promise<{ ok: boolean; error?: string; text?: string }> {
    const normalized = normalizeText(text);
    if (!normalized) {
      return { ok: false, error: "empty-text" };
    }

    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return { ok: false, error: "websocket-not-open" };
    }

    const images = await this.captureEnabledImages();
    this.socket.send(
      JSON.stringify({
        type: "text-input",
        text: normalized,
        ...(images.length ? { images } : {})
      })
    );
    this.resetAssistantTurn();
    this.stopAudioPlayback(true);
    this.resetPlaybackTurn();
    this.updateState({
      latestUserText: normalized,
      latestAssistantText: "",
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
    this.stopAudioPlayback(true);
    this.resetPlaybackTurn();
    this.updateState({
      aiState: "interrupted"
    });
  }

  public async setMicrophoneEnabled(enabled: boolean): Promise<{ ok: boolean; error?: string }> {
    if (enabled) {
      return this.startMicrophoneCapture();
    }
    return await this.stopMicrophoneCapture(true);
  }

  public async setCameraEnabled(enabled: boolean): Promise<{ ok: boolean; error?: string }> {
    if (!enabled) {
      this.stopMediaStream(this.cameraStream);
      this.cameraStream = null;
      this.removePreviewVideo(this.cameraVideo);
      this.cameraVideo = null;
      this.updateState({ cameraEnabled: false });
      return { ok: true };
    }

    try {
      this.cameraStream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false
      });
      this.cameraVideo = await this.createPreviewVideo(this.cameraStream);
      this.updateState({ cameraEnabled: true });
      return { ok: true };
    } catch (error) {
      console.warn("[pet-renderer] Camera capture failed", error);
      this.updateState({ cameraEnabled: false });
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }

  public async setScreenEnabled(enabled: boolean): Promise<{ ok: boolean; error?: string }> {
    if (!enabled) {
      this.stopMediaStream(this.screenStream);
      this.screenStream = null;
      this.removePreviewVideo(this.screenVideo);
      this.screenVideo = null;
      this.updateState({ screenEnabled: false });
      return { ok: true };
    }

    try {
      const sourceId = await window.kuroPetElectron.getScreenCaptureSourceId();
      if (!sourceId) {
        throw new Error("screen-source-missing");
      }
      const constraints = {
        audio: false,
        video: {
          mandatory: {
            chromeMediaSource: "desktop",
            chromeMediaSourceId: sourceId,
            maxFrameRate: 2
          }
        }
      } as unknown as MediaStreamConstraints;
      this.screenStream = await navigator.mediaDevices.getUserMedia(constraints);
      this.screenVideo = await this.createPreviewVideo(this.screenStream);
      this.updateState({ screenEnabled: true });
      return { ok: true };
    } catch (error) {
      console.warn("[pet-renderer] Screen capture failed", error);
      this.updateState({ screenEnabled: false });
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }

  public setBrowserPanelEnabled(enabled: boolean): { ok: boolean } {
    this.updateState({ browserPanelEnabled: enabled });
    return { ok: true };
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

  private stopAudioPlayback(clearQueue = false): void {
    if (clearQueue) {
      this.audioQueue = [];
    }

    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.src = "";
      this.currentAudio = null;
    }
  }

  private stopMediaStream(stream: MediaStream | null): void {
    if (!stream) {
      return;
    }
    for (const track of stream.getTracks()) {
      try {
        track.stop();
      } catch {
        // Ignore media cleanup failures.
      }
    }
  }

  private removePreviewVideo(video: HTMLVideoElement | null): void {
    if (!video) {
      return;
    }
    video.pause();
    video.srcObject = null;
    video.remove();
  }

  private async createPreviewVideo(stream: MediaStream): Promise<HTMLVideoElement> {
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.autoplay = true;
    video.style.display = "none";
    video.srcObject = stream;
    document.body.appendChild(video);

    await new Promise<void>((resolve) => {
      const done = () => resolve();
      if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
        resolve();
        return;
      }
      video.addEventListener("loadedmetadata", done, { once: true });
      window.setTimeout(done, 1000);
    });

    await video.play().catch(() => undefined);
    return video;
  }

  private captureVideoFrame(
    video: HTMLVideoElement | null,
    source: "camera" | "screen"
  ): BackendImagePayload | null {
    if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      return null;
    }

    const rawWidth = video.videoWidth || 0;
    const rawHeight = video.videoHeight || 0;
    if (rawWidth <= 0 || rawHeight <= 0) {
      return null;
    }

    const maxEdge = source === "screen" ? 1280 : 768;
    const scale = Math.min(1, maxEdge / Math.max(rawWidth, rawHeight));
    const width = Math.max(1, Math.round(rawWidth * scale));
    const height = Math.max(1, Math.round(rawHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) {
      return null;
    }
    context.drawImage(video, 0, 0, width, height);
    return {
      source,
      data: canvas.toDataURL("image/jpeg", 0.72),
      mime_type: "image/jpeg"
    };
  }

  private async captureEnabledImages(): Promise<BackendImagePayload[]> {
    const images: BackendImagePayload[] = [];
    const cameraFrame = this.captureVideoFrame(this.cameraVideo, "camera");
    if (cameraFrame) {
      images.push(cameraFrame);
    }
    const screenFrame = this.captureVideoFrame(this.screenVideo, "screen");
    if (screenFrame) {
      images.push(screenFrame);
    }
    return images;
  }

  private async startMicrophoneCapture(): Promise<{ ok: boolean; error?: string }> {
    if (this.micStream) {
      this.updateState({ micEnabled: true });
      return { ok: true };
    }

    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.updateState({ micEnabled: false });
      return { ok: false, error: "websocket-not-open" };
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        },
        video: false
      });
      const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
      const audioContext = new AudioContextCtor();
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const mute = audioContext.createGain();
      mute.gain.value = 0;

      this.micSamples = [];
      processor.onaudioprocess = (event) => {
        const channel = event.inputBuffer.getChannelData(0);
        const samples = downsampleFloat32(channel, audioContext.sampleRate, 16000);
        this.micSamples.push(...samples);
      };

      source.connect(processor);
      processor.connect(mute);
      mute.connect(audioContext.destination);

      this.micStream = stream;
      this.micAudioContext = audioContext;
      this.micSource = source;
      this.micProcessor = processor;
      this.updateState({ micEnabled: true, aiState: "listening" });
      return { ok: true };
    } catch (error) {
      console.warn("[pet-renderer] Microphone capture failed", error);
      this.stopMicrophoneNodes();
      this.updateState({ micEnabled: false });
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }

  private stopMicrophoneNodes(): void {
    try {
      this.micProcessor?.disconnect();
    } catch {
      // Ignore disconnect failures.
    }
    try {
      this.micSource?.disconnect();
    } catch {
      // Ignore disconnect failures.
    }
    this.stopMediaStream(this.micStream);
    void this.micAudioContext?.close().catch(() => undefined);
    this.micStream = null;
    this.micAudioContext = null;
    this.micSource = null;
    this.micProcessor = null;
  }

  private async stopMicrophoneCapture(submit: boolean): Promise<{ ok: boolean; error?: string }> {
    const samples = this.micSamples.slice();
    this.micSamples = [];
    this.stopMicrophoneNodes();
    this.updateState({ micEnabled: false });

    if (!submit || samples.length === 0) {
      this.updateState({ aiState: "idle" });
      return { ok: true };
    }

    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return { ok: false, error: "websocket-not-open" };
    }

    const chunkSize = 4096;
    for (let i = 0; i < samples.length; i += chunkSize) {
      this.socket.send(
        JSON.stringify({
          type: "mic-audio-data",
          audio: samples.slice(i, i + chunkSize)
        })
      );
    }
    this.resetAssistantTurn();
    this.stopAudioPlayback(true);
    this.resetPlaybackTurn();
    const images = await this.captureEnabledImages();
    this.socket.send(
      JSON.stringify({
        type: "mic-audio-end",
        ...(images.length ? { images } : {})
      })
    );
    this.updateState({ latestAssistantText: "", aiState: "thinking" });
    return { ok: true };
  }

  private resetPlaybackTurn(): void {
    this.audioQueue = [];
    this.backendSynthComplete = false;
    this.playbackCompleteSent = false;
  }

  private resetAssistantTurn(): void {
    this.assistantTurnParts = [];
    this.assistantTurnText = "";
  }

  private appendAssistantTextFragment(value: unknown): string {
    const fragment = normalizeText(value);
    if (!fragment) {
      return this.assistantTurnText;
    }

    if (this.assistantTurnText === fragment) {
      return this.assistantTurnText;
    }

    if (this.assistantTurnText && fragment.startsWith(this.assistantTurnText)) {
      this.assistantTurnParts = [fragment];
      this.assistantTurnText = fragment;
      return this.assistantTurnText;
    }

    if (this.assistantTurnText && this.assistantTurnText.includes(fragment)) {
      return this.assistantTurnText;
    }

    const lastPart = this.assistantTurnParts[this.assistantTurnParts.length - 1];
    if (lastPart === fragment) {
      return this.assistantTurnText;
    }

    this.assistantTurnParts.push(fragment);
    this.assistantTurnText = mergeTextFragments(this.assistantTurnParts);
    return this.assistantTurnText;
  }

  private setAssistantText(value: unknown): string {
    const text = normalizeText(value);
    if (!text) {
      return this.assistantTurnText;
    }

    if (text === "Connection established" || text === "Thinking...") {
      return this.assistantTurnText;
    }

    if (!this.assistantTurnText || text.startsWith(this.assistantTurnText)) {
      this.assistantTurnParts = [text];
      this.assistantTurnText = text;
      return this.assistantTurnText;
    }

    if (this.assistantTurnText.includes(text)) {
      return this.assistantTurnText;
    }

    return this.appendAssistantTextFragment(text);
  }

  private playAudioPayload(audioBase64: string | null): void {
    if (!audioBase64) {
      this.maybeNotifyPlaybackComplete();
      return;
    }

    this.audioQueue.push(audioBase64);
    this.playbackCompleteSent = false;
    this.updateState({
      aiState: "speaking"
    });
    this.playNextQueuedAudio();
  }

  private playNextQueuedAudio(): void {
    if (this.currentAudio) {
      return;
    }

    const audioBase64 = this.audioQueue.shift();
    if (!audioBase64) {
      this.maybeNotifyPlaybackComplete();
      return;
    }

    const audio = new Audio(`data:audio/wav;base64,${audioBase64}`);
    this.currentAudio = audio;
    this.updateState({
      aiState: "speaking"
    });

    let settled = false;
    const finishPlayback = () => {
      if (settled) {
        return;
      }
      settled = true;
      if (this.currentAudio === audio) {
        this.currentAudio = null;
      }
      this.playNextQueuedAudio();
    };

    audio.addEventListener("ended", finishPlayback);

    audio.addEventListener("error", () => {
      console.warn("[pet-renderer] Audio element reported playback error");
      finishPlayback();
    });

    void audio.play().catch((error) => {
      console.warn("[pet-renderer] Audio playback failed", error);
      finishPlayback();
    });
  }

  private markBackendSynthComplete(): void {
    this.backendSynthComplete = true;
    this.maybeNotifyPlaybackComplete();
  }

  private maybeNotifyPlaybackComplete(): void {
    if (this.currentAudio || this.audioQueue.length > 0) {
      return;
    }

    this.updateState({
      aiState: "idle"
    });

    if (!this.backendSynthComplete || this.playbackCompleteSent) {
      return;
    }

    this.playbackCompleteSent = true;
    window.setTimeout(() => {
      if (this.currentAudio || this.audioQueue.length > 0 || !this.backendSynthComplete || !this.playbackCompleteSent) {
        return;
      }
      this.sendPlaybackComplete();
    }, 50);
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
          currentModelUrl: absoluteUrl,
          confName: normalizeText(payload.conf_name || ""),
          confUid: normalizeText(payload.conf_uid || "")
        });
      }
      return;
    }

    if (messageType === "history-list") {
      const histories = Array.isArray(payload.histories) ? payload.histories : [];
      const selected = histories[0] || {};
      const historyUid = normalizeText(selected.uid || selected.history_uid || "");
      if (historyUid) {
        this.updateState({
          currentHistoryUid: historyUid,
          currentHistoryTitle: normalizeText(selected.title || "")
        });
      }
      return;
    }

    if (messageType === "new-history-created") {
      const historyUid = normalizeText(payload.history_uid || "");
      if (historyUid) {
        this.updateState({
          currentHistoryUid: historyUid,
          currentHistoryTitle: ""
        });
      }
      return;
    }

    if (messageType === "config-switched") {
      const historyUid = normalizeText(payload.history_uid || "");
      if (historyUid) {
        this.updateState({
          currentHistoryUid: historyUid,
          currentHistoryTitle: ""
        });
      }
      return;
    }

    if (messageType === "audio") {
      const displayText = normalizeText(payload.display_text?.text || "");
      if (displayText) {
        const assistantText = this.appendAssistantTextFragment(displayText);
        this.updateState({
          latestAssistantText: assistantText,
          aiState: payload.audio ? "speaking" : "idle"
        });
      }
      this.playAudioPayload(payload.audio || null);
      return;
    }

    if (messageType === "backend-synth-complete") {
      this.markBackendSynthComplete();
      return;
    }

    if (messageType === "control") {
      const text = String(payload.text || "");
      if (text === "conversation-chain-start") {
        this.stopAudioPlayback(true);
        this.resetPlaybackTurn();
        this.resetAssistantTurn();
        this.updateState({ latestAssistantText: "", aiState: "thinking" });
      } else if (text === "conversation-chain-end") {
        this.updateState({
          aiState: this.currentAudio || this.audioQueue.length > 0 ? "speaking" : "idle"
        });
      } else if (text === "interrupt" || text === "interrupt-signal") {
        this.stopAudioPlayback(true);
        this.resetPlaybackTurn();
        this.updateState({ aiState: "interrupted" });
      } else if (text === "audio-play-start") {
        this.updateState({ aiState: "speaking" });
      }
      return;
    }

    if (messageType === "full-text") {
      const text = this.setAssistantText(payload.text || "");
      if (text) {
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
  </div>
`;

const canvas = document.getElementById("live2d-canvas");
if (!(canvas instanceof HTMLCanvasElement)) {
  throw new Error("Renderer DOM bootstrap failed.");
}

const rendererState: RendererState = {
  wsConnected: false,
  aiState: "idle",
  latestAssistantText: "",
  latestUserText: "",
  wsUrl: "",
  baseUrl: "",
  currentModelUrl: "",
  confName: "",
  confUid: "",
  currentHistoryUid: "",
  currentHistoryTitle: "",
  micEnabled: false,
  cameraEnabled: false,
  screenEnabled: false,
  browserPanelEnabled: false
};

const reportState = (patch: Partial<RendererState>) => {
  Object.assign(rendererState, patch);
  window.__kuroPetRendererState = { ...rendererState };
  window.kuroPetElectron.reportFrontendState({ ...rendererState });
};

const initialConfig = window.kuroPetElectron.getInitialConfig();
const renderer = new PetLive2DRenderer(canvas);
renderer.setZoomScale(resolveInitialZoomScale(initialConfig.zoomScale));
storeModelZoomScale(renderer.getZoomScale());
window.kuroPetElectron.setPetWindowZoom(renderer.getZoomScale());
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

let hoverOnModel = false;
let draggingModel = false;

function setModelHoverState(nextHover: boolean): void {
  if (hoverOnModel === nextHover) {
    return;
  }
  hoverOnModel = nextHover;
  canvas.style.cursor = draggingModel ? "grabbing" : hoverOnModel ? "grab" : "default";
  window.kuroPetElectron.updateComponentHover("live2d-model", hoverOnModel);
}

function refreshModelHover(clientX: number, clientY: number): boolean {
  const nextHover = renderer.hitTestCanvasPoint(clientX, clientY);
  setModelHoverState(nextHover);
  return nextHover;
}

canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) {
    return;
  }

  if (!refreshModelHover(event.clientX, event.clientY)) {
    return;
  }

  draggingModel = true;
  canvas.style.cursor = "grabbing";
  event.preventDefault();
  window.kuroPetElectron.startWindowDrag(event.screenX, event.screenY);
});

canvas.addEventListener(
  "wheel",
  (event) => {
    if (!refreshModelHover(event.clientX, event.clientY)) {
      return;
    }

    event.preventDefault();
    const zoomScale = renderer.adjustZoomByWheel(event.deltaY);
    storeModelZoomScale(zoomScale);
    window.kuroPetElectron.setPetWindowZoom(zoomScale);
  },
  { passive: false }
);

window.addEventListener("pointermove", (event) => {
  if (draggingModel) {
    window.kuroPetElectron.updateWindowDrag(event.screenX, event.screenY);
    return;
  }

  refreshModelHover(event.clientX, event.clientY);
});

window.addEventListener("pointerup", () => {
  draggingModel = false;
  canvas.style.cursor = hoverOnModel ? "grab" : "default";
  window.kuroPetElectron.endWindowDrag();
});

canvas.addEventListener("pointerleave", () => {
  if (draggingModel) {
    return;
  }
  setModelHoverState(false);
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
  } else if (payload.type === "mic-toggle") {
    void client.setMicrophoneEnabled(Boolean(payload.enabled));
  } else if (payload.type === "camera-toggle") {
    void client.setCameraEnabled(Boolean(payload.enabled));
  } else if (payload.type === "screen-toggle") {
    void client.setScreenEnabled(Boolean(payload.enabled));
  } else if (payload.type === "browser-toggle") {
    client.setBrowserPanelEnabled(Boolean(payload.enabled));
  }
});

window.addEventListener(
  "beforeunload",
  () => {
    unsubscribe();
    setModelHoverState(false);
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
