const fs = require("fs");

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
  return Number.isFinite(numberValue) && numberValue >= 0
    ? Math.round(numberValue)
    : fallback;
}

function readJsonFile(filePath, log) {
  if (!filePath || !fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    if (typeof log === "function") {
      log("study-snapshot-read-failed", error);
    }
    return null;
  }
}

function normalizeStudyWord(candidate) {
  if (!isObject(candidate)) {
    return null;
  }
  const wordId = boundedText(candidate.word_id || candidate.wordId || candidate.id, 120);
  if (!wordId) {
    return null;
  }
  return {
    word_id: wordId,
    level: boundedText(candidate.level, 24),
    kanji: boundedText(candidate.kanji, 80),
    reading: boundedText(candidate.reading, 80),
    meaning: boundedText(candidate.meaning, 160),
    pos: boundedText(candidate.pos, 40),
    status: boundedText(candidate.status, 32, "new"),
    seen_count: toCount(candidate.seen_count ?? candidate.seenCount, 0),
    correct_count: toCount(candidate.correct_count ?? candidate.correctCount, 0),
    wrong_count: toCount(candidate.wrong_count ?? candidate.wrongCount, 0),
    next_review: boundedText(candidate.next_review ?? candidate.nextReview, 40)
  };
}

function normalizeWordList(candidate, maxItems = 80) {
  return Array.isArray(candidate)
    ? candidate.map(normalizeStudyWord).filter(Boolean).slice(0, maxItems)
    : [];
}

function normalizeTodayItem(candidate, index = 0) {
  if (!isObject(candidate)) {
    return null;
  }
  const title = boundedText(candidate.title || candidate.text || candidate.label, 180);
  if (!title) {
    return null;
  }
  return {
    id: boundedText(candidate.id, 120, `study:item:${index}`),
    source: "study",
    kind: boundedText(candidate.kind, 32, "vocab"),
    level: boundedText(candidate.level || candidate.priority, 24, "must"),
    title,
    text: title,
    meta: boundedText(candidate.meta, 80),
    summary: boundedText(candidate.summary, 240)
  };
}

function normalizeStudySnapshot(candidate, fallbackStudy) {
  const source = isObject(candidate) ? candidate : {};
  const fallback = isObject(fallbackStudy) ? fallbackStudy : {};
  if (!Object.keys(source).length && !Object.keys(fallback).length) {
    return null;
  }

  const vocab = isObject(source.vocab)
    ? source.vocab
    : isObject(fallback.vocab)
      ? fallback.vocab
      : {};
  const stats = isObject(vocab.stats) ? vocab.stats : {};
  const statuses = isObject(stats.statuses) ? stats.statuses : {};
  const levels = isObject(stats.levels) ? stats.levels : {};
  const today = isObject(vocab.today) ? vocab.today : {};
  const todaySource = isObject(source.today)
    ? source.today
    : isObject(fallback.today)
      ? fallback.today
      : {};

  return {
    schemaVersion: 1,
    updatedAt: boundedText(source.updatedAt, 40, fallback.updatedAt || ""),
    source: "study",
    studyType: boundedText(source.studyType, 32, fallback.studyType || "japanese"),
    vocab: {
      stats: {
        total: toCount(stats.total, 0),
        due: toCount(stats.due, 0),
        withMistakes: toCount(stats.withMistakes, 0),
        statuses: Object.fromEntries(
          Object.entries(statuses).map(([key, value]) => [boundedText(key, 32), toCount(value, 0)])
        ),
        levels: Object.fromEntries(
          Object.entries(levels).map(([key, value]) => [boundedText(key, 32), toCount(value, 0)])
        )
      },
      today: {
        review: normalizeWordList(today.review),
        focus: normalizeWordList(today.focus),
        new: normalizeWordList(today.new)
      }
    },
    today: {
      items: Array.isArray(todaySource.items)
        ? todaySource.items.map(normalizeTodayItem).filter(Boolean)
        : []
    }
  };
}

function wordItem(word) {
  return {
    text: boundedText(`${word.kanji || word.reading} - ${word.meaning}`, 240),
    meta: boundedText(`${word.level || "Study"} / ${word.status || "new"}`, 64),
    source: "study",
    priority: word.wrong_count > 0 ? "focus" : "must"
  };
}

function countTodayWords(study) {
  const today = study?.vocab?.today || {};
  return {
    review: Array.isArray(today.review) ? today.review.length : 0,
    focus: Array.isArray(today.focus) ? today.focus.length : 0,
    new: Array.isArray(today.new) ? today.new.length : 0
  };
}

