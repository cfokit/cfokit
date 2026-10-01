// Builds the CFOKit design system, as the Design System artifact keeps it, into
// dist-design-system/project/. The repository is its source: docs/design holds the prose, and
// web/design and web/src/components the tokens, fonts, marks and components (ADR-0049 § 10).
//
//   README.md                    the brand book                  docs/design/README.md
//   tokens.json                  the tokens                      web/design/tokens.json
//   fonts/, licenses/            the faces and their licenses    web/design/fonts, web/public/licenses
//   assets/Logos/                the marks, and their notes      web/design/brand, docs/design/logos.md
//   components/bundle.js         window.CFOKit, on window.React  web/src/components
//   components/bundle.css        their stylesheet, by data-theme web/design/theme.design-system.css
//   components/index.d.ts        their props                     web/src/components
//   components/<Comp>/README.md  each one's guide                docs/design/components/<Comp>.md
//   components/<Comp>/preview.html  each one's live card         web/design/publish/previews
//
// The canvas supplies React 18 to every artboard, so the bundle is compiled to classic
// React.createElement against window.React rather than carrying the client's React 19.
// Run with `pnpm design-system`. Publishing the output to the artifact is a separate step.

import { copyFile, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import ts from "typescript";
import { build } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..", "..");
const docs = join(web, "..", "docs", "design");
const project = join(web, "dist-design-system", "project");
const out = join(project, "components");
const NAMESPACE = "CFOKit";

await rm(join(web, "dist-design-system"), { recursive: true, force: true });

async function copyDir(from, to, keep = () => true) {
  await mkdir(to, { recursive: true });
  for (const file of await readdir(from)) {
    if (keep(file)) await copyFile(join(from, file), join(to, file));
  }
}

// The brand book, the tokens, the faces with their licenses, and the marks with their notes.
await mkdir(project, { recursive: true });
await copyFile(join(docs, "README.md"), join(project, "README.md"));
await copyFile(join(web, "design", "tokens.json"), join(project, "tokens.json"));
await copyDir(join(web, "design", "fonts"), join(project, "fonts"));
await copyDir(join(web, "public", "licenses"), join(project, "licenses"));
await copyDir(join(web, "design", "brand"), join(project, "assets", "Logos"));
await copyFile(join(docs, "logos.md"), join(project, "assets", "Logos", "README.md"));

// The components, each with a preview here and a guide in docs/design.
const components = (await readdir(join(here, "previews")))
  .filter((f) => f.endsWith(".html"))
  .map((f) => f.replace(/\.html$/, ""))
  .sort();
const guides = (await readdir(join(docs, "components"))).map((f) => f.replace(/\.md$/, ""));

// Every exported component has a preview and a guide, and every preview and guide a component.
// Icons are parts of other components; types and formatMoney are not components.
const index = await readFile(join(web, "src", "components", "index.ts"), "utf8");
const exported = [...index.matchAll(/export \{ ([^}]+) \}/g)]
  .flatMap((m) => m[1].split(","))
  .map((n) => n.trim())
  .filter((n) => /^[A-Z]/.test(n) && !/Icon$/.test(n))
  .sort();
for (const [what, names] of [
  ["previews", components],
  ["guides", guides.sort()],
]) {
  if (names.join() !== exported.join()) {
    throw new Error(`${what} out of step with the exports: ${names} against ${exported}`);
  }
}

await build({
  configFile: false,
  root: web,
  publicDir: false,
  logLevel: "warn",
  plugins: [tailwindcss()],
  oxc: { jsx: { runtime: "classic", pragma: "React.createElement", pragmaFrag: "React.Fragment" } },
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: out,
    emptyOutDir: false,
    minify: true,
    lib: {
      entry: join(here, "entry.ts"),
      formats: ["iife"],
      name: NAMESPACE,
      fileName: () => "bundle.js",
      cssFileName: "bundle",
    },
    rollupOptions: { external: ["react"], output: { globals: { react: "React" } } },
  },
});

// The header names the namespace and the components, in order. Both files are inlined by the
// page that loads them, so neither may close its element.
const bundlePath = join(out, "bundle.js");
const bundle = await readFile(bundlePath, "utf8");
if (/<\/script|<!--/i.test(bundle)) throw new Error("bundle.js holds </script or <!--");
const header = {
  format: 4,
  namespace: NAMESPACE,
  components: components.map((name) => ({ name })),
};
await writeFile(bundlePath, `/* @ds-bundle: ${JSON.stringify(header)} */\n${bundle}`);
const css = await readFile(join(out, "bundle.css"), "utf8");
if (/<\/style/i.test(css)) throw new Error("bundle.css holds </style");

// The props, as one declaration file: each module's declarations in turn, their imports of one
// another dropped (they now share the file), React's types imported once.
const sources = (await readdir(join(web, "src", "components")))
  .filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) && f !== "index.ts")
  .sort()
  .map((f) => join(web, "src", "components", f));
const declarations = new Map();
ts.createProgram(sources, {
  target: ts.ScriptTarget.ES2023,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
  jsx: ts.JsxEmit.ReactJSX,
  strict: true,
  skipLibCheck: true,
  declaration: true,
  emitDeclarationOnly: true,
  types: ["vite/client"],
}).emit(undefined, (file, text) => declarations.set(file, text));
const stem = (path) => relative(web, path).replace(/(\.d\.ts|\.tsx?)$/, "");
const reactTypes = new Set();
const body = sources
  .map((source) => {
    const file = [...declarations.keys()].find((f) => stem(f) === stem(source));
    return (file === undefined ? "" : declarations.get(file))
      .split("\n")
      .filter((line) => {
        const react = /^import (?:type )?\{ ([^}]+) \} from "react";$/.exec(line);
        if (react) {
          for (const name of react[1].split(",")) reactTypes.add(name.replace(/^type /, "").trim());
          return false;
        }
        return !/^import .* from "\.\/[^"]+";$/.test(line) && line !== "export {};";
      })
      .join("\n")
      .trim();
  })
  .filter(Boolean)
  .join("\n\n");
await writeFile(
  join(out, "index.d.ts"),
  `// The props of window.${NAMESPACE}'s components, generated from web/src/components.\n` +
    `import type { ${[...reactTypes].sort().join(", ")} } from "react";\n\n${body}\n`,
);

for (const name of components) {
  await mkdir(join(out, name), { recursive: true });
  await copyFile(join(docs, "components", `${name}.md`), join(out, name, "README.md"));
  await copyFile(join(here, "previews", `${name}.html`), join(out, name, "preview.html"));
}

console.log(`dist-design-system/project: ${components.length} components`);
