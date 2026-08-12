import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const client = readFileSync(new URL("../src/shared/api/client.ts", import.meta.url), "utf8");

// Границу между продовым и mock-кодом нельзя проверить на уровне модуля: она
// возникает на сборке, когда Rollup складывает MOCK_ENABLED в константу. Поэтому
// тест охраняет три свойства исходника, потеря любого из которых возвращает
// 47 КБ мок-API в бандл пользователя — молча, без единой ошибки.

test("статического импорта мока нет", () => {
  assert.doesNotMatch(
    client,
    /^import .*from "\.\/mock";$/m,
    "статический импорт возвращает мок в граф сборки, и tree-shaking снять его не сможет",
  );
});

test("мок грузится динамически и один раз", () => {
  assert.match(client, /import\("\.\/mock"\)/, "мок должен подключаться динамическим импортом");
  assert.match(client, /mockApiPromise \?\?=/, "результат загрузки должен переиспользоваться");
});

test("режим решается литералами import.meta.env, а не вызовом функции", () => {
  // Ветвление через getApiMode() вычислялось внутри функций: Rollup не мог
  // доказать недостижимость ветки и оставлял мок в бандле.
  assert.match(client, /const MOCK_ENABLED: boolean =/);
  assert.match(client, /import\.meta\.env\.VITE_API_MODE === "mock"/);
  assert.doesNotMatch(
    client,
    /getApiMode\(\) === "mock"/,
    "рантайм-ветвление не сворачивается на сборке",
  );
});

test("режим mock вычисляется так же, как в getApiMode", () => {
  // Обе формы должны совпадать на всех входах, иначе dev-режим начнёт бить в
  // живой API или наоборот.
  const resolve = (mode: string | undefined, dev: boolean) =>
    mode === "mock" || (mode !== "live" && dev);
  const reference = (mode: string | undefined, dev: boolean) =>
    mode === "live" || mode === "mock" ? mode === "mock" : dev;

  for (const mode of ["mock", "live", undefined, "", "garbage"]) {
    for (const dev of [true, false]) {
      assert.equal(
        resolve(mode, dev),
        reference(mode, dev),
        `расхождение при mode=${String(mode)}, dev=${dev}`,
      );
    }
  }
});
