# KELBET AI — Telegram Stars Payments

Status: Stage 5 payment vertical slice  
Updated: 30 July 2026

## Product contract

KELBET sells digital AI credits inside Telegram exclusively for Telegram Stars
with currency `XTR`. Payments are disabled by default and cannot be enabled
without all three production prerequisites:

- `PAYMENTS_ENABLED=true`;
- a public `PAYMENT_TERMS_URL`;
- a configured `SUPPORT_USERNAME` for `/paysupport`.

The initial packages are editable database products:

| Product | Credits | Stars |
|---|---:|---:|
| Starter | 100 | 100 |
| Creator | 300 | 270 |
| Studio | 800 | 640 |

These are launch-draft values. Before enabling production payments, finance must
validate Telegram's actual net Star proceeds, provider costs and Kazakhstan tax
requirements. Prices are never calculated by the Mini App.

## Safe payment flow

```text
product → accept terms → create order + price snapshot → XTR invoice
       → pre_checkout validation → successful_payment
       → durable receipt → idempotent ledger credit → paid order
```

The server validates the buyer Telegram ID, currency, exact amount, order state
and expiry during pre-checkout. Answering pre-checkout does not deliver credits.
Credits are added only after the bot receives `successful_payment`.

Every Telegram charge ID has:

- a unique `payment_receipts` row;
- one ledger idempotency key `stars:<telegram_payment_charge_id>`;
- at most one linked order and one credit transaction.

A repeated update returns the already recorded result and cannot add credits
again. An unknown payload, wrong buyer, currency or amount is stored as a
rejected receipt for `/paysupport`, while the wallet remains unchanged.

## User surfaces

- Mini App `/plans`: localized packages, mandatory terms checkbox, Telegram
  `openInvoice`, and purchase history;
- bot `/buy`: localized package invoice flow;
- bot `/terms`: current purchase and refund terms;
- bot `/paysupport`: payment support route;
- API: products, idempotent order creation and authenticated history.

## Environment

```env
PAYMENTS_ENABLED=false
PAYMENT_TERMS_URL=https://kelbet.ai/terms
PAYMENT_TERMS_VERSION=2026-07-30
PAYMENT_ORDER_TTL_MINUTES=30
SUPPORT_USERNAME=kelbet_support
```

Changing product rows affects only new orders. Every order keeps its credits,
Stars amount, localization and terms version in an immutable purchase snapshot.

## Remaining production gates

1. Legal review of RU/KK terms, refund policy and Kazakhstan seller identity.
2. Finance review of package economics and Star proceeds.
3. Operator-only `refundStarPayment` flow with reverse ledger transaction.
4. `getStarTransactions` reconciliation and chargeback/dispute ingestion.
5. Telegram test-environment run followed by a small live canary.
6. Backups and alerting for rejected receipts and paid orders without ledger IDs.

## Official references

- Telegram digital goods payments: <https://core.telegram.org/bots/payments-stars>
- Telegram Bot API payment methods: <https://core.telegram.org/bots/api>
