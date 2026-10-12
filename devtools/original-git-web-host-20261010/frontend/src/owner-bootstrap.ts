import { makeOwnerBridge, OwnerTransport, type Port } from "./owner-bridge";
import { installPresentationGuards } from "./owner-presentation";
import { installPresentationPreferences } from "./owner-preferences";

// No import of preview-bridge / synthetic / qt.ts. No renderer until handshake.
async function boot(): Promise<void> {
  const w = window as unknown as {qt?: {webChannelTransport: unknown}; QWebChannel?: new (transport: unknown, ready: (channel: {objects: {workPort: Port}}) => void) => unknown};
  if (!w.qt?.webChannelTransport) throw new Error("Qt owner unavailable");
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Qt channel unavailable")), 5000);
    const script = document.createElement("script"); script.src = "/qwebchannel.js";
    script.onload = () => { clearTimeout(timer); resolve(); };
    script.onerror = () => { clearTimeout(timer); reject(new Error("Qt channel unavailable")); };
    document.head.appendChild(script);
  });
  const port = await new Promise<Port>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Qt handshake timeout")), 5000);
    new w.QWebChannel!(w.qt!.webChannelTransport, channel => {
      clearTimeout(timer);
      const port = channel.objects.workPort;
      if (typeof port?.submit !== "function" || !port.response || !port.event) reject(new Error("Qt owner invalid"));
      else resolve(port);
    });
  });
  const transport = new OwnerTransport(port);
  await transport.hello();
  Object.defineProperty(window, "kuroWorkPanel", {value: makeOwnerBridge(transport), writable: false, configurable: false});
  installPresentationGuards(transport);
  installPresentationPreferences(window);
  await import("./work-panel/main");
}

void boot().catch(() => {
  const root = document.getElementById("app");
  if (root) root.textContent = "Work Companion 未連接 Qt owner；請使用原有 Qt 視窗。候選介面尚未啟用。";
});
