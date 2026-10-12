export type RendererState = {
  speechStatus?: string;
  wsConnected: boolean;
  aiState: string;
  latestAssistantText: string;
  wsUrl: string;
  baseUrl: string;
  currentModelUrl: string;
  confName: string;
  confUid: string;
  currentOutfitId: string;
  currentOutfitParameterId: string;
  currentOutfitParameterIndex: number | null;
  currentOutfitValue: number;
  currentExpressionId: string;
  currentExpressionLabel: string;
  micEnabled: boolean;
  micPaused: boolean;
  cameraEnabled: boolean;
  screenEnabled: boolean;
  live2dInspectorOverlayEnabled: boolean;
};

export type MicrophoneControlAction = "start" | "pause" | "resume" | "submit" | "cancel";

export type MicrophoneControlResult = {
  ok: boolean;
  error?: string;
  micEnabled?: boolean;
  micPaused?: boolean;
  capture?: { format: "pcm16le"; sampleRate: number; data: string };
  images?: BackendImagePayload[];
  discarded?: boolean;
  empty?: boolean;
};

export type BackendConfig = {
  baseUrl: string;
  wsUrl: string;
};

export type BackendImagePayload = {
  source: "camera" | "screen" | "upload";
  data: string;
  mime_type: string;
};



export type SpeechLipSyncEnvelope = {
  values: number[];
  frameRate: number;
  duration: number;
};
