import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Inline JS+CSS into a single index.html so it loads over file:// in pywebview
// (WebView2 blocks separate module scripts served from file:// via CORS).
export default defineConfig({
  base: "./",
  plugins: [react(), viteSingleFile()],
});
