const http = require("http");

function createCoreClient({ url, token, instance, timeoutMs = 4000 }) {
  async function request(route, payload) {
    let target;
    try {
      target = new URL(url);
      if (target.protocol !== "http:" || target.hostname !== "127.0.0.1" || target.username || target.password || !token || !instance) throw new Error();
      target.pathname = route.split("?")[0];
      target.search = route.includes("?") ? route.slice(route.indexOf("?")) : "";
      target.hash = "";
    } catch {
      return { ok: false, error: "core_not_configured" };
    }
    const body = payload === undefined ? null : JSON.stringify(payload);
    if (body && Buffer.byteLength(body) > 65536) return { ok: false, error: "invalid_request" };
    return new Promise((resolve) => {
      const req = http.request(target, { method: body === null ? "GET" : "POST", headers: {
        Authorization: `Bearer ${token}`, "Content-Type": "application/json",
        ...(body === null ? {} : { "Content-Length": Buffer.byteLength(body) })
      } }, (res) => {
        const chunks = []; let size = 0;
        res.on("data", (chunk) => {
          size += chunk.length;
          if (size > 4 * 1024 * 1024) req.destroy(new Error("response_too_large"));
          else chunks.push(chunk);
        });
        res.on("end", () => {
          try {
            const value = JSON.parse(Buffer.concat(chunks).toString("utf8"));
            resolve(value && typeof value === "object" && !Array.isArray(value) ? value : { ok: false, error: "invalid_response" });
          } catch { resolve({ ok: false, error: "invalid_response" }); }
        });
        res.on("error", () => resolve({ ok: false, error: "core_unavailable" }));
      });
      req.setTimeout(timeoutMs, () => req.destroy(new Error("timeout")));
      req.on("error", () => resolve({ ok: false, error: "core_unavailable" }));
      req.end(body);
    });
  }
  async function call(action, payload = {}) {
    if (!["status", "view", "item", "mutate", "materialize", "prepare", "notifications", "notification-action"].includes(action) || !payload || typeof payload !== "object" || Array.isArray(payload)) return { ok: false, error: "invalid_request" };
    const health = await request("/status");
    if (!health.ok) return health;
    if (health.service !== "kuro-core" || health.instanceId !== instance || health.schema !== 3 || health.contract !== "kuro.core.schedule.v1") return { ok: false, error: "core_identity_mismatch" };
    if (action === "status") return health;
    if (["mutate","materialize","prepare","notification-action"].includes(action)) return request(`/v1/schedule/${action}`, payload);
    if (action === "notifications") return request("/v1/schedule/notifications");
    const allowed = action === "view" ? ["start", "end", "timezone", "limit", "offset"] : ["id"];
    if (Object.keys(payload).some((key) => !allowed.includes(key))) return { ok: false, error: "invalid_request" };
    return request(`/v1/schedule/${action}?${new URLSearchParams(payload)}`);
  }
  return { call };
}

function registerCoreIpc(ipcMain, client, getWindow) {
  ipcMain.handle("work-panel-schedule", (event, action, payload) => {
    const window = getWindow();
    if (!window || window.isDestroyed() || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) return { ok: false, error: "unauthorized_sender" };
    if (action === "notification-action" && !["dismiss","snooze","preferences"].includes(payload?.action)) return {ok:false,error:"unauthorized_action"};
    return client.call(action, payload);
  });
}

module.exports = { createCoreClient, registerCoreIpc };
