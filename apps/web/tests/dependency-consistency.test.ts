import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";

// Почему этот тест существует.
//
// 12 августа в App.tsx появился `import { Analytics } from "@vercel/analytics/react"`,
// а сам пакет в package.json не попал. `tsc -b` падал с TS2307, Vercel останавливал
// сборку, и прод продолжал отдавать прежнюю версию — молча, потому что Vercel
// считает это обычной неудачной сборкой, а не инцидентом. Mini App простояло
// незамеченным двое суток, вместе со всей фронтовой работой этих дней.
//
// Отдельная проверка нужна именно потому, что симптом не выглядит как поломка:
// приложение в проде работает, просто оно старое.

const root = path.dirname(fileURLToPath(new URL("../package.json", import.meta.url)));
const manifest = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8")) as {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};
const declared = new Set([
  ...Object.keys(manifest.dependencies ?? {}),
  ...Object.keys(manifest.devDependencies ?? {}),
]);

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const full = path.join(directory, entry);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.tsx?$/.test(entry) ? [full] : [];
  });
}

/** Корень пакета из спецификатора импорта: "@scope/name/sub" → "@scope/name". */
function packageRoot(specifier: string): string {
  const segments = specifier.split("/");
  return specifier.startsWith("@") ? segments.slice(0, 2).join("/") : segments[0];
}

function importedPackages(contents: string): string[] {
  const specifiers = [...contents.matchAll(/(?:from|import)\s+"([^"]+)"/g)].map(
    (match) => match[1],
  );
  return specifiers
    .filter((specifier) => !specifier.startsWith("."))
    // `@/` — алиас на src/, настроенный в vite.config.ts, а не пакет.
    .filter((specifier) => !specifier.startsWith("@/"))
    // Встроенные модули Node существуют без объявления.
    .filter((specifier) => !specifier.startsWith("node:"))
    .map(packageRoot);
}

test("каждый импортируемый пакет объявлен в package.json", () => {
  const missing = new Map<string, string[]>();

  for (const file of sourceFiles(path.join(root, "src"))) {
    for (const name of importedPackages(readFileSync(file, "utf8"))) {
      if (declared.has(name)) continue;
      const relative = path.relative(root, file);
      missing.set(name, [...(missing.get(name) ?? []), relative]);
    }
  }

  assert.deepEqual(
    Object.fromEntries(missing),
    {},
    "эти пакеты импортируются, но не объявлены — сборка Vercel упадёт с TS2307",
  );
});

test("разбор импортов действительно ловит неучтённый пакет", () => {
  // Без этой проверки предыдущий тест мог бы зеленеть из-за сломанной регулярки,
  // а не из-за порядка в зависимостях.
  const sample = [
    'import { Analytics } from "@vercel/analytics/react";',
    'import { QueryClient } from "@tanstack/react-query";',
    'import ReactDOM from "react-dom/client";',
  ].join("\n");

  assert.deepEqual(importedPackages(sample), [
    "@vercel/analytics",
    "@tanstack/react-query",
    "react-dom",
  ]);
});

test("относительные пути, алиас и встроенные модули не считаются пакетами", () => {
  const sample = [
    'import { AppProviders } from "./app/providers";',
    'import "./styles/global.css";',
    'import x from "@/shared/api/client";',
    'import fs from "node:fs";',
  ].join("\n");

  assert.deepEqual(importedPackages(sample), []);
});
