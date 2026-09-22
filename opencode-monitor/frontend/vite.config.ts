import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// vite.config.ts (P2): /api proxy -> backend 4100 + CORS二重保険
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    cors: true,
    proxy: {
      "/api": {
        target: "http://localhost:4100",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 5173,
    cors: true,
    proxy: {
      "/api": {
        target: "http://localhost:4100",
        changeOrigin: true,
      },
    },
  },
});
