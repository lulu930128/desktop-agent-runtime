export type KuroBackendEvent =
  | { type: "speech-status"; status: string }
  | {
      type: "model-load";
      modelUrl: string;
      scaleWidth: number;
      confName: string;
      confUid: string;
    }
  | {
      type: "assistant-audio";
      speechStatus?: string;
      displayText: string;
      audioBase64: string | null;
      segmentId?: number;
      appendDisplay?: boolean;
    }
  | {
      type: "assistant-text";
      text: string;
    }
  | {
      type: "synth-complete";
    }
  | {
      type: "conversation-start";
    }
  | {
      type: "conversation-end";
    }
  | {
      type: "interrupt";
    }
  | {
      type: "audio-play-start";
    };

export type BackendProtocolAdapter = {
  createPlaybackCompleteMessage: () => unknown;
  toKuroEvents: (payload: Record<string, any>, context: { baseUrl: string }) => KuroBackendEvent[];
};
