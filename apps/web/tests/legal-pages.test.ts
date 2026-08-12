import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const terms = readFileSync(new URL("../public/terms.html", import.meta.url), "utf8");
const refunds = readFileSync(new URL("../public/refunds.html", import.meta.url), "utf8");
const pages = [
  ["terms.html", terms],
  ["refunds.html", refunds],
] as const;

// Обе страницы обслуживают production gate платежей: сервер отказывается
// принимать деньги, пока PAYMENT_TERMS_URL и PAYMENT_REFUND_POLICY_URL не
// указывают на публичные HTTPS-документы. Значит эти файлы — часть платёжного
// контура, а не украшение, и ломать их молча нельзя.

test("документы двуязычные: русский и казахский", () => {
  for (const [name, html] of pages) {
    assert.match(html, /<section lang="ru">/, `${name}: нет русской версии`);
    assert.match(html, /<section lang="kk"/, `${name}: нет казахской версии`);
  }
});

test("документы ссылаются друг на друга", () => {
  // Политика возврата объявлена неотъемлемой частью условий оплаты; читатель
  // должен добраться до второго документа из первого, не возвращаясь в чат.
  assert.match(terms, /href="\/refunds\.html"/);
  assert.match(refunds, /href="\/terms\.html"/);
});

test("версия документа проставлена и совпадает в обоих", () => {
  const version = /Версия документа 2026-08-12/;
  for (const [name, html] of pages) {
    assert.match(html, version, `${name}: версия не проставлена или не совпадает`);
  }
});

test("условия описывают то, что код действительно делает", () => {
  // Каждый из этих фактов подтверждён реализацией, а не желаемым:
  // payment_order_ttl_minutes = 30; резерв освобождается при неудаче;
  // расчёты только в XTR.
  assert.match(terms, /30 минут/, "срок жизни счёта должен совпадать с payment_order_ttl_minutes");
  assert.match(terms, /Telegram Stars \(XTR\)/, "валюта расчётов");
  assert.match(
    terms,
    /кредиты возвращаются на баланс автоматически/,
    "освобождение резерва при неудачной генерации",
  );
  assert.match(
    refunds,
    /двух возвратов на одного пользователя в сутки/,
    "лимит должен совпадать с stars_refund_user_daily_limit = 2",
  );
});

test("НЕ ЗАПОЛНЕНО: личность продавца и контакт поддержки", () => {
  // Этот тест красный намеренно и является блокировкой мержа.
  //
  // __SELLER_IDENTITY__ — имя, под которым продавец раскрывается покупателю.
  // Оно обязано совпадать с тем, кто фактически получает выплаты Telegram
  // Stars, и не может быть выведено из репозитория.
  //
  // __SUPPORT_USERNAME__ — контакт поддержки. Значение живёт в переменной
  // окружения, но Railway скрывает значения от подключённых приложений, поэтому
  // подставить его автоматически нельзя.
  //
  // Опубликовать документ с незаполненным местом хуже, чем не публиковать: он
  // выглядит официальным и при этом не называет сторону договора.
  for (const [name, html] of pages) {
    assert.ok(
      !html.includes("__SELLER_IDENTITY__"),
      `${name}: не указана личность продавца — заполните __SELLER_IDENTITY__`,
    );
    assert.ok(
      !html.includes("__SUPPORT_USERNAME__"),
      `${name}: не указан контакт поддержки — заполните __SUPPORT_USERNAME__`,
    );
  }
});
