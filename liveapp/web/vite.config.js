import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built into ../static/app and served by FastAPI at "/" (works offline: fonts and libraries are bundled).
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: { outDir: "../static/app", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/static": "http://127.0.0.1:8000" } },
});
