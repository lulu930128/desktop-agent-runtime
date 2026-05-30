const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

const DEFAULT_INTERVAL_SECONDS = 900;
const MIN_INTERVAL_SECONDS = 300;
const DEFAULT_MAX_RESULTS = 12;
const MAX_MAIL_RESULTS = 500;
const DEFAULT_NEWER_THAN_DAYS = 7;
const DEFAULT_PREFERENCES = {
  version: 1,
  autoRefresh: true,
  intervalSeconds: DEFAULT_INTERVAL_SECONDS,
  maxResults: DEFAULT_MAX_RESULTS,
  newerThanDays: DEFAULT_NEWER_THAN_DAYS,
  unreadOnly: true,
  extraQuery: "",
  focusSenders: [],
  focusDomains: [],
  focusKeywords: [],
  ignoreSenders: [],
  ignoreDomains: [],
  ignoreKeywords: []
};
const DEFAULT_RULES = {
  version: 1,
  rules: []
};

function toPositiveInt(value, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.floor(parsed);
}

function clampInt(value, fallback, min, max) {
  return Math.max(min, Math.min(max, toPositiveInt(value, fallback)));
}

function normalizeRuleText(value, maxLength = 120) {
  let normalized = String(value || "").trim().replace(/\s+/g, " ").slice(0, maxLength);
  const addressMatch = normalized.match(/<([^<>\s]+@[^<>\s]+)>/);
  if (addressMatch) {
    normalized = addressMatch[1];
  }
  if (normalized.startsWith("<") && normalized.endsWith(">")) {
    normalized = normalized.slice(1, -1).trim();
  }
  return normalized;
}

function normalizeList(value, maxItems = 80, maxLength = 120) {
  const rawItems = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.replace(/,/g, "\n").split(/\r?\n/)
      : [];
  const output = [];
  const seen = new Set();
  for (const item of rawItems) {
    const normalized = normalizeRuleText(item, maxLength);
    const key = normalized.toLocaleLowerCase();
    if (!normalized || seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push(normalized);
    if (output.length >= maxItems) {
      break;
    }
  }
  return output;
}

function normalizeRuleCondition(raw) {
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const field = normalizeRuleText(source.field || "text", 48);
  const op = normalizeRuleText(source.op || "containsAny", 32);
  const value = Array.isArray(source.value)
    ? normalizeList(source.value, 40, 240)
    : normalizeRuleText(source.value, 500);
  if (!field || !op || (Array.isArray(value) && !value.length) || (!Array.isArray(value) && !value)) {
    return null;
  }
  return { field, op, value };
}

function normalizeConditionGroup(value) {
  const source = Array.isArray(value) ? value : [];
  return source.map(normalizeRuleCondition).filter(Boolean).slice(0, 16);
}

function normalizeExtractRule(raw) {
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const key = normalizeRuleText(source.key, 48);
  const pattern = String(source.pattern || "").trim().slice(0, 500);
  if (!key || !pattern) {
    return null;
  }
  return {
    key,
    label: normalizeRuleText(source.label || key, 80),
    pattern
  };
}

function normalizeMailRule(raw) {
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const id = normalizeRuleText(source.id, 80);
  const type = normalizeRuleText(source.type || "required_event", 32);
  if (!id || !["required_event", "mute"].includes(type)) {
    return null;
  }
  const when = source.if && typeof source.if === "object" && !Array.isArray(source.if)
    ? source.if
    : {};
  const then = source.then && typeof source.then === "object" && !Array.isArray(source.then)
    ? source.then
    : {};
  return {
    id,
    name: normalizeRuleText(source.name || id, 120),
    type,
    enabled: source.enabled !== false,
    if: {
      all: normalizeConditionGroup(when.all),
      any: normalizeConditionGroup(when.any),
      none: normalizeConditionGroup(when.none)
    },
    then: {
      priority: normalizeRuleText(then.priority || (type === "required_event" ? "high" : ""), 24),
      category: normalizeRuleText(then.category || type, 80),
      score: clampInt(then.score, 100, -100, 200),
      scorePenalty: clampInt(then.scorePenalty, 80, 0, 200),
      fetchFullBody: Boolean(then.fetchFullBody),
      tags: normalizeList(then.tags, 12, 40),
      extract: Array.isArray(then.extract)
        ? then.extract.map(normalizeExtractRule).filter(Boolean).slice(0, 12)
        : []
    }
  };
}

function normalizeRulesPayload(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const rawRules = Array.isArray(source.rules)
    ? source.rules
    : Array.isArray(value)
      ? value
      : [];
  const seen = new Set();
  const rules = [];
  for (const rawRule of rawRules) {
    const rule = normalizeMailRule(rawRule);
    if (!rule || seen.has(rule.id)) {
      continue;
    }
    seen.add(rule.id);
    rules.push(rule);
  }
  return {
    version: 1,
    rules
  };
}

function normalizePreferences(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    version: 1,
    autoRefresh: typeof source.autoRefresh === "boolean"
      ? source.autoRefresh
      : DEFAULT_PREFERENCES.autoRefresh,
    intervalSeconds: clampInt(
      source.intervalSeconds,
      DEFAULT_PREFERENCES.intervalSeconds,
      MIN_INTERVAL_SECONDS,
      86400
    ),
    maxResults: clampInt(source.maxResults, DEFAULT_PREFERENCES.maxResults, 1, MAX_MAIL_RESULTS),
    newerThanDays: clampInt(source.newerThanDays, DEFAULT_PREFERENCES.newerThanDays, 1, 365),
    unreadOnly: typeof source.unreadOnly === "boolean"
      ? source.unreadOnly
      : DEFAULT_PREFERENCES.unreadOnly,
    extraQuery: String(source.extraQuery || "").trim().replace(/\s+/g, " ").slice(0, 240),
    focusSenders: normalizeList(source.focusSenders),
    focusDomains: normalizeList(source.focusDomains),
    focusKeywords: normalizeList(source.focusKeywords),
    ignoreSenders: normalizeList(source.ignoreSenders),
    ignoreDomains: normalizeList(source.ignoreDomains),
    ignoreKeywords: normalizeList(source.ignoreKeywords)
  };
}

