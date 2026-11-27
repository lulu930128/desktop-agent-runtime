// Apply the reviewed history fix to the immutable upstream panel for Vite and its tests.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

const main = path.join(__dirname, 'src/work-panel/main.ts');
function historySource() {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'kuro-work-panel-'));
  const file = path.join(scratch, 'main.ts');
  try {
    fs.copyFileSync(main, file);
    execFileSync('git', ['-c', 'core.autocrlf=false', 'apply', '--no-index', '--whitespace=nowarn',
      path.join(__dirname, 'work-panel-history.patch')], {cwd: scratch, windowsHide: true});
    return fs.readFileSync(file, 'utf8');
  } finally {
    if (fs.existsSync(file)) fs.unlinkSync(file);
    fs.rmdirSync(scratch);
  }
}

function loadPanel(id) {
  if (path.resolve(id) === main) return historySource();
}

module.exports = {historySource, loadPanel};
