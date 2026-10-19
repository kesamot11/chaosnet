import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The controller (chaosnet-api); its default CHAOSNET_PORT.
const API = "http://127.0.0.1:8476";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    // The browser talks only to this dev server; it forwards /api to the controller.
    // Same origin for the browser, so the API needs no CORS headers (ADR-005).
    proxy: {
      "/api": { target: API, rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
