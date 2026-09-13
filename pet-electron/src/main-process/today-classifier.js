const MAX_TODAY_ITEMS = 120;
const MAX_LEVEL_ITEMS = 40;

const LEVELS = ["urgent", "must", "focus", "watch", "normal", "muted"];
const LEVEL_RANK = new Map(LEVELS.map((level, index) => [level, index]));
const LEVEL_LABELS = {
  urgent: "\u7acb\u5373\u8655\u7406",
  must: "\u4eca\u65e5\u5fc5\u505a",
  focus: "\u91cd\u9ede\u95dc\u6ce8",
  watch: "\u7a0d\u5f8c\u67e5\u770b",
  normal: "\u666e\u901a\u8a18\u9304",
  muted: "\u964d\u566a"
};

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

function toCount(value, fallback = 0) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? Math.round(numberValue) : fallback;
}

function normalizeLevel(value, fallback = "normal") {
  const normalized = text(value).toLowerCase().replace(/[^a-z_ -]/g, "").replace(/[ _-]+/g, "-");
  if (normalized === "critical" || normalized === "urgent") {
    return "urgent";
  }
  if (normalized === "required" || normalized === "must" || normalized === "must-do") {
    return "must";
  }
  if (normalized === "high" || normalized === "focus" || normalized === "important") {
    return "focus";
  }
  if (normalized === "medium" || normalized === "watch" || normalized === "later") {
    return "watch";
  }
  if (normalized === "muted" || normalized === "ignore" || normalized === "noise") {
    return "muted";
  }
  return LEVEL_RANK.has(normalized) ? normalized : fallback;
}

function compactDate(value) {
  const raw = text(value);
  if (!raw) {
    return "";
  }
  const date = new Date(raw);
  if (!Number.isNaN(date.getTime())) {
    return date.toISOString().slice(0, 10);
  }
  return raw.slice(0, 16);
}

function sourceMeta(source) {
  return {
    mail: "Mail",
    calendar: "Calendar",
    study: "Study",
    stocks: "Stocks",
    notes: "Notes",
    finance: "Finance"
  }[source] || source || "today";
}

function mailSender(message) {
  return boundedText(message.from || message.senderEmail || message.senderDomain || "Mail", 80);
}

function mailSubject(message) {
  return boundedText(message.subject || "(no subject)", 180);
}

function classifyMailLevel(message) {
  if (!isObject(message)) {
    return "";
  }

  const priorityLevel = normalizeLevel(message.priorityLevel, "normal");
  const score = toCount(message.priorityScore, 0);
  const required = Boolean(message.requiredEvent);
  const muted = Boolean(message.muted);

  if (muted && !required) {
    return "muted";
  }
  if (required && (priorityLevel === "urgent" || score >= 120)) {
    return "urgent";
  }
  if (required) {
    return "must";
  }
  if (priorityLevel === "urgent" || priorityLevel === "focus" || score >= 70 || message.attention) {
    return "focus";
  }
  if (priorityLevel === "watch" || message.gmailImportant || score >= 35) {
    return "watch";
  }
  return "normal";
}

function eventName(message) {
  const event = isObject(message.event)
    ? message.event
    : Array.isArray(message.events) && isObject(message.events[0])
      ? message.events[0]
      : null;
  return event ? boundedText(event.name || event.id, 40) : "";
}

function mailToTodayItem(message) {
  const level = classifyMailLevel(message);
  if (!level) {
    return null;
  }

  const metaParts = [LEVEL_LABELS[level]];
  const event = eventName(message);
  if (event) {
    metaParts.push(event);
  } else if (message.unread) {
    metaParts.push("\u672a\u8b80");
  }
  const date = compactDate(message.date);
  if (date) {
    metaParts.push(date);
  }

  return {
    id: boundedText(`mail:${message.id || message.threadId || mailSubject(message)}`, 120),
    source: "mail",
    kind: "mail",
    level,
    priority: boundedText(message.priorityLevel || level, 24),
    score: toCount(message.priorityScore, 0),
    date: boundedText(message.date, 60),
    text: boundedText(`${mailSubject(message)} - ${mailSender(message)}`, 240),
    meta: boundedText(metaParts.join(" / "), 80),
    refId: boundedText(message.id, 80),
    evidence: boundedText(message.snippet, 240)
  };
}

