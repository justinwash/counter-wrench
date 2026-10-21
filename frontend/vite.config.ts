/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // In dev, the API runs separately (`make api`); in Docker, FastAPI serves the built UI itself.
  // 127.0.0.1, not "localhost": on Windows that can resolve to IPv6 only (same as D-010).
  server: { host: "127.0.0.1", proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "jsdom" },
});
