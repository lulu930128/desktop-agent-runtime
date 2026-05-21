import type { BackendProtocolAdapter, KuroBackendEvent } from "../kuro-backend-events";
import { buildAbsoluteModelUrl, normalizeText } from "../text-utils";

export const llmVtuberAdapter: BackendProtocolAdapter = {
  createHistoryStartMessage() {
    return {
      type: "create-new-history"
    };
  },

  createTextInputMessage({ text, images, files }) {
    return {
      type: "text-input",
      text,
      ...(images.length ? { images } : {}),
      ...(files.length ? { files } : {})
    };
  },

  createInterruptMessage() {
    return {
      type: "interrupt-signal",
      text: "launcher-interrupt"
    };
  },

  createPlaybackCompleteMessage() {
    return {
      type: "frontend-playback-complete"
    };
  },

  createMicAudioDataMessage(audio) {
    return {
      type: "mic-audio-data",
      audio
    };
  },

  createMicAudioEndMessage({ images }) {
    return {
      type: "mic-audio-end",
      ...(images.length ? { images } : {})
    };
  },

  toKuroEvents(payload, context) {
    const messageType = String(payload.type || "");
    const events: KuroBackendEvent[] = [];

    if (messageType === "set-model-and-conf") {
      const modelInfo = payload.model_info || {};
      const rawUrl = String(modelInfo.url || "").trim();
      if (rawUrl) {
        events.push({
          type: "model-load",
          modelUrl: buildAbsoluteModelUrl(context.baseUrl, rawUrl),
          scaleWidth: Math.max(0.8, Number(modelInfo.kScale || 0.45) * 2),
          confName: normalizeText(payload.conf_name || ""),
          confUid: normalizeText(payload.conf_uid || "")
        });
      }
      return events;
    }

    if (messageType === "history-list") {
      const histories = Array.isArray(payload.histories) ? payload.histories : [];
      const selected = histories[0] || {};
      const historyUid = normalizeText(selected.uid || selected.history_uid || "");
      if (historyUid) {
        events.push({
          type: "history-selected",
          historyUid,
          historyTitle: normalizeText(selected.title || "")
        });
      }
      return events;
    }

    if (messageType === "new-history-created" || messageType === "config-switched") {
      const historyUid = normalizeText(payload.history_uid || "");
      if (historyUid) {
        events.push({
          type: "history-selected",
          historyUid,
          historyTitle: ""
        });
      }
      return events;
    }

    if (messageType === "audio") {
      events.push({
        type: "assistant-audio",
        displayText: normalizeText(payload.display_text?.text || ""),
        audioBase64: payload.audio || null
      });
      return events;
    }

    if (messageType === "backend-synth-complete") {
      events.push({ type: "synth-complete" });
      return events;
    }

    if (messageType === "control") {
      const text = String(payload.text || "");
      if (text === "conversation-chain-start") {
        events.push({ type: "conversation-start" });
      } else if (text === "conversation-chain-end") {
        events.push({ type: "conversation-end" });
      } else if (text === "interrupt" || text === "interrupt-signal") {
        events.push({ type: "interrupt" });
      } else if (text === "audio-play-start") {
        events.push({ type: "audio-play-start" });
      }
      return events;
    }

    if (messageType === "full-text") {
      const text = normalizeText(payload.text || "");
      if (text) {
        events.push({
          type: "assistant-text",
          text
        });
      }
    }

    return events;
  }
};
