import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { keycloakify } from "keycloakify/vite-plugin";
import { defineConfig } from "vitest/config";

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
    // Vitest blanks CSS by default; the theme test reads the generated theme as text.
    css: { include: [/design\/theme\.css/] },
  },
});
