import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend (api.py) runs on 8077; proxy /api to it during dev so the
// frontend can call same-origin paths and avoid CORS in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8077",
    },
  },
});
