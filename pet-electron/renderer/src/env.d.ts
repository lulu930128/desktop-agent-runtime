export {};

declare global {
  interface Window {
    kuroPetElectron: {
      getInitialConfig: () => { baseUrl: string; wsUrl: string; zoomScale: number };
      reportFrontendState: (payload: Record<string, unknown>) => void;
      updateComponentHover: (componentName: string, hovered: boolean) => void;
      setIgnoreMouseEvent: (ignore: boolean) => void;
      startWindowDrag: (screenX: number, screenY: number) => void;
      updateWindowDrag: (screenX: number, screenY: number) => void;
      setPetWindowZoom: (zoomScale: number) => void;
      endWindowDrag: () => void;
      showContextMenu: () => void;
      onCommand: (listener: (payload: { type: string }) => void) => () => void;
    };
    __kuroPetRendererState?: Record<string, unknown>;
    __kuroPetSendTextInput?: (text: string) => { ok: boolean; error?: string; text?: string };
    __kuroPetApplyBackendConfig?: (
      baseUrl: string,
      wsUrl: string,
      reconnect?: boolean
    ) => { baseUrl: string; wsUrl: string };
  }
}
