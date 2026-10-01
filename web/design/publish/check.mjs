// Mounts every preview the design system build wrote, as Claude Design will: on React 18, with
// window.CFOKit from components/bundle.js. The client runs React 19 and its tests run there, so
// a component that comes to depend on something only React 19 has passes them and breaks on the
// canvas. This is where that fails instead. Run by `pnpm design-system`, after build.mjs.

import { readdir, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const web = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = join(web, "dist-design-system", "project", "components");
const require = createRequire(import.meta.url);
const read = (path) => readFile(path, "utf8");

// React 18's browser builds, from the packages aliased as react-18 and react-dom-18.
const umd = (pkg, file) => read(join(dirname(require.resolve(`${pkg}/package.json`)), "umd", file));
const react = await umd("react-18", "react.production.min.js");
const reactDom = await umd("react-dom-18", "react-dom.production.min.js");
const bundle = await read(join(out, "bundle.js"));

// jsdom has <dialog> but not its modal methods; a browser has both.
const dialog = `if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
}`;

const names = (await readdir(out, { withFileTypes: true }))
  .filter((d) => d.isDirectory())
  .map((d) => d.name);

const failures = [];
for (const name of names) {
  const preview = await read(join(out, name, "preview.html"));
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (error) => errors.push(error.message));
  virtualConsole.on("error", (...args) => errors.push(args.join(" ")));
  const html = preview.replace(
    "<head>",
    `<head><script>${dialog}</script><script>${react}</script><script>${reactDom}</script>` +
      `<script>${bundle}</script>`,
  );
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole,
  });
  await new Promise((resolve) => setTimeout(resolve, 100));
  const root = dom.window.document.getElementById("root");
  const version = dom.window.React?.version;
  if (version !== "18.3.1") errors.push(`ran on React ${version}`);
  if (root === null || root.childElementCount === 0) errors.push("rendered nothing");
  if (errors.length > 0) failures.push(`${name}: ${errors.join("; ")}`);
  dom.window.close();
}

if (failures.length > 0) {
  throw new Error(`previews that fail on React 18:\n  ${failures.join("\n  ")}`);
}
process.stdout.write(`dist-design-system: ${names.length} previews render on React 18.3.1\n`);
