// The client's Tailwind theme, generated from tokens.json beside it (ADR-0049 § 10).
//
// tokens.json is the design system's tokens; theme.css and theme.design-system.css are this
// function's output, and theme.test.ts fails when they disagree. A change of look is a change to
// tokens.json, then `pnpm theme`. A family this does not know fails the generation rather than
// dropping out of the theme unnoticed.

type Themed = string | Record<string, string>;
interface Token {
  name: string;
  value: Themed;
}
interface TextStyle {
  name: string;
  fontSize: string;
  lineHeight: string;
  fontWeight: number;
  letterSpacing?: string;
}
interface Tokens {
  color: { themes: { id: string }[]; tokens: Token[] };
  type: {
    fonts: { family: string; file: string; weight: string; style: string }[];
    families: Record<string, string>;
    groups: { styles: TextStyle[] }[];
  };
  [family: string]: unknown;
}

// Each family's tokens land in a Tailwind namespace, losing a prefix that repeats it: `space-4`
// becomes `--spacing-4` and so `p-4`, `bp-tablet` becomes the `tablet:` variant.
const NAMESPACES: Record<string, { namespace: string; strip: string }> = {
  spacing: { namespace: "spacing", strip: "space-" },
  radius: { namespace: "radius", strip: "radius-" },
  shadow: { namespace: "shadow", strip: "shadow-" },
  breakpoint: { namespace: "breakpoint", strip: "bp-" },
  size: { namespace: "spacing", strip: "" },
};

// Tokens with no utility of their own are plain custom properties, used as `outline-(--stroke-focus)`.
const PLAIN = new Set(["stroke"]);

// Every default the design system replaces is cleared, so a utility outside it does not exist.
const RESETS = ["color", "font", "text", "spacing", "radius", "shadow", "breakpoint", "container"];

// Where the theme is used. The client follows the device's light or dark setting and serves its
// own fonts. The design system's copy of the components follows the theme its page or canvas sets
// with `data-theme`, and takes its fonts from the system's own tokens.css.
export type Target = "client" | "design-system";

export function themeCss(tokens: Tokens, target: Target = "client"): string {
  const themes = tokens.color.themes.map((t) => t.id);
  const [first, ...others] = themes;
  if (first === undefined) throw new Error("tokens.json declares no color theme");

  const theme: string[] = [];
  const plain: string[] = [];
  const overrides = new Map<string, string[]>(others.map((id) => [id, []]));

  const themed = (property: string, value: Themed, into: string[]) => {
    if (typeof value === "string") {
      into.push(`${property}: ${value};`);
      return;
    }
    into.push(`${property}: ${value[first]};`);
    for (const id of others) {
      const v = value[id];
      if (v !== undefined && v !== value[first]) overrides.get(id)?.push(`${property}: ${v};`);
    }
  };

  // `"{accent}"` names another color token, so it follows that token into every theme.
  for (const { name, value } of tokens.color.tokens) {
    const alias = typeof value === "string" && /^\{([\w.-]+)\}$/.exec(value);
    themed(`--color-${name}`, alias ? `var(--color-${alias[1]})` : value, theme);
  }

  for (const [family, stack] of Object.entries(tokens.type.families)) {
    theme.push(`--font-${family}: ${stack};`);
  }
  for (const style of tokens.type.groups.flatMap((g) => g.styles)) {
    const p = `--text-${style.name}`;
    theme.push(`${p}: ${style.fontSize};`);
    theme.push(`${p}--line-height: ${style.lineHeight};`);
    theme.push(`${p}--font-weight: ${style.fontWeight};`);
    if (style.letterSpacing !== undefined) {
      theme.push(`${p}--letter-spacing: ${style.letterSpacing};`);
    }
  }

  for (const [family, body] of Object.entries(tokens)) {
    if (family === "name" || family === "version" || family === "color" || family === "type") {
      continue;
    }
    const list = (body as { tokens?: Token[] }).tokens;
    if (list === undefined) throw new Error(`tokens.json family "${family}" has no tokens list`);
    for (const { name, value } of list) {
      const [property, isPlain] = place(family, name, value);
      themed(property, value, isPlain ? plain : theme);
    }
  }

  const fontFaces = (target === "client" ? tokens.type.fonts : []).map((f) =>
    [
      "@font-face {",
      `  font-family: "${f.family}";`,
      `  src: url("./${f.file}") format("woff2");`,
      `  font-weight: ${f.weight};`,
      `  font-style: ${f.style};`,
      "  font-display: swap;",
      "}",
    ].join("\n"),
  );

  const block = (selector: string, lines: string[]) =>
    [`${selector} {`, ...lines.map((l) => `  ${l}`), "}"].join("\n");
  const override = (id: string, lines: string[]) =>
    target === "client"
      ? [
          `@media (prefers-color-scheme: ${id}) {`,
          ...block(":root", lines)
            .split("\n")
            .map((l) => `  ${l}`),
          "}",
        ].join("\n")
      : block(`[data-theme="${id}"]`, lines);
  // Tailwind's `dark:` follows the same switch as the colors.
  const variant =
    target === "client"
      ? []
      : [`@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));`];

  return (
    [
      `/* Generated from tokens.json by theme.ts. Do not edit: change tokens.json, then \`pnpm theme\`. */`,
      ...variant,
      ...fontFaces,
      block("@theme", [
        ...RESETS.map((r) => `--${r}-*: initial;`),
        "--spacing: initial;",
        // Zero is not a step of the scale but where it starts: inset-0, m-0, min-w-0.
        "--spacing-0: 0px;",
        ...theme,
      ]),
      block(":root", plain),
      ...[...overrides].filter(([, lines]) => lines.length > 0).map(([id, l]) => override(id, l)),
    ].join("\n\n") + "\n"
  );
}

// Where a token goes: its custom property, and whether it is plain rather than theme.
function place(family: string, name: string, value: Themed): [string, boolean] {
  const rule = NAMESPACES[family];
  if (rule !== undefined) return [`--${rule.namespace}-${name.replace(rule.strip, "")}`, false];
  if (PLAIN.has(family)) return [`--${name}`, true];
  if (family === "layout") {
    // Column counts are numbers, not lengths; the -max widths cap a container; gutters are space.
    if (/^\d+$/.test(String(value))) return [`--${name}`, true];
    if (name.endsWith("-max")) return [`--container-${name}`, false];
    return [`--spacing-${name}`, false];
  }
  throw new Error(`tokens.json family "${family}" has no place in the theme`);
}
