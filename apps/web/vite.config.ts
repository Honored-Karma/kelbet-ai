import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { validateApiBaseUrl } from "./src/shared/api/config.js";

/**
 * Штамп сборки.
 *
 * Дважды за один день мы теряли часы на вопрос «доехал ли деплой»: сначала
 * из-за стека PR, не дошедшего до main, потом из-за кеша index.html. В самом
 * приложении не было ни одного способа узнать, какая версия перед тобой.
 *
 * Vercel отдаёт VERCEL_GIT_COMMIT_SHA сборочному процессу, но без префикса
 * VITE_ он не попадает в клиент — поэтому подставляем его через define.
 */
const buildCommit = (
  process.env.VERCEL_GIT_COMMIT_SHA ??
  process.env.GIT_COMMIT_SHA ??
  "local"
).slice(0, 7);
const buildTime = new Date().toISOString();

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
    plugins: [
      react(),
      {
        // Мета-тег читается снаружи одной командой: curl -s <домен> | grep kelbet-build.
        // Это делает вопрос «какая версия в проде» проверяемым, а не обсуждаемым.
        name: "kelbet-build-stamp",
        transformIndexHtml() {
          return [
            {
              tag: "meta",
              attrs: { name: "kelbet-build", content: `${buildCommit} ${buildTime}` },
              injectTo: "head" as const,
            },
          ];
        },
      },
    ],
    define: {
      __KELBET_BUILD__: JSON.stringify({ commit: buildCommit, builtAt: buildTime }),
    },
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
