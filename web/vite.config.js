import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";

// The FastAPI backend (api.py) runs on 8077; proxy /api to it during dev so the
// frontend can call same-origin paths and avoid CORS in development.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Consume the shared graph package straight from source so edits are live
    // in dev with no rebuild step. dedupe keeps a single React instance.
    dedupe: ["react", "react-dom"],
    alias: {
      "@reno/graph": fileURLToPath(new URL("../packages/graph/src", import.meta.url)),
    },
  },
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8077",
    },
  },
});
