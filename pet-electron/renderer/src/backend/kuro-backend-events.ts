import type { BackendFilePayload, BackendImagePayload } from "./types";

export type KuroBackendEvent =
  | {
      type: "model-load";
      modelUrl: string;
      scaleWidth: number;
      confName: string;
      confUid: string;
    }
  | {
      type: "history-selected";
      historyUid: string;
      historyTitle: string;
    }
  | {
      type: "assistant-audio";
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

export type TextInputPayload = {
  text: string;
  images: BackendImagePayload[];
  files: BackendFilePayload[];
};

export type MicAudioEndPayload = {
  images: BackendImagePayload[];
};

export type BackendProtocolAdapter = {
  createHistoryStartMessage: () => unknown;
  createTextInputMessage: (payload: TextInputPayload) => unknown;
  createInterruptMessage: () => unknown;
  createPlaybackCompleteMessage: () => unknown;
  createMicAudioDataMessage: (audio: number[]) => unknown;
  createMicAudioEndMessage: (payload: MicAudioEndPayload) => unknown;
  toKuroEvents: (payload: Record<string, any>, context: { baseUrl: string }) => KuroBackendEvent[];
};