function resolvePython(repoRoot) {
  const pythonPath = process.env.KURO_MAIL_PYTHON;
  if (pythonPath) {
    return pythonPath;
  }
  return path.join(repoRoot, "envs", "kuro-llm310", "python.exe");
}

function readPreferencesFile(preferencesPath) {
  const fallback = defaultPreferencesFromEnv();
  try {
    if (!fs.existsSync(preferencesPath)) {
      return fallback;
    }
    return normalizePreferences({
      ...fallback,
      ...JSON.parse(fs.readFileSync(preferencesPath, "utf8"))
    });
  } catch (_error) {
    return fallback;
  }
}

function writePreferencesFile(preferencesPath, preferences) {
  fs.mkdirSync(path.dirname(preferencesPath), { recursive: true });
  fs.writeFileSync(preferencesPath, JSON.stringify(normalizePreferences(preferences), null, 2), "utf8");
}

function readRulesFile(rulesPath) {
  try {
    if (!fs.existsSync(rulesPath)) {
      return DEFAULT_RULES;
    }
    return normalizeRulesPayload(JSON.parse(fs.readFileSync(rulesPath, "utf8")));
  } catch (_error) {
    return DEFAULT_RULES;
  }
}

function writeRulesFile(rulesPath, rulesPayload) {
  fs.mkdirSync(path.dirname(rulesPath), { recursive: true });
  fs.writeFileSync(rulesPath, JSON.stringify(normalizeRulesPayload(rulesPayload), null, 2), "utf8");
}

function defaultPreferencesFromEnv() {
  return normalizePreferences({
    ...DEFAULT_PREFERENCES,
    intervalSeconds: process.env.KURO_MAIL_POLL_INTERVAL_SECONDS || DEFAULT_PREFERENCES.intervalSeconds,
    maxResults: process.env.KURO_MAIL_MAX_RESULTS || DEFAULT_PREFERENCES.maxResults,
    newerThanDays: process.env.KURO_MAIL_NEWER_THAN_DAYS || DEFAULT_PREFERENCES.newerThanDays
  });
}

