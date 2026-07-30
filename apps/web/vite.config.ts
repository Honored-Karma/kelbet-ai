import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { validateApiBaseUrl } from "./src/shared/api/config.js";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (command === "build" && env.VITE_API_MODE === "live") {
    const validation = validateApiBaseUrl(env.VITE_API_BASE_URL, {
      production: mode === "production",
    });
    if (!validation.ok) {
      throw new Error(
        `[KELBET] Invalid VITE_API_BASE_URL: ${validation.reason}. ` +
          "Set the real Railway API HTTPS URL in Vercel and redeploy.",
      );
    }
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    server: {
      port: 5173,
      host: true,
    },
  };
});
