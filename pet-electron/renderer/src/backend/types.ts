export type RendererState = {
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
  currentOutfitId: string;
  currentOutfitParameterId: string;
  currentOutfitParameterIndex: number | null;
  currentOutfitValue: number;
  currentExpressionId: string;
  currentExpressionLabel: string;
  micEnabled: boolean;
  cameraEnabled: boolean;
  screenEnabled: boolean;
  browserPanelEnabled: boolean;
  live2dInspectorOverlayEnabled: boolean;
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

export type BackendFilePayload = {
  name: string;
  data: string;
  mime_type: string;
  size?: number;
  kind?: string;
};

export type UserAttachmentPayload = {
  kind?: string;
  name?: string;
  data?: string;
  mime_type?: string;
  type?: string;
  size?: number;
};

export type SpeechLipSyncEnvelope = {
  values: number[];
  frameRate: number;
  duration: number;
};
