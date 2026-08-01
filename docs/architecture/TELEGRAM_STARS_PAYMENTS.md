# KELBET AI — Telegram Stars: платежи, refunds и reconciliation

**Статус:** технический контур реализован локально через migration `0015_stars_refunds`; production gate не
подтверждён, все внешние возможности выключены по умолчанию.  
**Обновлено:** 1 августа 2026.

## Неизменяемые правила

- Цифровые AI credits внутри Telegram продаются только за `XTR`.
- Mini App не рассчитывает цены: order хранит серверный snapshot credits, Stars и terms version.
- Один `telegram_payment_charge_id` соответствует одному receipt и одному ledger credit
  `stars:<charge_id>`.
- Refund создаётся только ролью `admin`; `support` видит состояние и расхождения без права записи.
- Telegram API и PostgreSQL не считаются одной атомарной транзакцией.
- Prompt, media, raw Telegram response, bot token и полный exception text не сохраняются в
  payment tables, audit или metric labels.

## Production gate

Флаг `PAYMENTS_ENABLED=true` сам по себе ничего не разрешает. Сервер дополнительно требует:

1. публичный HTTPS `PAYMENT_TERMS_URL`;
2. публичный HTTPS `PAYMENT_REFUND_POLICY_URL`;
3. непустую утверждённую `PAYMENT_TERMS_VERSION` (не `draft`/`placeholder`/`unapproved`);
4. `PAYMENT_SELLER_IDENTITY`;
5. явное `PAYMENT_FINANCE_REVIEW_CONFIRMED=true`;
6. рабочий `SUPPORT_USERNAME`.

Эти значения — технические свидетельства gate, а не юридическое утверждение со стороны
репозитория. Пока реальный владелец не разместил материалы и не подтвердил finance/seller/support,
оставить следующие значения:

```env
PAYMENTS_ENABLED=false
STARS_REFUNDS_ENABLED=false
STARS_RECONCILIATION_ENABLED=false
PAYMENT_REFUND_POLICY_URL=
PAYMENT_SELLER_IDENTITY=
PAYMENT_FINANCE_REVIEW_CONFIRMED=false
STARS_CANARY_TELEGRAM_IDS=
```

Отключение новых invoices не требует отключать read-only reconciliation во время rollback.
Независимые флаги позволяют остановить каждую внешнюю операцию отдельно.

## Purchase flow

```text
product → terms acceptance → durable order/snapshot → XTR invoice
        → pre_checkout validation → successful_payment
        → durable receipt → idempotent ledger credit → paid order
```

Pre-checkout проверяет buyer Telegram ID, `XTR`, точную сумму, срок и состояние order. Credits
выдаются только после durable `successful_payment`. Неизвестный payload или несовпадение
сохраняются как rejected receipt без ledger credit.

## Refund state machine

```text
requested → processing → refunded
    │            ├──────→ failed → processing
    │            └──────→ needs_review
    └───────────────────→ needs_review
```

`payment_refunds` уникален по order, receipt, charge ID и operator reference. Admin request и audit
записываются до внешнего вызова. Maintain worker:

1. атомарно claim-ит одну due запись через row lock;
2. фиксирует `processing` и завершает DB transaction;
3. вызывает `refundStarPayment(user_id, telegram_payment_charge_id)` без открытой DB transaction;
4. в новой transaction выполняет idempotent debit
   `stars-refund:<telegram_payment_charge_id>`;
5. переводит order/receipt/refund в `refunded`.

При временном однозначном отказе используются ограниченные retry 30 секунд / 5 минут / 30 минут.
Timeout имеет неизвестный внешний результат и сразу становится `needs_review`: повторять внешний
refund вслепую нельзя. Если credits уже потрачены или зарезервированы, автоматический refund не
начинается; случай попадает в review. Лимиты на пользователя и оператора также переводят request в
review, а не обходятся.

## Reconciliation

Worker периодически читает `getStarTransactions(offset, limit)` страницами до текущего конца,
сохраняет только нормализованные metadata и сверяет:

