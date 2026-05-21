const http = require("http");

function writeJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(payload));
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > 1024 * 256) {
        reject(new Error("Request body too large."));
        req.destroy();
      }
    });
    req.on("end", () => resolve(raw));
    req.on("error", reject);
  });
}

function parseRequestJson(raw) {
  return raw ? JSON.parse(raw) : {};
}

function startControlServer({
  host,
  port,
  readRendererStatus,
  readLive2DInspectorSnapshot,
  getShellStatus,
  isReaderVisible,
  handleControlAction,
  applyRendererBackendConfig,
  log
}) {
  const server = http.createServer(async (req, res) => {
    const requestUrl = new URL(req.url || "/", `http://${host}:${port}`);

    try {
      if (req.method === "GET" && requestUrl.pathname === "/status") {
        const renderer = await readRendererStatus();
        renderer.readerVisible = isReaderVisible();
        writeJson(res, 200, {
          ok: true,
          ...getShellStatus(),
          renderer
        });
        return;
      }

      if (req.method === "GET" && requestUrl.pathname === "/live2d-inspector") {
        const snapshot = typeof readLive2DInspectorSnapshot === "function"
          ? await readLive2DInspectorSnapshot()
          : null;
        writeJson(res, 200, {
          ok: Boolean(snapshot),
          snapshot
        });
        return;
      }

      if (req.method === "POST" && requestUrl.pathname === "/command") {
        const payload = parseRequestJson(await readRequestBody(req));
        const action = String(payload.action || "").trim();
        const result = await handleControlAction(action, payload);
        const renderer = await readRendererStatus();
        renderer.readerVisible = isReaderVisible();
        writeJson(res, 200, {
          ok: Boolean(result && result.ok),
          message: result && result.ok ? `command ${action} dispatched` : result.error || "command failed",
          action,
          result,
          renderer
        });
        return;
      }

      if (req.method === "POST" && requestUrl.pathname === "/backend-config") {
        const payload = parseRequestJson(await readRequestBody(req));
        const baseUrl = String(payload.baseUrl || "").trim();
        const wsUrl = String(payload.wsUrl || "").trim();
        const reload = payload.reload !== false;
        const result = await applyRendererBackendConfig(baseUrl, wsUrl, reload);
        const renderer = await readRendererStatus();
        writeJson(res, 200, {
          ok: true,
          message: reload ? "backend config updated and frontend reloaded" : "backend config updated",
          result,
          renderer
        });
        return;
      }

      writeJson(res, 404, {
        ok: false,
        error: "Not found"
      });
    } catch (error) {
      log("control-server-error", error);
      writeJson(res, 500, {
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  });

  server.on("error", (error) => {
    log("control-server-listen-error", error);
  });

  server.listen(port, host, () => {
    log("control-server-ready", {
      host,
      port
    });
  });

  return server;
}

module.exports = {
  startControlServer
};
