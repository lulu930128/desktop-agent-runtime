import { BackendClient } from "../backend/backend-client";
import type { RendererState } from "../backend/types";
import { PetLive2DRenderer } from "../live2d/pet-live2d-renderer";

type BindPetCommandsOptions = {
  client: BackendClient;
  renderer: PetLive2DRenderer;
  reportState: (patch: Partial<RendererState>) => void;
  defaultOutfitParameterId: string;
};

export function bindPetCommands({
  client,
  renderer,
  reportState,
  defaultOutfitParameterId
}: BindPetCommandsOptions): () => void {
  return window.kuroPetElectron.onCommand((payload) => {
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
    } else if (payload.type === "outfit-set") {
      const outfitId = String(payload.outfitId || "normal");
      const parameterId = String(payload.parameterId || defaultOutfitParameterId);
      const parameterIndex =
        Number.isInteger(payload.parameterIndex) && payload.parameterIndex !== null
          ? payload.parameterIndex
          : null;
      const value = Math.min(1, Math.max(0, Number(payload.value) || 0));
      renderer.setOutfitParameter(parameterId, value, parameterIndex);
      reportState({
        currentOutfitId: outfitId,
        currentOutfitParameterId: parameterId,
        currentOutfitParameterIndex: parameterIndex,
        currentOutfitValue: value
      });
    } else if (payload.type === "expression-set") {
      const expressionId = String(payload.expressionId || "neutral");
      const expressionLabel = String(payload.expressionLabel || expressionId);
      const parameters = payload.parameters || {};
      renderer.setExpressionId(expressionId);
      renderer.setExpressionParameters(parameters);
      reportState({
        currentExpressionId: expressionId,
        currentExpressionLabel: expressionLabel
      });
    } else if (payload.type === "motion-play") {
      const group = String(payload.group || "Idle");
      const motionIndex =
        Number.isInteger(payload.motionIndex) && payload.motionIndex !== null
          ? Number(payload.motionIndex)
          : null;
      const priority = Number.isInteger(payload.priority)
        ? Number(payload.priority)
        : undefined;
      renderer.playMotion(group, motionIndex, priority);
    } else if (payload.type === "pet-zoom-set") {
      renderer.setZoomScale(Number(payload.zoomScale));
    } else if (payload.type === "pet-host-set" || payload.type === "pet-anchor-set") {
      renderer.setHostBounds(payload.petHostBounds);
      if (payload.petAnchor) {
        renderer.setAnchorScreenPoint(payload.petAnchor.x, payload.petAnchor.y);
      }
    }
  });
}
