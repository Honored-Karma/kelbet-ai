import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const webapp = readFileSync(new URL("../src/shared/telegram/webapp.ts", import.meta.url), "utf8");
const hook = readFileSync(
  new URL("../src/shared/telegram/useTelegramBackButton.ts", import.meta.url),
  "utf8",
);
const shell = readFileSync(new URL("../src/app/layout/AppShell.tsx", import.meta.url), "utf8");

test("вызовы SDK не падают там, где методов нет", () => {
  // HapticFeedback и BackButton появились не во всех клиентах Telegram, а на
  // десктопе части методов нет вовсе. Отсутствие отдачи — не ошибка, и оно не
  // должно ронять действие, которое её вызвало.
  assert.match(webapp, /HapticFeedback\?\.impactOccurred\?\./);
  assert.match(webapp, /HapticFeedback\?\.notificationOccurred\?\./);
  assert.match(webapp, /const backButton = webApp\?\.BackButton;/);
  assert.match(webapp, /if \(!backButton\) \{\s*return \(\) => \{\};/);
});

test("подписка на кнопку «назад» снимается", () => {
  // Telegram держит подписки на своей стороне: незакрытая продолжает
  // навигировать после того, как экран уже размонтирован.
  assert.match(webapp, /backButton\.offClick\(onClick\)/);
  assert.match(webapp, /backButton\.hide\(\)/);
});

test("на корневых вкладках кнопки «назад» нет", () => {
  // Уводить «назад» с корневой вкладки некуда: Telegram в этом случае закрыл бы
  // мини-приложение, чего пользователь не просил.
  for (const route of ["/", "/history", "/create", "/plans", "/profile"]) {
    assert.ok(hook.includes(`"${route}"`), `корневой маршрут ${route} должен быть в списке`);
  }
  assert.match(hook, /if \(isRoot\) \{\s*hideBackButton\(\);/);
});

test("открытие по прямой ссылке не оставляет пользователя в тупике", () => {
  // location.key === "default" — первая запись истории: шага назад нет, и
  // navigate(-1) ничего бы не сделал.
  assert.match(hook, /location\.key === "default"/);
  assert.match(hook, /navigate\("\/", \{ replace: true \}\)/);
});

test("кнопка подключена в оболочке приложения", () => {
  assert.match(shell, /useTelegramBackButton\(\)/);
});