function createMailBriefingService({
  repoRoot,
  controlHost,
  controlPort,
  log,
  onStatusChange
}) {
  const python = resolvePython(repoRoot);
  const script = path.join(repoRoot, "Open-LLM-VTuber", "local_mcp", "mail_briefing_poller.py");
  const messageReaderScript = path.join(
    repoRoot,
    "Open-LLM-VTuber",
    "local_mcp",
    "mail_message_reader.py"
  );
  const preferencesPath = process.env.KURO_GMAIL_PREFERENCES_FILE
    || path.join(repoRoot, "Open-LLM-VTuber", "private", "gmail", "mail_preferences.json");
  const rulesPath = process.env.KURO_GMAIL_RULES_FILE
    || path.join(repoRoot, "Open-LLM-VTuber", "private", "gmail", "mail_rules.json");
  const petControlUrl = process.env.KURO_PET_CONTROL_URL || `http://${controlHost}:${controlPort}`;
  let preferences = readPreferencesFile(preferencesPath);
  let rulesData = readRulesFile(rulesPath);

  let poller = null;
  let refreshProcess = null;
  let messageReadProcess = null;
  let stdoutBuffer = "";
  let status = {
    enabled: false,
    running: false,
    inFlight: false,
    preferencesPath,
    rulesPath,
    intervalSeconds: DEFAULT_INTERVAL_SECONDS,
    maxResults: DEFAULT_MAX_RESULTS,
    newerThanDays: DEFAULT_NEWER_THAN_DAYS,
    unreadOnly: true,
    lastOk: null,
    lastRunAt: "",
    lastUpdatedAt: "",
    lastResultSizeEstimate: null,
    lastMessageCount: null,
    lastError: ""
  };

  function applyPreferencesToStatus() {
    status = {
      ...status,
      enabled: process.env.KURO_MAIL_BRIEFING_AUTO !== "0" && preferences.autoRefresh,
      intervalSeconds: preferences.intervalSeconds,
      maxResults: preferences.maxResults,
      newerThanDays: preferences.newerThanDays,
      unreadOnly: preferences.unreadOnly
    };
  }

  applyPreferencesToStatus();

  function emit() {
    if (typeof onStatusChange === "function") {
      onStatusChange(readStatus());
    }
  }

  function updateStatus(patch) {
    status = {
      ...status,
      ...(patch || {})
    };
    emit();
  }

  function readStatus() {
    return {
      ...status,
      running: Boolean(poller),
      inFlight: Boolean(refreshProcess)
    };
  }

  function handlePollerLine(line) {
    const trimmed = String(line || "").trim();
    if (!trimmed) {
      return;
    }
    try {
      const payload = JSON.parse(trimmed);
      updateStatus({
        lastOk: Boolean(payload.ok),
        lastRunAt: payload.time || new Date().toISOString(),
        lastUpdatedAt: payload.briefing?.updated_at || "",
        lastResultSizeEstimate: payload.resultSizeEstimate ?? null,
        lastMessageCount: payload.messageCount ?? null,
        lastError: payload.ok ? "" : payload.error || payload.error_type || "Mail poll failed."
      });
    } catch (error) {
      if (typeof log === "function") {
        log("mail-briefing-poller-parse-error", error);
      }
    }
  }

  let stopping = false;

  function buildPollerArgs({ once = false } = {}) {
    const args = [
      script,
      "--max-results",
      String(status.maxResults),
      "--newer-than-days",
      String(status.newerThanDays),
      "--pet-control-url",
      petControlUrl
    ];
    if (once) {
      args.push("--once");
    } else {
      args.push("--interval-seconds", String(status.intervalSeconds));
    }
    if (!status.unreadOnly) {
      args.push("--all-recent");
    }
    return args;
  }

  function start() {
    preferences = readPreferencesFile(preferencesPath);
    applyPreferencesToStatus();
    if (!status.enabled || poller) {
      return readStatus();
    }

    stopping = false;
    const child = spawn(
      python,
      buildPollerArgs(),
      {
        cwd: repoRoot,
        windowsHide: true,
        stdio: ["ignore", "pipe", "ignore"],
        env: {
          ...process.env,
          KURO_GMAIL_PREFERENCES_FILE: preferencesPath,
          KURO_GMAIL_RULES_FILE: rulesPath,
          KURO_PET_CONTROL_URL: petControlUrl,
          PYTHONIOENCODING: "utf-8",
          LOGURU_LEVEL: "ERROR"
        }
      }
    );
    poller = child;

    stdoutBuffer = "";
    updateStatus({ running: true, lastError: "" });
    if (typeof log === "function") {
      log("mail-briefing-poller-started", {
        intervalSeconds: status.intervalSeconds,
        maxResults: status.maxResults,
        newerThanDays: status.newerThanDays,
        unreadOnly: status.unreadOnly
      });
    }

    child.stdout.on("data", (chunk) => {
      stdoutBuffer += chunk.toString("utf8");
      const lines = stdoutBuffer.split(/\r?\n/);
      stdoutBuffer = lines.pop() || "";
      for (const line of lines) {
        handlePollerLine(line);
      }
    });

    child.on("exit", (code, signal) => {
      if (poller !== child) {
        return;
      }
      const expectedStop = stopping;
      stopping = false;
      poller = null;
      updateStatus({
        running: false,
        lastOk: expectedStop || code === 0,
        lastError: expectedStop || code === 0
          ? ""
          : `Mail poller exited: code=${code} signal=${signal || ""}`.trim()
      });
      if (typeof log === "function") {
        log("mail-briefing-poller-exit", { code, signal });
      }
    });

    child.on("error", (error) => {
      if (poller !== child) {
        return;
      }
      poller = null;
      updateStatus({
        running: false,
        lastOk: false,
        lastError: error instanceof Error ? error.message : String(error)
      });
      if (typeof log === "function") {
        log("mail-briefing-poller-error", error);
      }
    });

    return readStatus();
  }

  function stop() {
    if (!poller) {
      return readStatus();
    }
    const current = poller;
    poller = null;
    stopping = true;
    current.kill();
    updateStatus({ running: false });
    return readStatus();
  }

  function refreshOnce() {
    if (refreshProcess) {
      return Promise.resolve({
        ok: false,
        error: "Mail briefing refresh is already running.",
        mailBriefing: readStatus()
      });
    }

    preferences = readPreferencesFile(preferencesPath);
    applyPreferencesToStatus();
    updateStatus({ inFlight: true, lastError: "" });

    return new Promise((resolve) => {
      let output = "";
      refreshProcess = spawn(
        python,
        buildPollerArgs({ once: true }),
        {
          cwd: repoRoot,
          windowsHide: true,
          stdio: ["ignore", "pipe", "ignore"],
          env: {
            ...process.env,
            KURO_GMAIL_PREFERENCES_FILE: preferencesPath,
            KURO_GMAIL_RULES_FILE: rulesPath,
            KURO_PET_CONTROL_URL: petControlUrl,
            PYTHONIOENCODING: "utf-8",
            LOGURU_LEVEL: "ERROR"
          }
        }
      );
      emit();

      refreshProcess.stdout.on("data", (chunk) => {
        output += chunk.toString("utf8");
      });

      refreshProcess.on("error", (error) => {
        refreshProcess = null;
        const message = error instanceof Error ? error.message : String(error);
        updateStatus({ inFlight: false, lastOk: false, lastError: message });
        resolve({ ok: false, error: message, mailBriefing: readStatus() });
      });

      refreshProcess.on("exit", (code) => {
        refreshProcess = null;
        const lines = output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        let payload = null;
        for (let index = lines.length - 1; index >= 0; index -= 1) {
          try {
            payload = JSON.parse(lines[index]);
            break;
          } catch (_error) {
            // Keep searching for the last JSON status line.
          }
        }

        if (!payload) {
          const message = code === 0 ? "Mail refresh did not return JSON." : `Mail refresh exited: ${code}`;
          updateStatus({ inFlight: false, lastOk: false, lastError: message });
          resolve({ ok: false, error: message, mailBriefing: readStatus() });
          return;
        }

        updateStatus({
          inFlight: false,
          lastOk: Boolean(payload.ok),
          lastRunAt: payload.time || new Date().toISOString(),
          lastUpdatedAt: payload.briefing?.updated_at || "",
          lastResultSizeEstimate: payload.resultSizeEstimate ?? null,
          lastMessageCount: payload.messageCount ?? null,
          lastError: payload.ok ? "" : payload.error || payload.error_type || "Mail refresh failed."
        });
        resolve({ ok: Boolean(payload.ok), result: payload, mailBriefing: readStatus() });
      });
    });
  }

  function readPreferences() {
    preferences = readPreferencesFile(preferencesPath);
    applyPreferencesToStatus();
    return {
      ok: true,
      preferences: { ...preferences },
      mailBriefing: readStatus()
    };
  }

  function readRules() {
    rulesData = readRulesFile(rulesPath);
    return {
      ok: true,
      rules: rulesData.rules,
      rulesPath,
      mailBriefing: readStatus()
    };
  }

  function readMessage(messageId) {
    const id = String(messageId || "").trim();
    if (!id) {
      return Promise.resolve({ ok: false, error: "Mail message id is required." });
    }
    if (messageReadProcess) {
      return Promise.resolve({ ok: false, error: "Another mail message is already loading." });
    }

    return new Promise((resolve) => {
      let output = "";
      let errorOutput = "";
      messageReadProcess = spawn(
        python,
        [
          messageReaderScript,
          "--message-id",
          id,
          "--max-body-chars",
          "40000"
        ],
        {
          cwd: repoRoot,
          windowsHide: true,
          stdio: ["ignore", "pipe", "pipe"],
          env: {
            ...process.env,
            KURO_GMAIL_PREFERENCES_FILE: preferencesPath,
            KURO_GMAIL_RULES_FILE: rulesPath,
            PYTHONIOENCODING: "utf-8",
            LOGURU_LEVEL: "ERROR"
          }
        }
      );

      messageReadProcess.stdout.on("data", (chunk) => {
        output += chunk.toString("utf8");
      });
      messageReadProcess.stderr.on("data", (chunk) => {
        errorOutput += chunk.toString("utf8");
      });

      messageReadProcess.on("error", (error) => {
        messageReadProcess = null;
        resolve({
          ok: false,
          error: error instanceof Error ? error.message : String(error)
        });
      });

      messageReadProcess.on("exit", (code) => {
        messageReadProcess = null;
        const lines = output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        for (let index = lines.length - 1; index >= 0; index -= 1) {
          try {
            const payload = JSON.parse(lines[index]);
            resolve(payload);
            return;
          } catch (_error) {
            // Keep searching for the last JSON line.
          }
        }
        const stderr = errorOutput.trim();
        resolve({
          ok: false,
          error: stderr
            ? stderr.slice(0, 1200)
            : (code === 0 ? "Mail message reader did not return JSON." : `Mail message reader exited: ${code}`)
        });
      });
    });
  }

  function savePreferences(nextPreferences) {
    const normalized = normalizePreferences({
      ...preferences,
      ...(nextPreferences || {})
    });
    writePreferencesFile(preferencesPath, normalized);
    preferences = normalized;
    applyPreferencesToStatus();
    const wasRunning = Boolean(poller);
    if (wasRunning) {
      stop();
    }
    if (status.enabled) {
      start();
    }
    emit();
    return {
      ok: true,
      preferences: { ...preferences },
      mailBriefing: readStatus()
    };
  }

  function saveRules(nextRules) {
    const normalized = normalizeRulesPayload(nextRules || {});
    writeRulesFile(rulesPath, normalized);
    rulesData = normalized;
    emit();
    return {
      ok: true,
      rules: rulesData.rules,
      rulesPath,
      mailBriefing: readStatus()
    };
  }

  return {
    start,
    stop,
    refreshOnce,
    readMessage,
    readPreferences,
    readRules,
    savePreferences,
    saveRules,
    readStatus
  };
}

module.exports = {
  createMailBriefingService
};
