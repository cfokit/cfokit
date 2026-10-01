import tokens from "./tokens.json";
import css from "./theme.css?raw";
import { themeCss } from "./theme";

// The committed theme is what the generator makes of the committed tokens. `pnpm theme` rewrites
// it; CI, which never updates a snapshot, fails on any difference.
test("theme.css is generated from tokens.json", async () => {
  await expect(themeCss(tokens)).toMatchFileSnapshot("./theme.css");
});

test("the design system's theme is generated from the same tokens", async () => {
  await expect(themeCss(tokens, "design-system")).toMatchFileSnapshot("./theme.design-system.css");
});

test("the design system's theme follows data-theme and leaves the fonts to the system", () => {
  const ds = themeCss(tokens, "design-system");
  expect(ds).toContain('[data-theme="dark"] {');
  expect(ds).toContain("--color-paper: #12161c;");
  expect(ds).not.toContain("prefers-color-scheme");
  expect(ds).not.toContain("@font-face");
});

// The checks below take their expected values from tokens.json and the design system's README,
// not from the generator, so a generator that drops or misplaces a token fails here too.

const darkBlock = /@media \(prefers-color-scheme: dark\) \{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
const lightPart = css.replace(darkBlock, "");

test.each(tokens.color.tokens)("color $name is set for both themes", ({ name, value }) => {
  if (typeof value === "string") {
    expect(lightPart).toContain(`--color-${name}: var(--color-${value.slice(1, -1)});`);
    return;
  }
  expect(lightPart).toContain(`--color-${name}: ${value.light};`);
  expect(darkBlock).toContain(`--color-${name}: ${value.dark};`);
});

test("only the design system's colors, sizes and breakpoints exist", () => {
  for (const reset of ["color", "text", "spacing", "radius", "breakpoint"]) {
    expect(css).toContain(`--${reset}-*: initial;`);
  }
});

test("every text style carries its size, line height and weight", () => {
  for (const style of tokens.type.groups.flatMap((g) => g.styles)) {
    expect(css).toContain(`--text-${style.name}: ${style.fontSize};`);
    expect(css).toContain(`--text-${style.name}--line-height: ${style.lineHeight};`);
    expect(css).toContain(`--text-${style.name}--font-weight: ${style.fontWeight};`);
  }
});

test("the README's utility names resolve", () => {
  // Names the design system's README uses for spacing, corners and layout, as Tailwind keys.
  for (const property of [
    "--spacing-1: 4px;",
    "--spacing-6: 24px;",
    "--spacing-10: 40px;",
    "--spacing-target-min: 44px;",
    "--spacing-bar-height: 56px;",
    "--radius-sm: 3px;",
    "--radius-lg: 8px;",
    "--breakpoint-tablet: 640px;",
    "--breakpoint-desktop: 1024px;",
    "--container-reading-max: 65ch;",
    "--stroke-focus: 2px;",
  ]) {
    expect(css).toContain(property);
  }
});

// Each face is bundled, so the build names it by its content hash and it can be cached for good,
// and its license ships in the same build (ADR-0049 § 6, § 9).
const fonts = Object.keys(import.meta.glob("./fonts/*", { query: "?url" }));
const licenses = Object.keys(import.meta.glob("/public/licenses/*", { query: "?url" }));

test.each(tokens.type.fonts)("$file is bundled, with its license", ({ family, file }) => {
  expect(fonts).toContain(`./${file}`);
  expect(css).toContain(`src: url("./${file}") format("woff2");`);
  expect(licenses).toContain(`/public/licenses/${family.replaceAll(" ", "")}-OFL.txt`);
});
