import { PetLive2DRenderer } from "../live2d/pet-live2d-renderer";
import { llmVtuberAdapter } from "./adapters/llm-vtuber-adapter";
import { buildSpeechLipSyncEnvelope, downsampleFloat32 } from "./audio-utils";
import {
  buildVisibleInputText,
  mergeTextFragments,
  normalizeText
} from "./text-utils";
import type { BackendProtocolAdapter, KuroBackendEvent } from "./kuro-backend-events";
import type {
  BackendConfig,
  BackendFilePayload,
  BackendImagePayload,
  RendererState,
  SpeechLipSyncEnvelope,
  UserAttachmentPayload
} from "./types";

export class BackendClient {
  private config: BackendConfig;
  private socket: WebSocket | null;
  private renderer: PetLive2DRenderer;
  private protocolAdapter: BackendProtocolAdapter;
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
  private speechAudioContext: AudioContext | null;
  private speechAnalyser: AnalyserNode | null;
  private speechSource: MediaElementAudioSourceNode | null;
  private speechData: Uint8Array<ArrayBuffer> | null;
  private speechEnvelope: SpeechLipSyncEnvelope | null;
  private lipSyncFrameId: number | null;
  private lipSyncTimerId: number | null;
  private lipSyncLevel: number;
  private speechFallbackStartedAt: number;

  public constructor(
    config: BackendConfig,
    renderer: PetLive2DRenderer,
    updateState: (patch: Partial<RendererState>) => void,
    protocolAdapter: BackendProtocolAdapter = llmVtuberAdapter
  ) {
    this.config = config;
    this.renderer = renderer;
    this.protocolAdapter = protocolAdapter;
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
    this.speechAudioContext = null;
    this.speechAnalyser = null;
    this.speechSource = null;
    this.speechData = null;
    this.speechEnvelope = null;
    this.lipSyncFrameId = null;
    this.lipSyncTimerId = null;
    this.lipSyncLevel = 0;
    this.speechFallbackStartedAt = 0;
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
        JSON.stringify(this.protocolAdapter.createHistoryStartMessage())
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
    void this.speechAudioContext?.close().catch(() => undefined);
    this.speechAudioContext = null;
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

  public async sendText(
    text: string,
    attachments: UserAttachmentPayload[] = []
  ): Promise<{ ok: boolean; error?: string; text?: string }> {
    const normalized = normalizeText(text);
    const visibleText = buildVisibleInputText(normalized, attachments);
    const normalizedAttachments = this.normalizeAttachments(attachments);
    if (!normalized && normalizedAttachments.images.length === 0 && normalizedAttachments.files.length === 0) {
      return { ok: false, error: "empty-text" };
    }

    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return { ok: false, error: "websocket-not-open" };
    }

    const images = await this.captureEnabledImages();
    images.push(...normalizedAttachments.images);
    this.socket.send(
      JSON.stringify(
        this.protocolAdapter.createTextInputMessage({
          text: normalized || "請分析我附上的檔案。",
          images,
          files: normalizedAttachments.files
        })
      )
    );
    this.resetAssistantTurn();
    this.stopAudioPlayback(true);
    this.resetPlaybackTurn();
    this.updateState({
      latestUserText: visibleText,
      latestAssistantText: "",
      aiState: "thinking"
    });
    return { ok: true, text: visibleText };
  }

  public sendInterrupt(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(
      JSON.stringify(this.protocolAdapter.createInterruptMessage())
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
      JSON.stringify(this.protocolAdapter.createPlaybackCompleteMessage())
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
    this.stopSpeechLipSync(true);
  }

  private ensureSpeechAudioContext(): AudioContext | null {
    if (this.speechAudioContext) {
      return this.speechAudioContext;
    }

    const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextCtor) {
      return null;
    }

    this.speechAudioContext = new AudioContextCtor();
    return this.speechAudioContext;
  }

  private beginSpeechLipSync(
    audio: HTMLAudioElement,
    envelope: SpeechLipSyncEnvelope | null
  ): void {
    this.stopSpeechLipSync(false);
    this.speechEnvelope = envelope;

    const audioContext = this.ensureSpeechAudioContext();
    if (!audioContext) {
      this.startSpeechLipSyncFallback();
      return;
    }

    try {
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.58;
      const source = audioContext.createMediaElementSource(audio);
      source.connect(analyser);
      analyser.connect(audioContext.destination);

      this.speechSource = source;
      this.speechAnalyser = analyser;
      this.speechData = new Uint8Array(new ArrayBuffer(analyser.fftSize));
      this.lipSyncLevel = envelope ? 0 : 0.34;
      this.speechFallbackStartedAt = performance.now();
      this.renderer.setLipSyncValue(this.lipSyncLevel);

      if (audioContext.state === "suspended") {
        void audioContext.resume().catch((error) => {
          console.warn("[pet-renderer] Speech audio context resume failed", error);
        });
      }

      this.scheduleSpeechLipSyncFrame();
    } catch (error) {
      console.warn("[pet-renderer] Speech lip sync setup failed", error);
      this.startSpeechLipSyncFallback();
    }
  }

