import path from "node:path";

const root = import.meta.dirname;
// The archived HTML stays byte-identical. This is the entire entry-only delta.
const originalEntry = '<script type="module" src="./src/work-panel/main.ts"></script>';
const csp = "default-src 'none'; script-src 'self' qrc:; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'none'; media-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";

export default {
  root,
  base: "./",
  publicDir: false,
  plugins: [{
    name: "isolated-bootstrap-only",
    transformIndexHtml: {
      order: "pre",
      handler(html, context) {
        if (!html.includes(originalEntry)) throw new Error("Original HTML entry changed");
        const mode = context.filename.endsWith("qt-preview.html") ? "qt" : "baseline";
        return html.replace(originalEntry, `<script type="module" src="./src/${mode}.ts"></script>`)
          .replace('<meta charset="UTF-8" />', `<meta charset="UTF-8" /><meta http-equiv="Content-Security-Policy" content="${csp}" />`);
      }
    }
  }],
  build: {
    outDir: path.join(root, "dist"),
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: { input: {
      baseline: path.join(root, "work-panel.html"),
      qt: path.join(root, "qt-preview.html")
    } }
  }
};
