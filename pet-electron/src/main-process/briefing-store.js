const fs = require("fs");
const path = require("path");

const STORE_VERSION = 1;
const MAX_MEMORY_CANDIDATES = 100;
const MEMORY_CANDIDATE_STATUSES = new Set(["pending", "approved", "rejected", "saved"]);

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function text(value, fallback = "") {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function boundedText(value, maxLength, fallback = "") {
  return text(value, fallback).slice(0, maxLength);
}

function toBool(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function toCount(value, fallback = 0) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) && numberValue >= 0
    ? Math.round(numberValue)
    : fallback;
}

function localDateKey(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function newId(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function defaultSections() {
  return [
    {
      key: "overview",
      label: "\u4eca\u65e5\u5927\u7db1",
      icon: "T",
      count: 3,
      subtitle: "\u4eca\u65e5\u7c21\u5831\u5feb\u7167\u8207\u512a\u5148\u9805",
      accent: "",
      modules: [
        {
          id: "priority",
          title: "\u512a\u5148\u8655\u7406",
          tag: "Snapshot",
          value: "0",
          unit: "items",
          wide: true,
          items: [
            {
              text: "\u5de5\u5177\u8cc7\u6599\u5c1a\u672a\u63a5\u5165",
              meta: "pending"
            }
          ]
        },
        {
          id: "memory-candidates",
          title: "\u8a18\u61b6\u5019\u9078",
          tag: "Review",
          value: "0",
          unit: "pending",
          items: [
            {
              text: "\u53ea\u6709\u901a\u904e\u6279\u51c6\u7684\u5019\u9078\u624d\u9032\u9577\u671f\u8a18\u61b6",
              meta: "safe"
            }
          ]
        },
        {
          id: "tools",
          title: "\u5de5\u5177\u72c0\u614b",
          tag: "Sources",
          value: "0",
          unit: "online",
          items: [
            {
              text: "Mail / News / Stocks / Messages adapters",
              meta: "not connected"
            }
          ]
        }
      ]
    },
    {
      key: "tasks",
      label: "\u5f85\u8655\u7406",
      icon: "A",
      count: 0,
      subtitle: "\u9700\u8981\u4eba\u5de5\u5224\u65b7\u6216\u56de\u8986\u7684\u9805\u76ee",
      accent: "accent-yellow",
      modules: []
    },
    {
      key: "mail",
      label: "Mail",
      icon: "M",
      count: 0,
      subtitle: "\u91cd\u8981\u4fe1\u4ef6\u6458\u8981",
      accent: "accent-cyan",
      modules: []
    },
    {
      key: "messages",
      label: "Messages",
      icon: "D",
      count: 0,
      subtitle: "\u8a0a\u606f\u8207\u793e\u7fa4\u6458\u8981",
      accent: "accent-green",
      modules: []
    },
    {
      key: "stocks",
      label: "Stocks",
      icon: "S",
      count: 0,
      subtitle: "\u5e02\u5834\u8207 watchlist \u6a21\u7d44",
      accent: "accent-red",
      modules: []
    },
    {
      key: "news",
      label: "News",
      icon: "N",
      count: 0,
      subtitle: "\u65b0\u805e\u8207\u4e16\u754c\u8a0a\u865f",
      accent: "",
      modules: []
    },
    {
      key: "calendar",
      label: "Calendar",
      icon: "C",
      count: 0,
      subtitle: "\u884c\u7a0b\u8207\u6642\u9593\u7bc0\u9ede",
      accent: "accent-yellow",
      modules: []
    },
    {
      key: "notes",
      label: "Notes",
      icon: "R",
      count: 0,
      subtitle: "\u5099\u5fd8\u8207\u7814\u7a76\u7b46\u8a18",
      accent: "accent-green",
      modules: []
    }
  ];
}

function normalizeItem(candidate) {
  if (Array.isArray(candidate)) {
    return {
      text: boundedText(candidate[0], 240),
      meta: boundedText(candidate[1], 64)
    };
  }

  if (isObject(candidate)) {
    return {
      text: boundedText(candidate.text ?? candidate.title ?? candidate.label, 240),
      meta: boundedText(candidate.meta ?? candidate.status ?? candidate.time ?? candidate.source, 64),
      priority: boundedText(candidate.priority, 32),
      source: boundedText(candidate.source, 64)
    };
  }

  return {
    text: boundedText(candidate, 240),
    meta: ""
  };
}

function normalizeModule(candidate, index = 0) {
  const module = isObject(candidate) ? candidate : {};
  const items = Array.isArray(module.items)
    ? module.items.map(normalizeItem).filter((item) => item.text)
    : [];

  return {
    id: boundedText(module.id, 64, `module-${index}`),
    title: boundedText(module.title, 80, "Untitled"),
    tag: boundedText(module.tag, 32),
    value: boundedText(module.value, 32),
    unit: boundedText(module.unit, 32),
    wide: toBool(module.wide, false),
    items
  };
}

function normalizeSection(candidate, index = 0) {
  const section = isObject(candidate) ? candidate : {};
  const key = boundedText(section.key ?? section.id, 48, `section-${index}`);
  const modules = Array.isArray(section.modules)
    ? section.modules.map(normalizeModule).filter((module) => module.title)
    : [];

  return {
    key,
    label: boundedText(section.label ?? section.title, 64, key),
    icon: boundedText(section.icon, 4, key.slice(0, 1).toUpperCase() || "D"),
    count: toCount(section.count, modules.reduce((total, module) => total + module.items.length, 0)),
    subtitle: boundedText(section.subtitle, 160),
    accent: boundedText(section.accent, 32),
    modules
  };
}

function normalizeSourceStatus(candidate) {
  if (!isObject(candidate)) {
    return null;
  }
  const id = boundedText(candidate.id ?? candidate.source, 64);
  if (!id) {
    return null;
  }
  return {
    id,
    label: boundedText(candidate.label, 80, id),
    status: boundedText(candidate.status, 32, "unknown"),
    updatedAt: boundedText(candidate.updatedAt, 40),
    message: boundedText(candidate.message, 180)
  };
}

function normalizeSnapshot(candidate, fallbackSnapshot) {
  const now = new Date();
  const source = isObject(candidate) ? candidate : {};
  const fallback = isObject(fallbackSnapshot) ? fallbackSnapshot : {};
  const sectionsSource = Array.isArray(source.sections)
    ? source.sections
    : Array.isArray(fallback.sections)
      ? fallback.sections
      : defaultSections();
  const sections = sectionsSource.map(normalizeSection).filter((section) => section.key);
  const sourceStatus = Array.isArray(source.sourceStatus)
    ? source.sourceStatus.map(normalizeSourceStatus).filter(Boolean)
    : Array.isArray(fallback.sourceStatus)
      ? fallback.sourceStatus.map(normalizeSourceStatus).filter(Boolean)
      : [];

  return {
    schemaVersion: STORE_VERSION,
    date: boundedText(source.date, 16, fallback.date || localDateKey(now)),
    title: boundedText(source.title, 80, fallback.title || "\u4eca\u65e5\u7c21\u5831"),
    updatedAt: boundedText(source.updatedAt, 40, now.toISOString()),
    sections,
    sourceStatus
  };
}

function normalizeMemoryCandidate(candidate) {
  if (!isObject(candidate)) {
    return null;
  }

  const content = boundedText(candidate.content ?? candidate.text, 1000);
  if (!content) {
    return null;
  }

  const now = new Date().toISOString();
  const status = MEMORY_CANDIDATE_STATUSES.has(candidate.status)
    ? candidate.status
    : "pending";

  return {
    id: boundedText(candidate.id, 80, newId("mem")),
    status,
    memoryType: boundedText(candidate.memoryType ?? candidate.memory_type ?? candidate.type, 32, "preference"),
    content,
    reason: boundedText(candidate.reason, 240),
    source: boundedText(candidate.source, 80, "briefing"),
    createdAt: boundedText(candidate.createdAt, 40, now),
    updatedAt: boundedText(candidate.updatedAt, 40, now)
  };
}

function createDefaultData() {
  const now = new Date().toISOString();
  return {
    schemaVersion: STORE_VERSION,
    updatedAt: now,
    snapshot: normalizeSnapshot({
      updatedAt: now,
      sections: defaultSections()
    }),
    memoryCandidates: []
  };
}

function normalizeStoreData(candidate) {
  const fallback = createDefaultData();
  if (!isObject(candidate)) {
    return fallback;
  }

  const memoryCandidates = Array.isArray(candidate.memoryCandidates)
    ? candidate.memoryCandidates.map(normalizeMemoryCandidate).filter(Boolean)
    : [];

  return {
    schemaVersion: STORE_VERSION,
    updatedAt: boundedText(candidate.updatedAt, 40, fallback.updatedAt),
    snapshot: normalizeSnapshot(candidate.snapshot, fallback.snapshot),
    memoryCandidates: memoryCandidates.slice(0, MAX_MEMORY_CANDIDATES)
  };
}

function readStoreFile(storePath, log) {
  try {
    if (!storePath || !fs.existsSync(storePath)) {
      return createDefaultData();
    }
    const raw = fs.readFileSync(storePath, "utf8");
    return normalizeStoreData(JSON.parse(raw));
  } catch (error) {
    if (typeof log === "function") {
      log("briefing-store-load-failed", error);
    }
    return createDefaultData();
  }
}

function writeStoreFile(storePath, data, log) {
  if (!storePath) {
    return;
  }
  try {
    fs.mkdirSync(path.dirname(storePath), { recursive: true });
    fs.writeFileSync(storePath, JSON.stringify(normalizeStoreData(data), null, 2), "utf8");
  } catch (error) {
    if (typeof log === "function") {
      log("briefing-store-save-failed", error);
    }
  }
}

function createBriefingStore({ storePath, log } = {}) {
  let data = readStoreFile(storePath, log);

  function persist() {
    data.updatedAt = new Date().toISOString();
    writeStoreFile(storePath, data, log);
  }

  function getData() {
    return clone(data);
  }

  function replaceSnapshot(snapshot) {
    data.snapshot = normalizeSnapshot(snapshot, data.snapshot);
    persist();
    return getData();
  }

  function addMemoryCandidate(candidate) {
    const normalized = normalizeMemoryCandidate(candidate);
    if (!normalized) {
      return { ok: false, error: "Memory candidate content is required.", data: getData() };
    }

    const duplicate = data.memoryCandidates.find((item) =>
      item.content === normalized.content && item.memoryType === normalized.memoryType
    );
    if (duplicate) {
      duplicate.updatedAt = new Date().toISOString();
      persist();
      return { ok: true, candidate: clone(duplicate), data: getData(), duplicate: true };
    }

    data.memoryCandidates.unshift(normalized);
    data.memoryCandidates = data.memoryCandidates.slice(0, MAX_MEMORY_CANDIDATES);
    persist();
    return { ok: true, candidate: clone(normalized), data: getData(), duplicate: false };
  }

  function setMemoryCandidateStatus(candidateId, status) {
    const id = text(candidateId);
    if (!id) {
      return { ok: false, error: "Memory candidate id is required.", data: getData() };
    }
    if (!MEMORY_CANDIDATE_STATUSES.has(status)) {
      return { ok: false, error: `Unsupported memory candidate status: ${status}`, data: getData() };
    }

    const candidate = data.memoryCandidates.find((item) => item.id === id);
    if (!candidate) {
      return { ok: false, error: `Memory candidate not found: ${id}`, data: getData() };
    }

    candidate.status = status;
    candidate.updatedAt = new Date().toISOString();
    persist();
    return { ok: true, candidate: clone(candidate), data: getData() };
  }

  return {
    getData,
    replaceSnapshot,
    addMemoryCandidate,
    setMemoryCandidateStatus
  };
}

module.exports = {
  STORE_VERSION,
  createBriefingStore,
  createDefaultData,
  normalizeSnapshot,
  normalizeStoreData
};
