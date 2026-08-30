import { BackendClient } from "../backend/backend-client";
import type { RendererState } from "../backend/types";
import { PetLive2DRenderer } from "../live2d/pet-live2d-renderer";
import { storeModelZoomScale } from "../model-zoom";
import { applyPetGeometryCommand } from "./pet-command-geometry";

type BindPetCommandsOptions = {
  client: BackendClient;
  renderer: PetLive2DRenderer;
  reportState: (patch: Partial<RendererState>) => void;
  defaultOutfitParameterId: string;
  onTransformAccepted?: () => void;
  onHostAccepted?: (bounds: {
    x: number;
    y: number;
    width: number;
    height: number;
  }) => void;
};

export function bindPetCommands({
  client,
  renderer,
  reportState,
  defaultOutfitParameterId,
  onTransformAccepted,
  onHostAccepted
}: BindPetCommandsOptions): () => void {
  return window.kuroPetElectron.onCommand((payload) => {
    if (!payload || typeof payload.type !== "string") {
      return;
    }

    const geometryResult = applyPetGeometryCommand(renderer, payload);
    if (geometryResult.handled) {
      if (geometryResult.transformAccepted) {
        storeModelZoomScale(renderer.getZoomScale());
        onTransformAccepted?.();
      }
      if (geometryResult.hostAccepted && payload.petHostBounds) {
        onHostAccepted?.(payload.petHostBounds);
      }
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
    } else if (payload.type === "live2d-inspector-set") {
      const live2dInspectorOverlayEnabled = renderer.setInspectorOverlayEnabled(
        Boolean(payload.enabled)
      );
      reportState({ live2dInspectorOverlayEnabled });
    }
  });
}
