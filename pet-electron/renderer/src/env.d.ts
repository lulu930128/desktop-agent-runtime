import type { Live2DInspectorSnapshot } from "./live2d/live2d-inspector";

export {};

declare global {
  interface Window {
    kuroPetElectron: {
      getInitialConfig: () => {
        baseUrl: string;
        wsUrl: string;
        zoomScale: number;
        petHostBounds?: {
          x: number;
          y: number;
          width: number;
          height: number;
        };
        petAnchor?: {
          x: number;
          y: number;
        };
        outfit?: {
          outfitId?: string;
          parameterId?: string;
          parameterIndex?: number | null;
          value?: number;
        };
        expression?: {
          expressionId?: string;
          expressionLabel?: string;
          parameters?: Record<string, number>;
        };
      };
      reportFrontendState: (payload: Record<string, unknown>) => void;
      updateComponentHover: (componentName: string, hovered: boolean) => void;
      setIgnoreMouseEvent: (ignore: boolean) => void;
      startWindowDrag: (screenX: number, screenY: number) => void;
      updateWindowDrag: (screenX: number, screenY: number) => void;
      setPetWindowZoom: (zoomScale: number) => void;
      setPetModelZoom: (zoomScale: number) => void;
      setPetAnchor: (x: number, y: number) => void;
      getScreenCaptureSourceId: () => Promise<string>;
      endWindowDrag: () => void;
      showContextMenu: () => void;
      onCommand: (
        listener: (payload: {
          type: string;
          enabled?: boolean;
          outfitId?: string;
          parameterId?: string;
          parameterIndex?: number | null;
          expressionId?: string;
          expressionLabel?: string;
          parameters?: Record<string, number>;
          group?: string;
          motionIndex?: number | null;
          priority?: number;
          live2dInspectorOverlayEnabled?: boolean;
          zoomScale?: number;
          petHostBounds?: {
            x: number;
            y: number;
            width: number;
            height: number;
          };
          petAnchor?: {
            x: number;
            y: number;
          };
          value?: number;
        }) => void
      ) => () => void;
    };
    __kuroPetRendererState?: Record<string, unknown>;
    __kuroPetSendTextInput?: (
      text: string,
      attachments?: Array<{
        kind?: string;
        name?: string;
        data?: string;
        mime_type?: string;
        type?: string;
        size?: number;
      }>
    ) => Promise<{ ok: boolean; error?: string; text?: string }>;
    __kuroPetApplyBackendConfig?: (
      baseUrl: string,
      wsUrl: string,
      reconnect?: boolean
    ) => { baseUrl: string; wsUrl: string };
    __kuroPetSetInputEnabled?: (
      kind: string,
      enabled: boolean
    ) => Promise<{ ok: boolean; error?: string }> | { ok: boolean; error?: string };
    __kuroPetControlMicrophone?: (
      action: "start" | "pause" | "resume" | "submit" | "cancel"
    ) => Promise<{
      ok: boolean;
      error?: string;
      micEnabled?: boolean;
      micPaused?: boolean;
      submitted?: boolean;
      discarded?: boolean;
      empty?: boolean;
    }>;
    __kuroLive2DInspector?: {
      getSnapshot: () => Live2DInspectorSnapshot;
      setOverlayEnabled: (enabled: boolean) => Live2DInspectorSnapshot;
      toggleOverlay: () => Live2DInspectorSnapshot;
    };
    __kuroLive2DPreview?: {
      capture: (options?: {
        outfitId?: string;
        parameterId?: string;
        parameterIndex?: number | null;
        value?: number;
      }) => Promise<string | null>;
    };
  }
}