function normalizeExternalItem(candidate, index) {
  if (!isObject(candidate)) {
    return null;
  }

  const status = text(candidate.status).toLowerCase();
  if (status === "done" || status === "completed" || status === "ignored") {
    return null;
  }

  const source = boundedText(candidate.source || candidate.kind || "today", 32);
  const level = normalizeLevel(candidate.level || candidate.priority, "normal");
  const title = boundedText(candidate.text || candidate.title || candidate.label, 240);
  if (!title) {
    return null;
  }

  return {
    id: boundedText(candidate.id || `${source}:${index}:${title}`, 120),
    source,
    kind: boundedText(candidate.kind || source, 32),
    level,
    priority: boundedText(candidate.priority || level, 24),
    score: toCount(candidate.score ?? candidate.priorityScore, 0),
    date: boundedText(candidate.date || candidate.dueAt || candidate.remindAt, 60),
    text: title,
    meta: boundedText(candidate.meta || candidate.time || candidate.status || LEVEL_LABELS[level], 80),
    refId: boundedText(candidate.refId || candidate.messageId || candidate.eventId, 80),
    evidence: boundedText(candidate.evidence || candidate.summary || candidate.description, 240)
  };
}

function collectExternalItems(todaySource) {
  if (!isObject(todaySource)) {
    return [];
  }

  const items = [];
  if (Array.isArray(todaySource.items)) {
    for (const item of todaySource.items) {
      items.push(item);
    }
  }
  if (isObject(todaySource.levels)) {
    for (const level of LEVELS) {
      const levelItems = todaySource.levels[level];
      if (Array.isArray(levelItems)) {
        for (const item of levelItems) {
          items.push({ ...item, level: item.level || level });
        }
      }
    }
  }

  return items.map(normalizeExternalItem).filter(Boolean);
}

function sortTodayItems(left, right) {
  const leftRank = LEVEL_RANK.get(left.level) ?? 99;
  const rightRank = LEVEL_RANK.get(right.level) ?? 99;
  if (leftRank !== rightRank) {
    return leftRank - rightRank;
  }
  if (left.score !== right.score) {
    return right.score - left.score;
  }
  return String(right.date || "").localeCompare(String(left.date || ""));
}