- incoming transaction без receipt;
- paid order без ledger credit;
- purchase ledger credit без наблюдаемой incoming transaction;
- подтверждённый refund без reverse ledger;
- повтор transaction/charge ID в одном ответе;
- amount mismatch;
- outgoing transaction с тем же ID, что у исходной покупки.

Telegram документирует совпадение ID refund-транзакции с исходной покупкой, но не предоставляет
отдельный `chargeback` transaction type. Поэтому outgoing transaction без известного локального
refund помечается как `external_reversal` с классификацией
`suspected_chargeback_or_external_refund`, order/receipt переходят в `disputed`, а окончательное
решение принимает оператор. Код намеренно не выдумывает несуществующее поле Bot API.

Наблюдаемый outgoing transaction восстанавливает случай «Telegram refund успешен, запись ledger
не завершилась»: reconciliation повторяет только idempotent DB-компенсацию, не второй API refund.

## Admin и аудит

- `GET /api/v1/admin/payment-reconciliation` — refunds, issues и последний run для support/admin.
- `POST /api/v1/admin/payments/{order_id}/refund` — admin-only durable request.
- `POST /api/v1/admin/payment-refunds/{refund_id}/retry` — admin-only retry/recovery.

Каждая запись требует безопасные `reason`, `reference`, UUID `Idempotency-Key`, confirmation в UI и
append-only audit. Charge ID, invoice payload и raw gateway error не входят в audit response.

## Метрики и alerts

- `kelbet_payment_refunds_total{status}`;
- `kelbet_payment_reconciliation_runs_total{outcome}`;
- `kelbet_payment_reconciliation_issues_total{kind}`;
- maintain-worker duration/outcome для refund processor и reconciliation.

Alert срабатывает на `needs_review`, failed reconciliation и критические discrepancy classes.
Labels используют только фиксированные состояния/классы и не содержат user/order/charge IDs.

## Incident and rollback runbook

1. Установить `PAYMENTS_ENABLED=false`, чтобы остановить новые invoices.
2. При неоднозначном refund установить `STARS_REFUNDS_ENABLED=false`; не повторять API вызов вручную.
3. Оставить `STARS_RECONCILIATION_ENABLED=true`, если Telegram API доступен, и дождаться outgoing
   observation.
4. В `/admin` проверить `external_refunded_at`, `ledger_transaction_id`, issue kind и audit action.
5. `refund_without_reverse_ledger` исправлять только через retry/idempotent service, не SQL balance.
6. `external_reversal` считать suspected chargeback/external refund, проверить Telegram/support и
   не обещать автоматический clawback при недостаточном wallet.
7. При недоступности Telegram выключить reconciliation, сохранить run `failed`, восстановить API и
   запустить bounded canary.

Удалять receipts/refunds/observations/issues во время rollback запрещено.

## Canary checklist

- [ ] Опубликованы реальные terms/refund URLs и зафиксирована version.
- [ ] Подтверждены seller identity, finance review и support contact.
- [ ] Назначены реальные admin/support membership; bootstrap allowlist отозван после проверки.
- [ ] В `STARS_CANARY_TELEGRAM_IDS` только тестовые аккаунты команды.
- [ ] В staging выполнены purchase, duplicate update, refund, timeout recovery и reconciliation.
- [ ] Проверены alerts, backup и rollback по этому runbook.
- [ ] Выполнена одна минимальная live-покупка и один возврат; ledger и Telegram balance сверены.
- [ ] Только после письменной фиксации evidence рассматривается расширение canary.

Репозиторий не отмечает эти пункты выполненными автоматически.

## Официальные источники

- Telegram Stars payments: <https://core.telegram.org/bots/payments-stars>
- `refundStarPayment`: <https://core.telegram.org/bots/api#refundstarpayment>
- `getStarTransactions`: <https://core.telegram.org/bots/api#getstartransactions>
- `StarTransaction`: <https://core.telegram.org/bots/api#startransaction>
- `TransactionPartnerUser`: <https://core.telegram.org/bots/api#transactionpartneruser>
