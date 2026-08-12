import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const client = readFileSync(new URL("../src/shared/api/client.ts", import.meta.url), "utf8");
const providers = readFileSync(new URL("../src/app/providers.tsx", import.meta.url), "utf8");

// Транспортный слой тянет за собой fetch, sessionStorage и import.meta.env, а
// DOM-окружения в этом наборе тестов нет. Поэтому контракт проверяется по
// исходнику: важно не то, как именно устроен обработчик, а то, что три правила
// нельзя потерять при рефакторинге.

test("401 сбрасывает токен и объявляет сессию недействительной", () => {
  assert.match(client, /response\.status === 401/, "401 должен обрабатываться явно");
  assert.match(client, /setToken\(null\)/, "токен обязан сбрасываться");
  assert.match(
    client,
    /dispatchEvent\(new Event\(UNAUTHORIZED_EVENT\)\)/,
    "приложение должно узнавать о недействительной сессии",
  );
});

test("сам путь авторизации исключён, иначе получится цикл", () => {
  // Без этого условия неудачный обмен initData сбрасывал бы токен и снова
  // отправлял на /boot — бесконечная переавторизация вместо сообщения об ошибке.
  assert.match(client, /AUTH_PATH_PREFIX = "\/api\/v1\/auth\//);
  assert.match(client, /!path\.startsWith\(AUTH_PATH_PREFIX\)/);
});

test("граница ошибок и страж сессии подключены в дереве приложения", () => {
  assert.match(providers, /<ErrorBoundary/, "граница ошибок должна оборачивать приложение");
  assert.match(providers, /<SessionGuard>/, "страж сессии должен быть внутри роутера");
  // Порядок важен: страж навигирует, поэтому обязан находиться внутри роутера,
  // а подписи границы берутся из i18n, поэтому она внутри I18nProvider.
  const routerAt = providers.indexOf("<BrowserRouter>");
  const boundaryAt = providers.indexOf("<ErrorBoundary");
  const guardAt = providers.indexOf("<SessionGuard>");
  assert.ok(routerAt >= 0 && boundaryAt >= 0 && guardAt >= 0);
  assert.ok(boundaryAt < guardAt, "страж сессии должен быть внутри границы ошибок");
});
