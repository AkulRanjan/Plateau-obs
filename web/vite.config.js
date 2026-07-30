import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Tailwind v4 ships a first-class Vite plugin; there is no postcss.config here
// on purpose. Base is relative so the built bundle opens from a file:// path or
// any subdirectory — the demo may be served off a USB stick at the venue.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  build: {
    target: "es2022",
    // Fail the build rather than silently shipping a chunk big enough to stall
    // first paint on projector hardware.
    chunkSizeWarningLimit: 700,
  },
});
