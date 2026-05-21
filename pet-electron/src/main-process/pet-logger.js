const fs = require("fs");
const path = require("path");

function stringifyLogPart(part) {
  if (part instanceof Error) {
    return `${part.message}\n${part.stack || ""}`;
  }
  if (typeof part === "string") {
    return part;
  }
  try {
    return JSON.stringify(part);
  } catch {
    return String(part);
  }
}

function createPetLogger(app) {
  return function petLog(...parts) {
    const line = `[${new Date().toISOString()}] ${parts.map(stringifyLogPart).join(" ")}`;

    console.log(line);

    if (!app.isReady()) {
      return;
    }

    try {
      const logPath = path.join(app.getPath("userData"), "pet-shell.log");
      fs.appendFileSync(logPath, `${line}\n`, "utf8");
    } catch (error) {
      console.warn("[pet-electron] Failed to write log file:", error);
    }
  };
}

module.exports = {
  createPetLogger
};