  private startSpeechLipSyncFallback(): void {
    this.speechSource = null;
    this.speechAnalyser = null;
    this.speechData = null;
    this.lipSyncLevel = this.speechEnvelope ? 0 : 0.34;
    this.speechFallbackStartedAt = performance.now();
    this.renderer.setLipSyncValue(this.lipSyncLevel);
    this.scheduleSpeechLipSyncFrame();
  }

  private stopSpeechLipSync(resetMouth: boolean): void {
    if (this.lipSyncFrameId !== null) {
      window.cancelAnimationFrame(this.lipSyncFrameId);
      this.lipSyncFrameId = null;
    }
    if (this.lipSyncTimerId !== null) {
      window.clearTimeout(this.lipSyncTimerId);
      this.lipSyncTimerId = null;
    }

    try {
      this.speechSource?.disconnect();
    } catch {
      // Ignore disconnect failures.
    }

    try {
      this.speechAnalyser?.disconnect();
    } catch {
      // Ignore disconnect failures.
    }

    this.speechSource = null;
    this.speechAnalyser = null;
    this.speechData = null;
    this.speechEnvelope = null;
    this.lipSyncLevel = 0;
    this.speechFallbackStartedAt = 0;

    if (resetMouth) {
      this.renderer.setLipSyncValue(0);
    }
  }

  private scheduleSpeechLipSyncFrame(): void {
    if (this.lipSyncFrameId !== null || this.lipSyncTimerId !== null) {
      return;
    }

    this.lipSyncTimerId = window.setTimeout(() => {
      this.lipSyncTimerId = null;
      this.lipSyncFrameId = window.requestAnimationFrame(() => {
        this.lipSyncFrameId = null;
        this.updateSpeechLipSync();
      });
    }, 33);
  }

  private getSpeechFallbackTarget(): number {
    const elapsed =
      this.currentAudio?.currentTime ||
      Math.max(0, (performance.now() - this.speechFallbackStartedAt) / 1000);
    return Math.min(
      0.92,
      0.34 +
        0.34 * (0.5 + 0.5 * Math.sin(elapsed * 18.5)) +
        0.18 * (0.5 + 0.5 * Math.sin(elapsed * 31.0 + 0.7))
    );
  }

  private getSpeechEnvelopeTarget(): number | null {
    if (!this.currentAudio || !this.speechEnvelope) {
      return null;
    }

    const { values, frameRate, duration } = this.speechEnvelope;
    if (!values.length || frameRate <= 0 || duration <= 0) {
      return null;
    }

    const playbackTime = Math.min(
      duration,
      Math.max(0, this.currentAudio.currentTime || 0)
    );
    const exactIndex = playbackTime * frameRate;
    const lowerIndex = Math.min(values.length - 1, Math.floor(exactIndex));
    const upperIndex = Math.min(values.length - 1, lowerIndex + 1);
    const fraction = exactIndex - lowerIndex;
    const lowerValue = values[lowerIndex] || 0;
    const upperValue = values[upperIndex] || 0;
    return lowerValue + (upperValue - lowerValue) * fraction;
  }

