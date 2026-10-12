const http = require("http");
const { withTimeout } = require("./pet-status");

const PET_ACTIONS = new Set([
  "show-pet", "hide-pet", "move-next-display", "reset-pet-position",
  "set-game-mode", "toggle-game-mode", "set-force-ignore-mouse",
  "set-outfit", "set-expression", "play-motion", "set-presentation",
  "set-live2d-inspector", "set-live2d-debug-overlay", "toggle-live2d-inspector",
  "toggle-live2d-debug-overlay", "reload-frontend", "stop-playback",
  "mic-toggle", "mic-start", "mic-pause", "mic-resume", "mic-submit", "mic-cancel",
  "toggle-camera", "toggle-screen", "capture-input"
]);

function writeJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(payload));
}

function writeBinary(res, statusCode, contentType, payload) {
  res.writeHead(statusCode, {
    "Content-Type": contentType,
    "Cache-Control": "no-store"
  });
  res.end(payload);
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > 1024 * 1024 * 2) {
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
  captureLive2DPreview,
  getShellStatus,
  handleControlAction,
  applyRendererBackendConfig,
  log
}) {
  async function readControlState() {
    const renderer = await withTimeout(Promise.resolve().then(readRendererStatus), 350, { available: false });
    return { renderer: renderer || { available: false } };
  }
  if (!["127.0.0.1", "::1", "localhost"].includes(host)) throw new Error("Pet control requires loopback");
  const server = http.createServer(async (req, res) => {
    try {
      const requestUrl = new URL(req.url || "/", "http://127.0.0.1");
      if (req.method === "GET" && requestUrl.pathname === "/status") {
        const state = await readControlState();
        writeJson(res, 200, {
          ok: true,
          ...getShellStatus(),
          ...state
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

      if (req.method === "GET" && requestUrl.pathname === "/live2d-preview.png") {
        const outfitId = String(requestUrl.searchParams.get("outfitId") || "").trim();
        const parameterId = String(requestUrl.searchParams.get("parameterId") || "Param10").trim();
        const parameterIndexRaw = requestUrl.searchParams.get("parameterIndex");
        const valueRaw = requestUrl.searchParams.get("value");
        const captureOptions = {
          outfitId,
          parameterId,
          parameterIndex:
            parameterIndexRaw !== null && Number.isInteger(Number(parameterIndexRaw))
              ? Number(parameterIndexRaw)
              : null,
          value:
            valueRaw !== null && Number.isFinite(Number(valueRaw))
              ? Number(valueRaw)
              : outfitId === "hoodie"
                ? 1
                : outfitId === "normal"
                  ? 0
                  : undefined
        };
        const imageBuffer = typeof captureLive2DPreview === "function"
          ? await captureLive2DPreview(captureOptions)
          : null;
        if (imageBuffer && imageBuffer.length) {
          writeBinary(res, 200, "image/png", imageBuffer);
          return;
        }
        writeJson(res, 503, {
          ok: false,
          error: "Live2D preview capture is not available."
        });
        return;
      }

      if (req.method === "POST" && requestUrl.pathname === "/command") {
        const payload = parseRequestJson(await readRequestBody(req));
        const action = String(payload.action || "").trim();
        if (payload.expectedInstanceId &&
            payload.expectedInstanceId !== getShellStatus().instanceId) {
          writeJson(res, 200, { ok: false, error: "PET_IDENTITY_MISMATCH" });
          return;
        }
        if (!PET_ACTIONS.has(action)) {
          writeJson(res, 400, { ok: false, error: "pet-action-not-allowed" });
          return;
        }
        const result = await handleControlAction(action, payload);
        const state = await readControlState();
        writeJson(res, 200, {
          ok: Boolean(result && result.ok),
          message: result && result.ok ? `command ${action} dispatched` : result?.error || "command failed",
          action,
          result,
          ...state
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
          ok: result?.ok === true,
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
  startControlServer, PET_ACTIONS
};