function buildStudySection(study) {
  const stats = study?.vocab?.stats || {};
  const today = study?.vocab?.today || {};
  const counts = countTodayWords(study);
  const todayTotal = counts.review + counts.focus + counts.new;
  const statusCounts = stats.statuses || {};
  const focusWords = [
    ...(Array.isArray(today.focus) ? today.focus : []),
    ...(Array.isArray(today.review) ? today.review : []),
    ...(Array.isArray(today.new) ? today.new : [])
  ].slice(0, 8);

  const todayItems = [];
  if (counts.review) {
    todayItems.push({ text: `\u8907\u7fd2\u55ae\u5b57 ${counts.review} \u500b`, meta: "\u5230\u671f", source: "study", priority: "must" });
  }
  if (counts.focus) {
    todayItems.push({ text: `\u5f31\u9ede\u55ae\u5b57 ${counts.focus} \u500b`, meta: "\u932f\u984c", source: "study", priority: "focus" });
  }
  if (counts.new) {
    todayItems.push({ text: `\u65b0\u55ae\u5b57 ${counts.new} \u500b`, meta: "\u4eca\u65e5", source: "study", priority: "must" });
  }
  if (!todayItems.length) {
    todayItems.push({ text: "\u4eca\u5929\u9084\u6c92\u6709\u5b78\u7fd2\u4efb\u52d9\u3002", meta: "clear", source: "study", priority: "normal" });
  }

  return {
    key: "study",
    label: "Study",
    icon: "J",
    count: todayTotal,
    subtitle: "\u65e5\u6587\u55ae\u5b57\u8207\u5b78\u7fd2\u9032\u5ea6",
    accent: "accent-green",
    modules: [
      {
        id: "study-today",
        title: "\u4eca\u65e5\u5b78\u7fd2",
        tag: "Japanese",
        value: String(todayTotal),
        unit: "words",
        wide: true,
        items: todayItems
      },
      {
        id: "study-vocab-status",
        title: "\u55ae\u5b57\u72c0\u614b",
        tag: "Vocab",
        value: String(stats.total || 0),
        unit: "words",
        items: [
          { text: `New: ${toCount(statusCounts.new, 0)}`, meta: "\u672a\u958b\u59cb", source: "study" },
          { text: `Learning: ${toCount(statusCounts.learning, 0)}`, meta: "\u5b78\u7fd2\u4e2d", source: "study" },
          { text: `Review: ${toCount(statusCounts.review, 0)}`, meta: "\u5fa9\u7fd2", source: "study" },
          { text: `\u5230\u671f\u8907\u7fd2: ${toCount(stats.due, 0)}`, meta: "\u4eca\u65e5", source: "study" },
          { text: `\u932f\u984c\u8ffd\u8e64: ${toCount(stats.withMistakes, 0)}`, meta: "\u5f31\u9ede", source: "study" }
        ]
      },
      {
        id: "study-focus-words",
        title: "\u4eca\u65e5\u55ae\u5b57",
        tag: "Queue",
        value: String(focusWords.length),
        unit: "shown",
        wide: true,
        items: focusWords.length
          ? focusWords.map(wordItem)
          : [{ text: "\u6c92\u6709\u5f85\u986f\u793a\u55ae\u5b57\u3002", meta: "clear", source: "study" }]
      }
    ]
  };
}

function mergeStudySection(sections, study) {
  if (!study) {
    return Array.isArray(sections) ? sections : [];
  }
  const sourceSections = Array.isArray(sections) ? sections : [];
  const nextSections = sourceSections.filter(section => section && section.key !== "study");
  const mailIndex = nextSections.findIndex(section => section.key === "mail");
  const insertIndex = mailIndex >= 0 ? mailIndex + 1 : Math.min(3, nextSections.length);
  nextSections.splice(insertIndex, 0, buildStudySection(study));
  return nextSections;
}

function mergeTodayItems(today, study) {
  const current = isObject(today) ? today : {};
  const existingItems = Array.isArray(current.items) ? current.items : [];
  const studyItems = Array.isArray(study?.today?.items) ? study.today.items : [];
  return {
    ...current,
    items: [
      ...existingItems,
      ...studyItems
    ]
  };
}

function mergeSourceStatus(sourceStatus, study) {
  const statuses = Array.isArray(sourceStatus) ? sourceStatus.filter(item => item && item.id !== "study") : [];
  if (!study) {
    return statuses;
  }
  const counts = countTodayWords(study);
  const todayTotal = counts.review + counts.focus + counts.new;
  statuses.push({
    id: "study",
    label: "Study",
    status: "connected",
    updatedAt: study.updatedAt || "",
    message: `\u55ae\u5b57 ${study.vocab?.stats?.total || 0} \u7b46\uff0c\u4eca\u65e5 ${todayTotal} \u500b\u9805\u76ee\u3002`
  });
  return statuses;
}

function mergeStudyIntoSnapshot(snapshot, studyCandidate) {
  const source = isObject(snapshot) ? snapshot : {};
  const study = normalizeStudySnapshot(studyCandidate, source.study);
  if (!study) {
    return source;
  }
  return {
    ...source,
    sections: mergeStudySection(source.sections, study),
    sourceStatus: mergeSourceStatus(source.sourceStatus, study),
    today: mergeTodayItems(source.today, study),
    study
  };
}

function readStudySnapshotFile(filePath, log) {
  return normalizeStudySnapshot(readJsonFile(filePath, log), null);
}

module.exports = {
  buildStudySection,
  mergeStudyIntoSnapshot,
  normalizeStudySnapshot,
  readStudySnapshotFile
};
