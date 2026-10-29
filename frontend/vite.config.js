import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const googlePopupHeaders = {
  "Cross-Origin-Opener-Policy":
    "same-origin-allow-popups",

  "Cross-Origin-Embedder-Policy":
    "unsafe-none",

  "Referrer-Policy":
    "strict-origin-when-cross-origin",
};

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],

  server: {
    host: "localhost",
    port: 5173,
    strictPort: true,
    headers:
      googlePopupHeaders,
  },

  preview: {
    host: "localhost",
    port: 4173,
    strictPort: true,
    headers:
      googlePopupHeaders,
  },
});