import { boot, makeBridge, type Request } from "./preview-bridge";
import fixture from "./synthetic.json";

declare global {
  interface Window {
    qt?: { webChannelTransport: unknown };
    QWebChannel?: new (transport: unknown, ready: (channel: { objects: { previewPort: {
      request: (request: string, callback: (response: string) => void) => void;
    } } }) => void) => unknown;
  }
}

async function connect(): Promise<Request> {
  if (!window.qt?.webChannelTransport) throw new Error("Qt WebChannel unavailable (no browser fallback)");
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("WebChannel script timeout")), 5000);
    const script = document.createElement("script");
    script.src = "qrc:///qtwebchannel/qwebchannel.js";
    script.onload = () => { clearTimeout(timeout); resolve(); };
    script.onerror = () => { clearTimeout(timeout); reject(new Error("WebChannel script unavailable")); };
    document.head.appendChild(script);
  });
  return new Promise<Request>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("WebChannel handshake timeout")), 5000);
    new window.QWebChannel!(window.qt!.webChannelTransport, (channel) => {
      clearTimeout(timeout);
      if (typeof channel?.objects?.previewPort?.request !== "function") {
        reject(new Error("Qt preview port unavailable"));
        return;
      }
      let sequence = 0;
      resolve((command, payload = {}) => new Promise((done) => {
        const id = ++sequence;
        const timer = setTimeout(() => done({ok: false, error: "Qt bridge timeout; no retry"}), 5000);
        channel.objects.previewPort.request(JSON.stringify({id, context: fixture.context, revision: fixture.revision, command, payload}), (raw) => {
          clearTimeout(timer);
          try {
            const reply = JSON.parse(raw);
            if (reply.id !== id || reply.context !== fixture.context || reply.revision !== fixture.revision) throw new Error("stale context");
            done(reply.result);
          } catch { done({ok: false, error: "Invalid Qt bridge response"}); }
        });
      }));
    });
  });
}

void connect().then((request) => boot(makeBridge(request))).catch((error) => {
  document.getElementById("app")!.textContent = `SYNTHETIC Qt preview BLOCKED: ${String(error)}`;
});
