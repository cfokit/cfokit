import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The client is served at /app/ on the API's origin — by the REST service, or on GCP by a CDN at
// the same path (ADR-0049 § 5, ADR-0055).
export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
  },
  test: {
    environment: "jsdom",
    globals: true,
    // Vitest blanks CSS by default; the theme test reads the generated theme as text.
    css: { include: [/src\/design\/theme\.css/] },
  },
});
