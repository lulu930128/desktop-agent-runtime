const path = require("path");

const MAX_READER_ATTACHMENTS = 6;
const MAX_READER_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_READER_AUDIO_BYTES = 12 * 1024 * 1024;
const MAX_READER_TEXT_BYTES = 4 * 1024 * 1024;
const MAX_READER_ARCHIVE_BYTES = 24 * 1024 * 1024;
const MAX_READER_BINARY_BYTES = 16 * 1024 * 1024;

const READER_TEXT_EXTENSIONS = new Set([
  ".txt",
  ".md",
  ".json",
  ".jsonl",
  ".yaml",
  ".yml",
  ".toml",
  ".ini",
  ".cfg",
  ".csv",
  ".tsv",
  ".log",
  ".env",
  ".gitignore",
  ".xml"
]);

const READER_CODE_EXTENSIONS = new Set([
  ".py",
  ".js",
  ".mjs",
  ".cjs",
  ".ts",
  ".tsx",
  ".jsx",
  ".html",
  ".css",
  ".scss",
  ".c",
  ".cc",
  ".cpp",
  ".h",
  ".hpp",
  ".cs",
  ".java",
  ".go",
  ".rs",
  ".php",
  ".rb",
  ".lua",
  ".sql",
  ".swift",
  ".kt",
  ".kts",
  ".dart",
  ".vue",
  ".svelte",
  ".r",
  ".pl",
  ".bat",
  ".cmd",
  ".ps1",
  ".sh"
]);

const READER_ARCHIVE_EXTENSIONS = new Set([".zip", ".tar", ".tgz", ".tar.gz", ".gz"]);
const READER_BINARY_EXTENSIONS = new Set([".exe", ".dll", ".bin", ".dat"]);
const READER_ARCHIVE_MIME_TYPES = new Set([
  "application/zip",
  "application/x-zip-compressed",
  "application/x-tar",
  "application/gzip",
  "application/x-gzip"
]);
const READER_BINARY_MIME_TYPES = new Set([
  "application/octet-stream",
  "application/vnd.microsoft.portable-executable",
  "application/x-msdownload",
  "application/x-dosexec"
]);

function estimateDataUrlBytes(dataUrl) {
  const raw = String(dataUrl || "");
  const commaIndex = raw.indexOf(",");
  const payload = commaIndex >= 0 ? raw.slice(commaIndex + 1) : raw;
  return Math.floor((payload.length * 3) / 4);
}

function getReaderFileExtension(name) {
  const lowerName = String(name || "").toLowerCase();
  if (lowerName.endsWith(".tar.gz")) {
    return ".tar.gz";
  }
  const dotIndex = lowerName.lastIndexOf(".");
  return dotIndex >= 0 ? lowerName.slice(dotIndex) : "";
}

function guessReaderMimeType(name, kind, fallback) {
  const mimeType = String(fallback || "").trim().toLowerCase();
  if (mimeType) {
    return mimeType;
  }

  const mimeByExtension = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml",
    ".toml": "application/toml",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".log": "text/plain",
    ".env": "text/plain",
    ".gitignore": "text/plain",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".cjs": "text/javascript",
    ".ts": "text/typescript",
    ".tsx": "text/typescript",
    ".jsx": "text/javascript",
    ".html": "text/html",
    ".css": "text/css",
    ".scss": "text/x-scss",
    ".c": "text/plain",
    ".cc": "text/plain",
    ".cpp": "text/plain",
    ".h": "text/plain",
    ".hpp": "text/plain",
    ".cs": "text/plain",
    ".java": "text/x-java-source",
    ".go": "text/plain",
    ".rs": "text/plain",
    ".php": "text/x-php",
    ".rb": "text/plain",
    ".lua": "text/plain",
    ".sql": "application/sql",
    ".swift": "text/plain",
    ".kt": "text/plain",
    ".kts": "text/plain",
    ".dart": "text/plain",
    ".vue": "text/plain",
    ".svelte": "text/plain",
    ".r": "text/plain",
    ".pl": "text/plain",
    ".xml": "application/xml",
    ".bat": "text/plain",
    ".cmd": "text/plain",
    ".ps1": "text/plain",
    ".sh": "text/x-shellscript",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".tgz": "application/gzip",
    ".tar.gz": "application/gzip",
    ".gz": "application/gzip",
    ".exe": "application/vnd.microsoft.portable-executable",
    ".dll": "application/vnd.microsoft.portable-executable",
    ".bin": "application/octet-stream",
    ".dat": "application/octet-stream"
  };
  return mimeByExtension[getReaderFileExtension(name)] || (kind === "binary" ? "application/octet-stream" : "application/octet-stream");
}