  private updateSpeechLipSync(): void {
    if (!this.currentAudio) {
      this.renderer.setLipSyncValue(0);
      return;
    }

    if (this.currentAudio.ended) {
      this.lipSyncLevel *= 0.55;
      this.renderer.setLipSyncValue(this.lipSyncLevel);
      if (this.lipSyncLevel > 0.01) {
        this.scheduleSpeechLipSyncFrame();
      }
      return;
    }

    let target = this.currentAudio.paused ? 0 : this.getSpeechEnvelopeTarget();

    if (target === null && this.speechAnalyser && this.speechData) {
      this.speechAnalyser.getByteTimeDomainData(this.speechData);
      let sumSquares = 0;
      for (const sample of this.speechData) {
        const centered = (sample - 128) / 128;
        sumSquares += centered * centered;
      }

      const rms = Math.sqrt(sumSquares / this.speechData.length);
      target = Math.min(1, Math.max(0, (rms - 0.006) * 26));
    }

    if (target === null) {
      target = this.currentAudio.paused ? 0 : this.getSpeechFallbackTarget();
    }

    this.lipSyncLevel += (target - this.lipSyncLevel) * 0.58;
    this.renderer.setLipSyncValue(Math.min(1, Math.pow(this.lipSyncLevel, 0.78)));
    this.scheduleSpeechLipSyncFrame();
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

  private normalizeAttachments(attachments: UserAttachmentPayload[]): {
    images: BackendImagePayload[];
    files: BackendFilePayload[];
  } {
    const images: BackendImagePayload[] = [];
    const files: BackendFilePayload[] = [];
    const items = Array.isArray(attachments) ? attachments.slice(0, 6) : [];

    for (const item of items) {
      if (!item || typeof item !== "object") {
        continue;
      }

      const data = String(item.data || "");
      const requestedKind = String(item.kind || "").toLowerCase();
      const mimeType = String(item.mime_type || item.type || "").toLowerCase() || "application/octet-stream";
      const name = String(item.name || "uploaded-file").trim() || "uploaded-file";
      const size = Number(item.size) || 0;
      if (!data.startsWith("data:")) {
        continue;
      }

      if (mimeType.startsWith("image/")) {
        images.push({
          source: "upload",
          data,
          mime_type: mimeType
        });
      } else {
        files.push({
          kind: requestedKind || (mimeType.startsWith("audio/") ? "audio" : "file"),
          name,
          data,
          mime_type: mimeType,
          size
        });
      }
    }

    return { images, files };
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
        JSON.stringify(this.protocolAdapter.createMicAudioDataMessage(samples.slice(i, i + chunkSize)))
      );
    }
    this.resetAssistantTurn();
    this.stopAudioPlayback(true);
    this.resetPlaybackTurn();
    const images = await this.captureEnabledImages();
    this.socket.send(
      JSON.stringify(this.protocolAdapter.createMicAudioEndMessage({ images }))
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

    const lipSyncEnvelope = buildSpeechLipSyncEnvelope(audioBase64);
    const audio = new Audio(`data:audio/wav;base64,${audioBase64}`);
    this.currentAudio = audio;
    this.beginSpeechLipSync(audio, lipSyncEnvelope);
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
      this.stopSpeechLipSync(true);
      this.playNextQueuedAudio();
    };

    audio.addEventListener("ended", finishPlayback);
    audio.addEventListener("playing", () => {
      this.scheduleSpeechLipSyncFrame();
    });

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
    const events = this.protocolAdapter.toKuroEvents(payload, {
      baseUrl: this.config.baseUrl
    });

    for (const event of events) {
      this.handleKuroEvent(event);
    }
  }

  private handleKuroEvent(event: KuroBackendEvent): void {
    if (event.type === "model-load") {
      console.info("[pet-renderer] Loading model", {
        modelUrl: event.modelUrl,
        scaleWidth: event.scaleWidth
      });
      this.renderer.loadModel(event.modelUrl, event.scaleWidth);
      this.updateState({
        currentModelUrl: event.modelUrl,
        confName: event.confName,
        confUid: event.confUid
      });
    } else if (event.type === "history-selected") {
      this.updateState({
        currentHistoryUid: event.historyUid,
        currentHistoryTitle: event.historyTitle
      });
    } else if (event.type === "assistant-audio") {
      if (event.displayText) {
        const assistantText = this.appendAssistantTextFragment(event.displayText);
        this.updateState({
          latestAssistantText: assistantText,
          aiState: event.audioBase64 ? "speaking" : "idle"
        });
      }
      this.playAudioPayload(event.audioBase64);
    } else if (event.type === "synth-complete") {
      this.markBackendSynthComplete();
    } else if (event.type === "conversation-start") {
      this.stopAudioPlayback(true);
      this.resetPlaybackTurn();
      this.resetAssistantTurn();
      this.updateState({ latestAssistantText: "", aiState: "thinking" });
    } else if (event.type === "conversation-end") {
      this.updateState({
        aiState: this.currentAudio || this.audioQueue.length > 0 ? "speaking" : "idle"
      });
    } else if (event.type === "interrupt") {
      this.stopAudioPlayback(true);
      this.resetPlaybackTurn();
      this.updateState({ aiState: "interrupted" });
    } else if (event.type === "audio-play-start") {
      this.updateState({ aiState: "speaking" });
    } else if (event.type === "assistant-text") {
      const text = this.setAssistantText(event.text);
      if (text) {
        this.updateState({ latestAssistantText: text });
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
