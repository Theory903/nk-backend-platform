import { defineConfig } from "vite";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Assets are served by FastAPI from `/static/studio/dist`, so the bundle is
// built with stable (unhashed) filenames that `web/api/docs/views.py` can
// reference directly. Cache busting is handled server-side via a mtime query.
const OUT_DIR = "../{{cookiecutter.project_name}}/static/studio/dist";
const PUBLIC_BASE = "/static/studio/dist/";

// During `npm run dev`, proxy the API surface to the running FastAPI app so the
// Studio can load the live OpenAPI schema and send real requests.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

export default defineConfig({
  base: PUBLIC_BASE,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: OUT_DIR,
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: "studio.js",
        chunkFileNames: "studio-[name].js",
        assetFileNames: "studio.[ext]",
      },
    },
  },
  server: {
    proxy: {
      "/api": { target: API_ORIGIN, changeOrigin: true },
      "/static": { target: API_ORIGIN, changeOrigin: true },
    },
  },
});
