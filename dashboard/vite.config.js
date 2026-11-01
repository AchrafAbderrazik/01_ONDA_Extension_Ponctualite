import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En développement, les appels /api sont redirigés vers l'API Flask (port 5050).
export default defineConfig({
  plugins: [react()],
  base: "/",
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:5050" } },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
