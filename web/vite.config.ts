import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { keycloakify } from "keycloakify/vite-plugin";
import { configDefaults, defineConfig } from "vitest/config";

// The client is served at /app/ on the API's origin — by the REST service, or on GCP by a CDN at
// the same path (ADR-0049 § 5, ADR-0055). The same project builds the issuer's sign-in theme
// (ADR-0054 § 1): `keycloakify build` writes it as a JAR to dist_keycloak/.
export default defineConfig({
  base: "/app/",
  plugins: [
    react(),
    tailwindcss(),
    keycloakify({
      themeName: "cfokit",
      accountThemeImplementation: "none",
      keycloakVersionTargets: { "22-to-25": false, "all-other-versions": "cfokit-theme.jar" },
    }),
  ],
  experimental: {
    // A file a script loads is found relative to that script, not at /app/. The same build is
    // also the sign-in theme, served from the issuer's origin under another path, and Keycloakify's
    // rewrite of /app/ in Vite's preload helper does not match the helper Vite 8 emits — so every
    // page the theme loads on demand, the security-key pages among them, failed to load its CSS
    // and rendered blank. Relative to the script, the URL is right on both origins.
    renderBuiltUrl: (_filename, { hostType }) =>
      hostType === "js" ? { relative: true } : undefined,
  },
  build: {
    outDir: "dist",
    // Never inline a file as a data: URI. The CSP is default-src 'self' (ADR-0049 § 6), which
    // refuses data: images and fonts, and every file is a hashed asset of its own anyway.
    assetsInlineLimit: 0,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test-setup.ts"],
    // The end-to-end test drives a browser against a running stack, through Playwright.
    exclude: [...configDefaults.exclude, "e2e/**"],
    // Vitest blanks CSS by default; the theme test reads the generated theme as text.
    css: { include: [/design\/theme\.css/] },
  },
});
