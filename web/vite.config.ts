import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function stripOvWebRtcDevelopmentShortcut() {
  return {
    name: "strip-ov-web-rtc-development-shortcut",
    enforce: "pre" as const,
    transform(code: string, id: string) {
      const normalizedId = id.replaceAll("\\", "/");
      if (!normalizedId.includes("@nvidia/ov-web-rtc/dist/ov-web-rtc.js")) return null;

      const start = code.indexOf("static _registerKeyboardShortcut(){");
      const end = code.indexOf("static _buildOverlay", start);
      if (start < 0 || end < 0) {
        throw new Error("Le raccourci de développement ov-web-rtc n'a pas été trouvé pour être désactivé au build.");
      }
      return {
        code: `${code.slice(0, start)}static _registerKeyboardShortcut(){}${code.slice(end)}`,
        map: null
      };
    }
  };
}

export default defineConfig({
  plugins: [stripOvWebRtcDevelopmentShortcut(), react()],
  base: "./",
  define: {
    "window.OV_WEB_RTC_DEV": "false"
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: "assets/omniverse-panel.js",
        assetFileNames: "assets/omniverse-panel.[ext]"
      }
    }
  }
});
