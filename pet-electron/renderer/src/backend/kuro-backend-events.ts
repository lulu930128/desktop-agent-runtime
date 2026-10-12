export type KuroBackendEvent =
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