function uniqueItems(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const key = item.id || `${item.source}:${item.text}:${item.meta}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }
  return result;
}

function bucketItems(items) {
  const levels = Object.fromEntries(LEVELS.map((level) => [level, []]));
  for (const item of items) {
    const level = normalizeLevel(item.level, "normal");
    levels[level].push({ ...item, level });
  }
  for (const level of LEVELS) {
    levels[level] = levels[level].sort(sortTodayItems).slice(0, MAX_LEVEL_ITEMS);
  }
  return levels;
}

function buildTodaySnapshot({ mail, sourceToday, fallbackToday, updatedAt } = {}) {
  const mailMessages = isObject(mail) && Array.isArray(mail.messages) ? mail.messages : [];
  const items = uniqueItems([
    ...collectExternalItems(sourceToday),
    ...collectExternalItems(fallbackToday),
    ...mailMessages.map(mailToTodayItem).filter(Boolean)
  ]).filter((item) => item.source !== "calendar").sort(sortTodayItems).slice(0, MAX_TODAY_ITEMS);

  const levels = bucketItems(items);
  const counts = Object.fromEntries(LEVELS.map((level) => [level, levels[level].length]));
  counts.total = items.length;
  counts.actionable = counts.urgent + counts.must;
  counts.attention = counts.urgent + counts.must + counts.focus + counts.watch;

  return {
    schemaVersion: 1,
    updatedAt: boundedText(updatedAt, 40, new Date().toISOString()),
    levels,
    counts,
    items
  };
}

function asModuleItem(item) {
  return {
    text: boundedText(item.text, 240),
    meta: boundedText(item.meta || `${sourceMeta(item.source)} / ${LEVEL_LABELS[item.level]}`, 64),
    priority: boundedText(item.level, 32),
    source: boundedText(item.source, 64)
  };
}

function pickLevelItems(today, levels, limit) {
  const picked = [];
  for (const level of levels) {
    const levelItems = today.levels?.[level] || [];
    picked.push(...levelItems);
  }
  return picked.sort(sortTodayItems).slice(0, limit).map(asModuleItem);
}

function fallbackItem(textValue, meta = "clear") {
  return {
    text: textValue,
    meta,
    priority: "normal",
    source: "today"
  };
}

function mergeTodaySections(sections, today) {
  const sourceSections = Array.isArray(sections) ? sections : [];
  const sectionByKey = new Map(sourceSections.map((section) => [section.key, section]));
  const overview = sectionByKey.get("overview") || {};
  const tasks = sectionByKey.get("tasks") || {};
  const statusModules = Array.isArray(overview.modules)
    ? overview.modules.filter((module) =>
      module.id === "tools" || module.id === "gmail-status" || String(module.id || "").includes("status")
    ).slice(0, 1)
    : [];

  const immediateCount = today.counts.actionable || 0;
  const focusCount = (today.counts.focus || 0) + (today.counts.watch || 0);
  const immediateItems = pickLevelItems(today, ["urgent", "must"], 4);
  const focusItems = pickLevelItems(today, ["focus", "watch"], 4);

  sectionByKey.set("overview", {
    ...overview,
    key: "overview",
    label: overview.label || "\u4eca\u65e5\u5927\u7db1",
    icon: overview.icon || "T",
    count: today.counts.attention || 0,
    subtitle: "\u4eca\u65e5\u4e8b\u9805\u5206\u7d1a\u8207\u512a\u5148\u5ea6",
    modules: [
      {
        id: "today-immediate",
        title: "\u7acb\u5373\u8655\u7406",
        tag: "Today",
        value: String(immediateCount),
        unit: "items",
        wide: true,
        items: immediateItems.length
          ? immediateItems
          : [fallbackItem("\u76ee\u524d\u6c92\u6709\u9700\u8981\u7acb\u5373\u8655\u7406\u7684\u4e8b\u9805\u3002")]
      },
      {
        id: "today-focus",
        title: "\u91cd\u9ede\u95dc\u6ce8",
        tag: "Signals",
        value: String(focusCount),
        unit: "items",
        items: focusItems.length
          ? focusItems
          : [fallbackItem("\u76ee\u524d\u6c92\u6709\u9700\u8981\u95dc\u6ce8\u7684\u4fe1\u865f\u3002")]
      },
      ...statusModules
    ]
  });

  sectionByKey.set("tasks", {
    ...tasks,
    key: "tasks",
    label: tasks.label || "\u5f85\u8655\u7406",
    icon: tasks.icon || "A",
    count: immediateCount,
    subtitle: "\u4eca\u65e5\u5fc5\u505a\u8207\u7acb\u5373\u8655\u7406\u4e8b\u9805",
    modules: [
      {
        id: "today-required",
        title: "\u5fc5\u505a\u4e8b\u9805",
        tag: "Today",
        value: String(immediateCount),
        unit: "items",
        wide: true,
        items: immediateItems.length
          ? immediateItems.slice(0, 8)
          : [fallbackItem("\u76ee\u524d\u6c92\u6709\u5fc5\u505a\u4e8b\u9805\u3002")]
      }
    ]
  });

  const merged = sourceSections.map((section) => sectionByKey.get(section.key) || section);
  if (!merged.some((section) => section.key === "overview")) {
    merged.unshift(sectionByKey.get("overview"));
  }
  if (!merged.some((section) => section.key === "tasks")) {
    const overviewIndex = merged.findIndex((section) => section.key === "overview");
    merged.splice(overviewIndex >= 0 ? overviewIndex + 1 : 0, 0, sectionByKey.get("tasks"));
  }
  return merged;
}

module.exports = {
  buildTodaySnapshot,
  mergeTodaySections
};
