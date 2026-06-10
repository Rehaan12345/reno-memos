import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";

// review_api.py (FastAPI) runs on 8088; proxy /api to it during dev so the
// frontend can call same-origin paths and avoid CORS.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Consume the shared graph package straight from source so edits are live
    // in dev with no rebuild step. dedupe keeps a single React instance.
    dedupe: ["react", "react-dom"],
    alias: {
      "@reno/graph": fileURLToPath(new URL("../../packages/graph/src", import.meta.url)),
    },
  },
  server: {
    port: 5190,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8088",
    },
  },
});
