// No third-party dependencies, browser, Qt, or package installation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "geometry.js"), "utf8");
const sourceCss = fs.readFileSync(path.join(__dirname, "frontend/src/work-panel/styles.css"), "utf8");
const rootBlock = sourceCss.match(/^:root\s*\{([^}]*)\}/);
assert.ok(rootBlock, "Original :root must exist");
const sourceTokens = Object.fromEntries(Array.from(rootBlock[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g),
  ([, name, value]) => [name, value.trim()]));
assert.equal(Object.keys(sourceTokens).length, 16, "Original stable token count changed; review measurement coverage");

function measure(values) {
  const lookups = [];
  const css = {
    length: 0,
    *[Symbol.iterator]() {}, // Qt-style resolution with no enumerated names.
    getPropertyValue(name) {
      lookups.push(name);
      return Object.hasOwn(values, name) ? `  ${values[name]}  ` : "";
    },
    font: "14px sans-serif", color: "rgb(231, 234, 240)",
    backgroundColor: "rgb(16, 19, 25)", display: "grid"
  };
  assert.deepEqual(Array.from(css), []);
  const node = {getBoundingClientRect: () => ({x: 0, y: 0, width: 1280, height: 720})};
  const document = {
    documentElement: {scrollWidth: 1280, scrollHeight: 720},
    body: {innerText: "SYNTHETIC"}, fonts: {status: "loaded"},
    querySelector: () => node, querySelectorAll: () => []
  };
  const result = JSON.parse(vm.runInNewContext(script, {
    document, getComputedStyle: () => css,
    innerWidth: 1280, innerHeight: 720, devicePixelRatio: 1,
    screen: {width: 2560, height: 1440, colorDepth: 32},
    navigator: {userAgent: "SYNTHETIC mock", language: "ja"}
  }, {timeout: 1000}));
  assert.deepEqual(lookups.sort(), Object.keys(sourceTokens).sort(), "Read every source token explicitly");
  return result;
}

const complete = measure(sourceTokens);
assert.deepEqual(complete.tokens, sourceTokens, "An empty iterator must not erase resolved tokens");
// Read computed values, not hardcoded CSS defaults (e.g. responsive overrides).
const overridden = measure({...sourceTokens, "--rail-width": "76px"});
assert.equal(overridden.tokens["--rail-width"], "76px");
const missingValues = {...sourceTokens};
delete missingValues["--iris"];
const missing = measure(missingValues);
assert.equal(missing.tokens["--iris"], "", "Missing values stay visible; never backfill a default");
assert.equal(Object.keys(missing.tokens).length, 16);

if (process.argv.includes("--json")) {
  process.stdout.write(JSON.stringify({complete, overridden, missing}));
} else {
  process.stdout.write("PASS: 16 canonical tokens with empty iterator; computed override; missing token stays empty\n");
}
