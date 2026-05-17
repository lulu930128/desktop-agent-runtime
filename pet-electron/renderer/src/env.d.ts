export {};

declare global {
  interface Window {
    kuroPetElectron: {
      getInitialConfig: () => {
        baseUrl: string;
        wsUrl: string;
        zoomScale: number;
        outfit?: {
          outfitId?: string;
          parameterId?: string;
          parameterIndex?: number | null;
          value?: number;
        };
      };
      reportFrontendState: (payload: Record<string, unknown>) => void;
      updateComponentHover: (componentName: string, hovered: boolean) => void;
      setIgnoreMouseEvent: (ignore: boolean) => void;
      startWindowDrag: (screenX: number, screenY: number) => void;
      updateWindowDrag: (screenX: number, screenY: number) => void;
      setPetWindowZoom: (zoomScale: number) => void;
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
          value?: number;
        }) => void
      ) => () => void;
    };
    __kuroPetRendererState?: Record<string, unknown>;
    __kuroPetSendTextInput?: (
      text: string
    ) => Promise<{ ok: boolean; error?: string; text?: string }>;
    __kuroPetApplyBackendConfig?: (
      baseUrl: string,
      wsUrl: string,
      reconnect?: boolean
    ) => { baseUrl: string; wsUrl: string };
  }
}
