import assert from "node:assert/strict";
import test from "node:test";

import { creditTransactionSchema } from "../src/shared/api/types.ts";

const row = {
  id: "0e2a7b6c-1f3d-4a58-9c11-6b7e0d4a2f90",
  type: "debit",
  reason: "generation_capture",
  amount: -80,
  balance_after: 340,
  created_at: "2026-08-12T09:15:00Z",
  generation_id: "1f1c3c40-6f4a-4a5e-8f0c-2b6a5f9d1e77",
};

test("строка леджера разбирается со ссылкой на работу", () => {
  const parsed = creditTransactionSchema.parse(row);
  assert.equal(parsed.amount, -80);
  assert.equal(parsed.balance_after, 340);
  assert.equal(parsed.generation_id, "1f1c3c40-6f4a-4a5e-8f0c-2b6a5f9d1e77");
});

test("движение без привязки к работе допустимо", () => {
  const parsed = creditTransactionSchema.parse({
    ...row,
    type: "credit",
    reason: "welcome_bonus",
    amount: 60,
    balance_after: 60,
    generation_id: null,
  });
  assert.equal(parsed.generation_id, null);
  assert.equal(parsed.type, "credit");
});

test("арифметика выписки сходится: остаток каждой строки равен предыдущему плюс сумма", () => {
  // Именно это свойство пользователь и должен иметь возможность проверить —
  // ради него в ответе есть balance_after, а не только сумма.
  const newestFirst = [
    { amount: -80, balance_after: 340 },
    { amount: 300, balance_after: 420 },
    { amount: 60, balance_after: 120 },
  ].map((partial, index) =>
    creditTransactionSchema.parse({
      ...row,
      id: `row-${index}`,
      amount: partial.amount,
      balance_after: partial.balance_after,
      generation_id: null,
    }),
  );

  for (let index = 0; index < newestFirst.length - 1; index += 1) {
    const current = newestFirst[index]!;
    const previous = newestFirst[index + 1]!;
    assert.equal(
      current.balance_after,
      previous.balance_after + current.amount,
      `строка ${index} не сходится с предыдущей`,
    );
  }
});

test("неизвестная причина не ломает разбор", () => {
  // Бэкенд может добавить новое значение TxReason раньше, чем фронтенд узнает
  // о нём. Строка обязана дойти до экрана и показать причину как есть, а не
  // исчезнуть из выписки.
  const parsed = creditTransactionSchema.parse({
    ...row,
    reason: "some_future_reason",
  });
  assert.equal(parsed.reason, "some_future_reason");
});
