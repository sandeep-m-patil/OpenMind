import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In dev, /v1 and /health are proxied to the backend; in Docker, nginx does the same.
const BACKEND = process.env.OPSMIND_BACKEND ?? "http://127.0.0.1:8002";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3002,
    proxy: { "/v1": BACKEND, "/health": BACKEND },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/test/**", "src/**/*.test.{ts,tsx}", "src/types.ts"],
      thresholds: { lines: 80, branches: 75 },
    },
  },
});
