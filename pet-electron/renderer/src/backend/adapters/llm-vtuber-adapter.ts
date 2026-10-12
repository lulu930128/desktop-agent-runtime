import type { BackendProtocolAdapter, KuroBackendEvent } from "../kuro-backend-events";
import { buildAbsoluteModelUrl, normalizeText } from "../text-utils";

export const llmVtuberAdapter: BackendProtocolAdapter = {
  createPlaybackCompleteMessage() {
    return {
      type: "frontend-playback-complete"
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

    if (messageType === "audio") {
      events.push({
        type: "assistant-audio",
        speechStatus: typeof payload.speech_status === 'string' ? payload.speech_status : undefined,
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
