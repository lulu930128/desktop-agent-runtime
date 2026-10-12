import path from "node:path";
import {createHash} from "node:crypto";
import fs from "node:fs";

const root = import.meta.dirname;
const originalEntry = '<script type="module" src="./src/work-panel/main.ts"></script>';
const csp = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'none'; media-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";
export default {
  root, base: "./", publicDir: false,
  plugins: [{name: "qt-owner-only",
    enforce: "pre",
    resolveId(source, importer) {
      if (source === "./model" && importer?.replaceAll("\\", "/").endsWith("/src/work-panel/main.ts"))
        return path.join(root, "src/canonical-model.ts");
    },
    transformIndexHtml: {order: "pre", handler(html) {
      if (!html.includes(originalEntry)) throw new Error("Original HTML changed");
      return html.replace(originalEntry, '<script type="module" src="./src/owner-bootstrap.ts"></script>')
        .replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" /><meta http-equiv="Content-Security-Policy" content="${csp}" />`);
    }},
    generateBundle(options, bundle) {
      for (const item of Object.values(bundle)) {
        if (item.type === "chunk" && Object.keys(item.modules).some(m => /(?:preview-bridge|synthetic\.json|\/qt\.ts|\/baseline\.ts)$/.test(m)))
          throw new Error("Synthetic preview module leaked into owner bundle");
      }
    },
    writeBundle(options, bundle) {
      const names = ["work-panel.html", ...fs.readdirSync(path.join(options.dir, "assets")).map(n => `assets/${n}`)];
      if (names.some(n => !/\.(?:html|js|css)$/.test(n))) throw new Error("Unexpected candidate asset type");
      const files = Object.fromEntries(names.map(name => [name,
        createHash("sha256").update(fs.readFileSync(path.join(options.dir, name))).digest("hex")]));
      fs.writeFileSync(path.join(options.dir, "candidate-manifest.json"), JSON.stringify({contract: "kuro.qt.assets.v1", files}, null, 2));
    }
  }],
  build: {outDir: path.join(root, "../.runtime/candidate-dist"), emptyOutDir: true, sourcemap: false,
    rollupOptions: {input: path.join(root, "work-panel.html")}}
};
