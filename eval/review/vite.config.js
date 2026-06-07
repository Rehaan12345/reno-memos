import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// review_api.py (FastAPI) runs on 8088; proxy /api to it during dev so the
// frontend can call same-origin paths and avoid CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8088",
    },
  },
});
