import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const viteConfig = readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8");
const profile = readFileSync(new URL("../src/pages/ProfilePage.tsx", import.meta.url), "utf8");

// Штамп существует ради одного вопроса — «какая версия передо мной» — который
// дважды стоил часов отладки: сначала стек PR, не дошедший до main, потом
// закешированный index.html. Оба раза ответа не было ни в интерфейсе, ни снаружи.

test("коммит берётся из переменной Vercel, а не выдумывается", () => {
  // VERCEL_GIT_COMMIT_SHA доступен сборке, но без префикса VITE_ не попадает
  // в клиент — поэтому он обязан идти через define.
  assert.match(viteConfig, /process\.env\.VERCEL_GIT_COMMIT_SHA/);
  assert.match(viteConfig, /__KELBET_BUILD__: JSON\.stringify/);
});

test("локальная сборка честно помечена как local", () => {
  // Отсутствие переменной не должно превращаться в пустую строку или undefined:
  // «local» читается однозначно и не выглядит как настоящий коммит.
  assert.match(viteConfig, /"local"/);
});

test("версия читается снаружи одной командой", () => {
  // curl -s <домен> | grep kelbet-build — проверка без открытия приложения.
  assert.match(viteConfig, /name: "meta"|tag: "meta"/);
  assert.match(viteConfig, /name: "kelbet-build"/);
  assert.match(viteConfig, /injectTo: "head"/);
});

test("версия видна пользователю в профиле", () => {
  // Чтобы её мог назвать человек с телефона, у которого нет curl.
  assert.match(profile, /__KELBET_BUILD__\.commit/);
  assert.match(profile, /__KELBET_BUILD__\.builtAt/);
  assert.match(profile, /tx\("profile\.build"\)/);
});
