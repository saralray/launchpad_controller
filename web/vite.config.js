import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard imports the daemon's real config.json (one directory up) as the
// single source of truth for rooms / macros, so allow Vite to read the repo root.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    fs: { allow: [".", ".."] },
  },
});