function classifyReaderAttachment(name, mimeType, requestedKind) {
  const normalizedMime = String(mimeType || "").trim().toLowerCase();
  const extension = getReaderFileExtension(name);
  if (normalizedMime.startsWith("image/")) {
    return "image";
  }
  if (normalizedMime.startsWith("audio/")) {
    return "audio";
  }
  if (READER_CODE_EXTENSIONS.has(extension)) {
    return "code";
  }
  if (READER_TEXT_EXTENSIONS.has(extension) || normalizedMime.startsWith("text/")) {
    return "text";
  }
  if (READER_ARCHIVE_EXTENSIONS.has(extension) || READER_ARCHIVE_MIME_TYPES.has(normalizedMime)) {
    return "archive";
  }
  if (READER_BINARY_EXTENSIONS.has(extension) || READER_BINARY_MIME_TYPES.has(normalizedMime)) {
    return "binary";
  }
  if (["application/json", "application/xml", "application/x-yaml", "application/toml"].includes(normalizedMime)) {
    return "text";
  }
  const kind = String(requestedKind || "").trim().toLowerCase();
  if (["image", "audio", "text", "code", "archive", "binary"].includes(kind)) {
    return kind;
  }
  return "";
}

function getReaderAttachmentLimit(kind) {
  if (kind === "image") {
    return MAX_READER_IMAGE_BYTES;
  }
  if (kind === "audio") {
    return MAX_READER_AUDIO_BYTES;
  }
  if (kind === "archive") {
    return MAX_READER_ARCHIVE_BYTES;
  }
  if (kind === "binary") {
    return MAX_READER_BINARY_BYTES;
  }
  return MAX_READER_TEXT_BYTES;
}

function buildReaderVisibleInputText(text, attachments) {
  const normalizedText = String(text || "").trim();
  const attachmentNames = (Array.isArray(attachments) ? attachments : [])
    .map((item, index) => path.basename(String(item && item.name ? item.name : `file-${index + 1}`)).trim())
    .filter(Boolean);

  if (!attachmentNames.length) {
    return normalizedText;
  }
  return [normalizedText, `附件：${attachmentNames.join("、")}`].filter(Boolean).join("\n");
}

function normalizeReaderAttachments(attachments) {
  const input = Array.isArray(attachments) ? attachments : [];
  const output = [];
  const errors = [];

  for (const item of input.slice(0, MAX_READER_ATTACHMENTS)) {
    if (!item || typeof item !== "object") {
      continue;
    }

    const data = String(item.data || "");
    const name = path.basename(String(item.name || "uploaded-file")).slice(0, 160) || "uploaded-file";
    const requestedMimeType = String(item.mime_type || item.type || "").trim().toLowerCase();
    const kind = classifyReaderAttachment(name, requestedMimeType, item.kind);
    const mimeType = guessReaderMimeType(name, kind, requestedMimeType);
    const size = Number(item.size) || estimateDataUrlBytes(data);

    if (!data.startsWith("data:") || !kind || !mimeType) {
      errors.push(`${name}: invalid attachment payload`);
      continue;
    }

    if (size > getReaderAttachmentLimit(kind)) {
      errors.push(`${name}: file is too large`);
      continue;
    }

    output.push({
      kind,
      name,
      data,
      mime_type: mimeType,
      size
    });
  }

  if (input.length > MAX_READER_ATTACHMENTS) {
    errors.push(`Only the first ${MAX_READER_ATTACHMENTS} files were attached.`);
  }

  return { attachments: output, errors };
}

module.exports = {
  buildReaderVisibleInputText,
  normalizeReaderAttachments
};
