const fs = require("fs");
const path = require("path");

const DEFAULT_STATE = {
  mode: "pet",
  forceIgnoreMouse: true,
  petSpanAllDisplays: true,
  petZoomScale: 1,
  petAnchor: null,
  petGameMode: false,
  readerVisible: true,
  outfit: {
    outfitId: "normal",
    parameterId: "Param10",
    parameterIndex: null,
    value: 0
  },
  expression: {
    expressionId: "neutral",
    expressionLabel: "一般",
    parameters: {}
  },
  boundsByMode: {
    pet: {
      x: 96,
      y: 96,
      width: 500,
      height: 760
    },
    window: {
      x: 80,
      y: 80,
      width: 1280,
      height: 860
    }
  },
  readerBounds: {
    x: 540,
    y: 120,
    width: 440,
    height: 240
  }
};

function cloneDefaultState() {
  return JSON.parse(JSON.stringify(DEFAULT_STATE));
}

function mergeState(candidate) {
  const next = cloneDefaultState();

  if (!candidate || typeof candidate !== "object") {
    return next;
  }

  if (candidate.mode === "window" || candidate.mode === "pet") {
    next.mode = candidate.mode;
  }

  if (typeof candidate.forceIgnoreMouse === "boolean") {
    next.forceIgnoreMouse = candidate.forceIgnoreMouse;
  }

  if (typeof candidate.petSpanAllDisplays === "boolean") {
    next.petSpanAllDisplays = candidate.petSpanAllDisplays;
  }

  if (typeof candidate.petGameMode === "boolean") {
    next.petGameMode = candidate.petGameMode;
  }

  if (Number.isFinite(candidate.petZoomScale)) {
    next.petZoomScale = Math.max(0.2, Math.min(8, Number(candidate.petZoomScale)));
  }

  if (candidate.petAnchor && typeof candidate.petAnchor === "object") {
    const x = Number(candidate.petAnchor.x);
    const y = Number(candidate.petAnchor.y);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      next.petAnchor = {
        x: Math.round(x),
        y: Math.round(y)
      };
    }
  }

  if (typeof candidate.readerVisible === "boolean") {
    next.readerVisible = candidate.readerVisible;
  }

  if (candidate.outfit && typeof candidate.outfit === "object") {
    const outfit = candidate.outfit;
    const parameterId = String(outfit.parameterId || "Param10");
    const normalizedParameterId = parameterId === "\u5e3dT" ? "Param10" : parameterId;
    next.outfit = {
      outfitId: String(outfit.outfitId || "normal"),
      parameterId: normalizedParameterId,
      parameterIndex:
        normalizedParameterId === "Param10"
          ? null
          : Number.isInteger(outfit.parameterIndex) && outfit.parameterIndex >= 0
            ? outfit.parameterIndex
            : null,
      value: Number.isFinite(Number(outfit.value))
        ? Math.max(0, Math.min(1, Number(outfit.value)))
        : 0
    };
  }

  if (candidate.expression && typeof candidate.expression === "object") {
    const expression = candidate.expression;
    const parameters = {};
    if (expression.parameters && typeof expression.parameters === "object") {
      for (const [key, value] of Object.entries(expression.parameters)) {
        const parameterId = String(key || "").trim();
        const numberValue = Number(value);
        if (!parameterId || !Number.isFinite(numberValue)) {
          continue;
        }
        parameters[parameterId] = Math.max(-1, Math.min(1, numberValue));
      }
    }
    next.expression = {
      expressionId: String(expression.expressionId || "neutral"),
      expressionLabel: String(expression.expressionLabel || "一般"),
      parameters
    };
  }

  if (candidate.boundsByMode && typeof candidate.boundsByMode === "object") {
    for (const mode of ["pet", "window"]) {
      const bounds = candidate.boundsByMode[mode];
      if (!bounds || typeof bounds !== "object") {
        continue;
      }

      const current = next.boundsByMode[mode];
      next.boundsByMode[mode] = {
        x: Number.isFinite(bounds.x) ? Math.round(bounds.x) : current.x,
        y: Number.isFinite(bounds.y) ? Math.round(bounds.y) : current.y,
        width: Number.isFinite(bounds.width) ? Math.round(bounds.width) : current.width,
        height: Number.isFinite(bounds.height) ? Math.round(bounds.height) : current.height
      };
    }
  }

  if (candidate.readerBounds && typeof candidate.readerBounds === "object") {
    const bounds = candidate.readerBounds;
    const current = next.readerBounds;
    next.readerBounds = {
      x: Number.isFinite(bounds.x) ? Math.round(bounds.x) : current.x,
      y: Number.isFinite(bounds.y) ? Math.round(bounds.y) : current.y,
      width: Number.isFinite(bounds.width) ? Math.round(bounds.width) : current.width,
      height: Number.isFinite(bounds.height) ? Math.round(bounds.height) : current.height
    };
  }

  return next;
}

function loadState(statePath) {
  try {
    if (!fs.existsSync(statePath)) {
      return cloneDefaultState();
    }

    const raw = fs.readFileSync(statePath, "utf8");
    return mergeState(JSON.parse(raw));
  } catch (error) {
    console.warn("[pet-electron] Failed to load state, using defaults:", error);
    return cloneDefaultState();
  }
}

function saveState(statePath, state) {
  const normalized = mergeState(state);
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  fs.writeFileSync(statePath, JSON.stringify(normalized, null, 2), "utf8");
}

module.exports = {
  DEFAULT_STATE,
  cloneDefaultState,
  loadState,
  mergeState,
  saveState
};
