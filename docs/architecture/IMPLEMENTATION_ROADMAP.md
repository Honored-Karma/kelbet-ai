# KELBET AI — implementation roadmap

**Статус:** актуализировано по коду, миграциям и локальным тестам 10 августа 2026 года

**Назначение:** порядок доведения текущего v0.3-контура до безопасной платной beta

**Связанные документы:** [KELBET_FINAL_PRODUCT_PLAN.md](./KELBET_FINAL_PRODUCT_PLAN.md), [DATA_MODEL.md](./DATA_MODEL.md), [GENERATION_STATE_MACHINE.md](./GENERATION_STATE_MACHINE.md)

## Как читать статусы

- **Реализовано локально** — путь существует в коде и покрыт автоматическими тестами.
- **Частично реализовано** — есть рабочая основа, но отсутствует обязательная часть этапа.
- **Не реализовано** — в production-коде нет соответствующего сервиса, API или схемы данных.
- **Не подтверждено во внешней среде** — репозиторий не содержит проверяемого результата live/staging, юридического или финансового согласования.

Проверенная база на 10 августа 2026 года:

- миграционная цепочка: `0001_initial` → `0026_telegram_update_inbox`;
- backend: целевые контракты этапов 1–7, Ruff и mypy проходят локально;
- Mini App: tests, lint, TypeScript typecheck и production build проходят локально;
- CI проверяет Ruff, форматирование, полный mypy, цепочку Alembic upgrade/downgrade/re-upgrade, pytest, OpenAPI drift, а для Mini App — typecheck, tests, production build и lint; OpenAPI baseline, deployment manifests и локальные UI evidence-артефакты существуют;
- upgrade/downgrade миграций проверяется на отдельной локальной test DB; реальные provider/payment keys, live canary и юридические согласования не подтверждались.

`DATA_MODEL.md` синхронизирован с additive-цепочкой до `0026_telegram_update_inbox`.

## Фактический срез

| Направление | Фактический статус |
|---|---|
| Observability | Технический контур реализован: общий bootstrap API/bot/worker, privacy-first Sentry, bounded Prometheus backend, защищённый `/metrics`, instrumentation generation/provider/wallet/payment/stuck/worker, чистый liveness, строгий readiness, alerts и runbook. Внешние Sentry/Prometheus проекты, staging ingestion/scrape и alert drill не подтверждены; flags остаются выключенными. |
| Admin/operator | Технический minimum реализован: server-only `/api/v1/admin`, RBAC `support`/`admin`, env bootstrap, append-only audit, ledger-backed grant/generation refund, block/unblock, catalog/flag/payment SKU controls и внутренний `/admin`. Контур выключен по умолчанию; production bootstrap/smoke test не подтверждены. |
| Moderation/consent | Локальный technical minimum реализован: versioned privacy-safe decisions, RU/KK/EN baseline, optional official text adapter, pre-debit checks, photo-rights consent и support/admin review. Внешний report-mode canary не выполнен; semantic image/output moderation не заявляется. |
| Локальные шаблоны | Реализованы локально: server catalog из 6 image + 5 video RU/KK шаблонов, typed inputs, immutable quote/job snapshots, admin controls, history reuse и deterministic product-card/toi compositor с лицензированным Noto Sans. Client arrays остались только явным mock/dev fallback. |
| Telegram Stars | Технический контур реализован локально: XTR invoice, durable receipt/ledger, durable normalized update inbox с retry/recovery, operator-only recoverable refunds, reverse ledger, `getStarTransactions` reconciliation, refund/chargeback/dispute classification, limits, admin diagnostics, alerts и runbook. Все rollout-флаги выключены; legal/finance/support и Telegram live canary не подтверждены. |
| Stars subscriptions | Backend, API, bot handlers, Telegram-native recurring charge processing, expiration worker и idempotent period grants реализованы миграциями `0023`–`0024`. `SUBSCRIPTIONS_ENABLED=false`; Mini App checkout/status/cancel UI, deployment runbook и live canary отсутствуют. Включение запрещено до прохождения общего payment gate. |
| Второй image-provider | Реализован локально для generation/edit: Google Gemini native image adapter, обезличенные contract fixtures, immutable routing snapshot и общий transient-only cost-bounded fallback. Upscale честно не маршрутизируется в Google. `google_image` и `image_fallback` выключены; реальный provider canary не выполнялся. |
| Referral | MVP реализован локально: immutable new-user attribution, reconciliation-confirmed first purchase, ledger-backed reward states, limits/review, `/invite`, Mini App RU/KK, read-only admin и bounded metrics. `referrals=false`; production payment gate и live canary не подтверждены. |
| Generation reliability и новые video routes | Добавлены recovery для orphaned reservations/stuck jobs, открытый generation ledger/passport API, выбор video-моделей, durable Veo extended workflow и отдельный Veo consistency SKU. Новые Veo flags выключены; live provider canary и cost reconciliation не подтверждены. Неизвестное имя provider теперь fail-closed и не подменяется mock-результатом. |

## Обязательный dependency order

```text
1. observability
   ↓
2. admin auth + audit + operator minimum
   ↓
3. moderation + consent
   ↓
4. server-backed local templates + compositor minimum
   ↓
5. Telegram Stars production gates
   ↓
6. second image-provider + bounded fallback
   ↓
7. referral MVP
```

Этапы можно исследовать заранее, но production rollout следующего этапа не должен обходить gate предыдущего. В особенности referral не получает источник истины о первой покупке до завершения payment reconciliation.

---

## 1. Observability

| Обязательный пункт | Решение |
|---|---|
| 1. Фактический статус | **Реализовано в коде, production gate не пройден.** API, bot и worker используют общий идемпотентный bootstrap; Sentry opt-in с deny-first `before_send`; Prometheus backend имеет фиксированный каталог и bounded labels; `/metrics` opt-in и bearer-protected; instrumentation покрывает generation/provider/wallet/payment/stuck/worker. HTTP correlation UUID сохраняется в job и восстанавливается worker, bot получает correlation context на update. `/health` — чистый liveness, `/api/v1/ready` строго проверяет обязательные БД/Redis. Добавлены alerts, dashboard queries и incident runbook. Не подтверждены внешние проекты/DSN, scrape/ingestion, staging redaction event и alert drill. |
| 2. Точки расширения | `packages/kelbet/observability`, `CorrelationIdMiddleware`, `generation_jobs.correlation_id`, provider/service log sites, API lifespan, bot/worker startup, `/health`, `/api/v1/ready`, `Metrics` protocol и `set_metrics()`. |
| 3. Недостающая функциональность | Для закрытия production gate остались только внешняя настройка Sentry/Prometheus, scrape всех deployable registries, staging redaction/ingestion check, доставка alerts/on-call recipients и incident drill. Отдельный application observability service не требуется. |
| 4. Зависимости | Первый этап. Его безопасные error codes, audit correlation и метрики нужны всем последующим этапам. |
| 5. Миграции и внешние интеграции | Обязательной DB-миграции нет. Нужны аккуратно добавленные SDK dependencies, Sentry project/DSN и выбранный Prometheus-compatible collector/scraper. Наличие внешних проектов и ingestion endpoint пока не подтверждено. |
| 6. Feature flags/config | Планируемые env gates: `SENTRY_ENABLED=false`, `METRICS_ENABLED=false`, `METRICS_ENDPOINT_ENABLED=false`; DSN, environment, release и sampling задаются отдельно. `/metrics` разрешать только через private network или отдельный secret/auth dependency. |
| 7. Риски и rollback | Главные риски: утечка prompt/initData/token/file/provider response, высокая cardinality, публичный `/metrics`, деградация startup из-за telemetry. Rollback: выключить Sentry/export/endpoint независимо, вернуть `NoopMetrics`; приложение продолжает работать. |
| 8. Definition of Done | Все три процесса используют одну идемпотентную инициализацию; bot/API/worker errors попадают в настроенный backend без запрещённых данных; основные метрики экспортируются с bounded labels; liveness не зависит от БД/Redis, readiness честно отражает обязательные зависимости; dashboards/alerts/runbook проверены на staging. |
| 9. Обязательные тесты | Disabled config; повторная инициализация; redaction event/exception/breadcrumb/header/URL; отсутствие PII и высококардинальных labels; экспорт каждой основной метрики; `/metrics` недоступен без допуска; liveness при падении БД; readiness 503 при обязательной зависимости; correlation ID через HTTP → job → worker log/error. |
| 10. Порядок внутри этапа | 1) единая конфигурация; 2) усиление redaction; 3) bot/API/worker bootstrap; 4) Prometheus backend и instrumentation; 5) защищённый endpoint; 6) liveness/readiness; 7) Sentry; 8) dashboards/alerts/runbook; 9) staging drill. |

---

## 2. Admin auth, audit и operator minimum

| Обязательный пункт | Решение |
|---|---|
| 1. Фактический статус | **Реализован локально, production gate не пройден.** `/api/v1/admin` повторно проверяет opaque Telegram session и server-side роль; `/admin` — отдельный внутренний route. Migration `0012` добавляет membership, фактический user block и append-only audit с DB trigger. Read-only support отделён от admin writes. Grant переиспользует `grant_credits()`/`WalletService`; generation refund возвращает только внутренние credits и не вызывает Telegram Stars refund. |
| 2. Точки расширения | `OperatorContext`/admin dependencies, `AdminService` и `AdminRepository`; `operator_memberships`/`audit_events`; Telegram env bootstrap; user/wallet/generation/payment/catalog repositories; capability-gated `/admin`; correlation middleware и operator runbook. |
| 3. Недостающая функциональность | Для закрытия production gate нужны только внешний bootstrap/staging smoke test, назначение реальных membership, отзыв bootstrap allowlist и проверка доступа оператора. Moderation queue, Stars refunds/reconciliation и provider health намеренно остаются следующими отдельными этапами. Прямое редактирование balance отсутствует и запрещено. |
| 4. Зависимости | Требует observability для correlation/error/alerts. Даёт обязательную operator/audit основу moderation, payment refunds/reconciliation, provider kill switch и referral review. |
| 5. Миграции и внешние интеграции | Additive `0012_admin_operator_audit`: `operator_memberships`, `audit_events`, user block columns, constraints/indexes и trigger UPDATE/DELETE denial. Вся цепочка upgrade/downgrade проверена на отдельной test DB. Bootstrap IDs задаются только в server env; внешняя identity-система не нужна. |
| 6. Feature flags/config | Реализованы `ADMIN_ENABLED=false`, `ADMIN_BOOTSTRAP_TELEGRAM_IDS` и bounded admin rate limit. Скрытый URL не считается защитой. До реального bootstrap и smoke test флаг остаётся выключенным. |
| 7. Риски и rollback | Replay защищён UUID action ID + canonical request hash + transaction advisory lock; bearer-only session не использует cross-site cookie; audit DTO deny-list исключает prompt/secrets/raw provider/payment identifiers. Rollback: `ADMIN_ENABLED=false`, отзыв session/membership/bootstrap; audit, ledger и block state не удалять. |
| 8. Definition of Done | **Технически выполнено локально:** обычный user получает 403; support/admin разделены; повтор и concurrency не удваивают balance/refund; mutation содержит operator/reason/reference/correlation и safe before/after; audit append-only; block запрещает новые платные операции; user/payment/provider диагностика доступна без DB/terminal. Внешний staging access smoke test остаётся production gate. |
| 9. Обязательные тесты | Реализованы user 403, support/admin matrix, bootstrap, action replay/conflict, ORM append-only guard и DB migration trigger, audit privacy, повтор/concurrent grants, ledger refund, block enforcement, catalog/flag/payment SKU authorization, payments view и `/admin` navigation/capability tests. |
| 10. Порядок внутри этапа | 1) migration/RBAC/block; 2) server dependencies/bootstrap; 3) append-only audit/action replay; 4) read-only inspectors; 5) ledger-backed grant/refund; 6) block/catalog/flag/SKU writes; 7) `/admin`; 8) concurrency/security/frontend checks; 9) внешний staged enablement. |

---

## 3. Moderation, anti-abuse и consent

| Обязательный пункт | Решение |
|---|---|
| 1. Фактический статус | **Реализован локальный technical minimum; production canary не выполнен.** Есть provider-independent `ModerationService`/protocol, versioned privacy-safe decisions, `off/report/block`, RU/KK/EN phrase+obfuscation baseline, optional official OpenAI text adapter, pre-reserve integration для generation/chat/prompt assistant, versioned photo-rights consent и `/admin` review queue. Image content moderation отсутствует и явно не заявляется. |
| 2. Точки расширения | `ModerationProvider`, normalized provider result/error, `ModerationRepository`, decision/consent tables, config endpoint, generation binding, admin metadata queue/audit, bounded metrics и RU/KK support route. |
| 3. Недостающая функциональность | До production: real report-mode false-positive review, privacy/region/DPA decision для внешнего provider, staging smoke test и controlled block-mode canary. Semantic/image classifier, output media moderation и consent revocation workflow намеренно не заявлены как реализованные. |
| 4. Зависимости | После observability и admin/audit. Должен завершиться до server templates, payment public rollout и второго provider, чтобы шаблоны/fallback не обходили policy. |
| 5. Миграции и внешние интеграции | `0013_moderation_consent` добавляет `moderation_decisions` и `user_consents` с constraints/indexes. Внешний OpenAI adapter использует официальный text-only `POST /v1/moderations`; ключ отсутствует по умолчанию, real call в тестах не выполняется, DPA/region review остаётся внешним gate. |
| 6. Feature flags/config | `MODERATION_MODE=report` по умолчанию; `block`/`off` явные. External provider `none/openai`, documented `open/closed` failure policy, bounded request/repeat thresholds, policy/consent versions. Consent проверяется сервером; client checkbox сам по себе не является записью. |
| 7. Риски и rollback | False positives/negatives, обход обфускацией, хранение чувствительного контента, provider outage, fallback bypass. Rollback: `block` → `report` → `off`; решения сохраняются для расследования; платные операции при fail-closed не резервируют деньги. |
| 8. Definition of Done | **Локальный technical DoD выполнен:** block до reserve/enqueue, wallet/queue неизменны; decisions versioned/privacy-safe; image edit/image-to-video требуют current consent; support читает safe queue, admin review идемпотентен/audited; RU/KK и `/support`; bounded counter. Report-mode staging/canary остаётся production gate. |
| 9. Обязательные тесты | Реализованы allow/report/block, RU/KK и obfuscation, durable no-reserve block/replay, raw absence, documented external contract/fail-open/fail-closed, missing/accepted versioned consent, support/admin queue/audit, config honesty и frontend consent/capability contracts. Semantic/image/output moderation и consent revoke тесты не заявлены: соответствующих функций нет. |
| 10. Порядок внутри этапа | 1–8 реализованы: taxonomy → migration → service/protocol → pre-reserve integration → consent → admin review/audit → official optional text adapter → web integration/tests/docs. Следующее: 9) report-mode staging canary; 10) только после review — controlled block mode. |

---

## 4. Доведение локальных шаблонов

| Обязательный пункт | Решение |
|---|---|
| 1. Фактический статус | **Реализован локально; внешний canary не выполнен.** Migration `0014` добавляет canonical catalog и immutable quote/job snapshots. `/catalog/templates`, quote/create/draft/history, admin enable/order и bounded metrics используют один server contract. Product-card PNG и toi MP4 получают контролируемый deterministic text layer с Noto Sans RU/KK glyph coverage; provider output не выдаётся как готовый при сбое compositor. |
| 2. Точки расширения | `GenerationTemplateRepository/Service`, canonical seed catalog, quote/create request hash, immutable snapshot triggers, asset/output pipeline, deterministic compositor, admin catalog/audit, history/draft reuse, RU/KK runtime и server-driven frontend forms. |
| 3. Недостающая функциональность | До production остаются только staging visual QA на реальных provider outputs, подтверждение layout на целевых устройствах и controlled canary. Catalog/version/input/compatibility/compositor technical minimum закрыт; arbitrary/disabled slug и несовместимая модель отклоняются сервером. |
| 4. Зависимости | Нужны admin catalog/audit и moderation/consent; observability — для template success/cost. Payment gate не блокирует разработку, но цены остаются server quote. |
| 5. Миграции и внешние интеграции | `0014_generation_templates`: versioned/localized/form/prompt/routing/enabled catalog; nullable references и immutable JSON snapshots для старых/новых quote/jobs. Noto Sans Variable + SIL OFL vendored в package; Pillow/imageio-ffmpeg compositor не требует внешнего API. |
| 6. Feature flags/config | `SERVER_TEMPLATES_ENABLED=true`, `TEMPLATE_COMPOSITOR_ENABLED=true` для локального server-owned path; per-template `enabled` и model feature flags остаются независимыми. Client catalog разрешён только в явном mock/dev режиме. |
| 7. Риски и rollback | Изменение шаблона ломает repeat/history; выключенный template исчезает у старых jobs; несовместимые model params; некорректные KK glyphs/line wrapping; двойной client/server prompt. Rollback: отключить новые template versions/compositor, продолжать читать snapshots и показывать старые поколения. |
| 8. Definition of Done | **Локальный technical DoD выполнен:** API/Mini App parity, server-validated ID/version/inputs/snapshot, disabled/unknown/compatibility guards, old NULL history, reuse, admin audit, RU/KK glyph check, real PNG/MP4 compositor fixtures и bounded analytics. Внешний provider-output visual canary остаётся gate. |
| 9. Обязательные тесты | Реализованы catalog/parity, client/API schema, valid/unknown/disabled, model/asset/input/version compatibility, snapshot immutability, draft/reuse/old NULL, idempotency conflict, NFC RU/KK, support-read/admin-write, font glyphs и реальные PNG/FFmpeg MP4 compositor outputs. |
| 10. Порядок внутри этапа | 1–9 выполнены: schema/seeds → DB/API → snapshots → client parity → admin → history/reuse → product-card/toi compositor → RU/KK/font QA → tests/docs. Остался только внешний staging canary; client fallback уже ограничен mock/dev. |

---

## 5. Production gates Telegram Stars

| Обязательный пункт | Решение |
|---|---|
| 1. Фактический статус | **Технически реализовано локально, rollout выключен.** `0011` создаёт products/orders/receipts, `0015` — refund state machine и reconciliation, `0022` усиливает checkout/recovery, `0026` добавляет normalized durable update intake/replay. Bot/Mini App/API поддерживают XTR invoice, terms acceptance, pre-checkout, durable receipt, idempotent ledger credit и history. Admin-only refund восстанавливается после неизвестного внешнего результата, reverse ledger идемпотентен; reconciliation классифицирует missing/duplicate/reversal cases без raw Telegram payload. |
| 2. Точки расширения | `PaymentService`, `PaymentRefundService`, `reconcile_star_transactions`, gateway `refund_star_payment`/`get_star_transactions`, worker recovery jobs, `WalletService`, charge-ID uniqueness, admin/audit, metrics/alerts, `/paysupport` и payment snapshots. |
| 3. Недостающая функциональность | Только внешние gates: реальные Telegram test/live вызовы и canary, опубликованные legal/refund/privacy документы, finance/seller/support подтверждение и operational drill. |
| 4. Зависимости | Observability + admin/audit обязательны. Moderation/consent и templates должны быть готовы до публичной платной beta по зафиксированному порядку. Referral ждёт завершённой reconciliation и confirmed non-reversed first purchase. |
| 5. Миграции и внешние интеграции | Additive `0015_stars_refunds`: refund/reconciliation state; `0022_payment_hardening`: checkout ownership и coverage cursors; `0026_telegram_update_inbox`: минимальный replay payload, unique update ID, claim/retry state и due index. Gateway основан на текущем Bot API surface; fake gateway покрывает recovery без внешних вызовов. |
| 6. Feature flags/config | Реализованы независимые `PAYMENTS_ENABLED=false`, `STARS_REFUNDS_ENABLED=false`, `STARS_RECONCILIATION_ENABLED=false`, `STARS_CANARY_TELEGRAM_IDS` и bounded refund/inbox retry limits. Включение требует опубликованных URL/version, seller identity, finance review и support contact. |
| 7. Риски и rollback | Telegram API и DB не образуют одну atomic transaction; timeout после внешнего refund; повтор/concurrent refunds; reverse ledger без внешнего refund; chargeback после траты кредитов. Rollback: выключить новые invoices/refund initiation, продолжить reconciliation/read-only support, переводить неоднозначные случаи в `needs_review`, не удалять receipts/audit. |
| 8. Definition of Done | **Локальный technical DoD выполнен:** повторы/concurrency не удваивают credit/refund; сбой Telegram↔ledger восстанавливается; reconciliation находит заданные классы; operator action audited; alerts/runbook/rollback описаны. Production gate остаётся **не пройден**, пока нет legal/finance/seller/support evidence и успешного live canary. |
| 9. Обязательные тесты | Реализованы order/pre-checkout/receipt idempotency, durable update persistence-before-handler/dedup/stale recovery, refund state/replay/concurrency, external-success+DB-failure recovery, timeout/unknown result, reverse ledger, reconciliation fixtures, missing/duplicate/reversal/chargeback, limits/review, audit/redaction, disabled flags и fake gateway. |
| 10. Порядок внутри этапа | 1–8 выполнены локально: official surface → migration/state machines → admin request → external recovery → reverse ledger → reconciliation/issues → limits/review → metrics/admin/runbook. Остались 9) Telegram test environment; 10) legal/finance/support evidence + small live canary. |

---

## 6. Второй image-provider и fallback

| Обязательный пункт | Решение |
|---|---|
| 1. Фактический статус | **Реализовано локально для image generation/edit; canary не выполнен.** Текущий Google Gemini native image adapter использует Interactions API и модель `gemini-3.1-flash-image`; factory/routing поддерживает синхронную генерацию и edit. Upscale не заявлен как поддерживаемый и не получает fallback. Generic runner сохраняет primary/fallback attempts, usage, safe error class и финальный route. |
| 2. Точки расширения | Provider protocol/factory; Runway contract tests/fixtures; catalog capabilities/input requirements/pricing; `generation_attempts`, `provider_usage`; existing video fallback classification/cost ceiling; worker polling/idempotency; `runway_media` kill switch; admin provider health из этапа 2. |
| 3. Недостающая функциональность | Только внешний shadow/canary и quality/cost validation на реальном Google account/region. Capability matrix намеренно ограничена generation/edit; deterministic upscale отсутствует в выбранном API и остаётся primary-only. |
| 4. Зависимости | Выполняется после observability, admin kill switch, moderation policy, server templates и payment gates. Quote/user price остаётся неизменным независимо от provider route. |
| 5. Миграции и внешние интеграции | `0016_image_fallback` добавляет immutable `generation_jobs.routing_snapshot`, seed `google_image=false`/`image_fallback=false` и catalog fallback metadata. Выбор зафиксирован в ADR-013: прежний Imagen API deprecated, поэтому используется актуальный Gemini native image endpoint/model; region/pricing/capabilities сверены с официальной документацией 1 августа 2026. |
| 6. Feature flags/config | `google_image` и `image_fallback` выключены по умолчанию; оба обязательны вместе с catalog gate, canary allowlist и cost ceiling. Existing `runway_media` остаётся kill switch primary route. |
| 7. Риски и rollback | Неверный/устаревший model ID, region block, quality/capability mismatch, рост cost, moderation bypass, retry loop, двойной capture/release. Rollback: отключить fallback/new provider через flags/catalog, не менять уже подтверждённую цену и завершать/recover уже созданные jobs по snapshot. |
| 8. Definition of Done | **Локальный technical DoD выполнен:** adapter основан на official spec/fixtures; coverage честная; fallback только transient и в cost ceiling; attempts/final route/safe code сохранены; ровно один capture/release; prompts/images/raw responses не логируются; kill switch покрыт. Остался реальный canary. |
| 9. Обязательные тесты | Реализованы primary success, transient→fallback, запреты для permanent/moderation/invalid/unsupported/account, missing key/source validation, cost ceiling, fallback failure/replay, bounded attempts/no loop, immutable route/price, capture/release once, redaction/cardinality и kill switch. |
| 10. Порядок внутри этапа | 1–8 выполнены: official research → ADR/capabilities → routing snapshot → adapter/fixtures → generic fallback → catalog/flags → metrics/admin health → tests. Остались 9) shadow/canary; 10) controlled rollout. |

### 6.1 OpenAI GPT Image 2 route

`0018_openai_image_provider` adds a synchronous OpenAI adapter and two conservative generation
catalog candidates (`low` and `medium`). `openai_image=false` is the default, so this is a local
technical route rather than a production enablement. The adapter has idempotency, strict input and
output validation, safe error classification, and no raw provider-response persistence. A live
canary, account/region verification, moderation review, observed-cost reconciliation, and
allowlisted rollout remain mandatory; see `OPENAI_IMAGE_PROVIDER_RUNBOOK.md`.

---

## 7. Referral MVP

| Обязательный пункт | Решение |
|---|---|
| 1. Фактический статус | **Реализовано локально, rollout выключен.** `/start ref_<code>` сохраняет first touch через выбор языка; только созданный в этой регистрации user получает immutable attribution. Reconciliation-confirmed первая покупка переводит reward из `pending` в `eligible`; worker после waiting period начисляет inviter/invitee через `WalletService`. `/invite`, Mini App и read-only admin показывают server-owned RU/KK данные; `INVITE_COMING_SOON` остаётся только disabled-state сообщением. |
| 2. Точки расширения | `/start` registration/idempotency; Telegram deep links; user/wallet ledger; payment order/receipt/reconciliation; bot navigation/i18n; Mini App routing; admin/audit; feature flags and metrics. |
| 3. Недостающая функциональность | Для production остаются только completed payment live gate, allowlisted referral canary, operational fraud review и проверка опубликованных RU/KK условий. Автоматического отрицательного clawback намеренно нет. |
| 4. Зависимости | Последний этап. Требует production payment gate и reconciliation как source of truth, admin/audit для review, observability для funnel, moderation/anti-abuse baseline. |
| 5. Миграции и внешние интеграции | Additive `0017_referral_mvp`: `referral_codes`, `referral_attributions`, `referral_rewards`, uniqueness/check/FK/due indexes и DB trigger, запрещающий UPDATE/DELETE attribution. Telegram deep links используют существующий bot; отдельный сервис не нужен. |
| 6. Feature flags/config | DB flag `referrals=false` до canary; server-configured bot username, bonuses `5/2`, minimum `50 Stars`, waiting `72h`, daily cap `20` и suspicious-attribution threshold `50`. Referral не включается автоматически вместе с payments. |
| 7. Риски и rollback | Self/multi-account abuse, concurrent registration, duplicate payment updates, refund/chargeback race, negative wallet during clawback, потеря code между onboarding steps. Rollback: выключить new attribution/reward; сохранить immutable rows; pending отменять, credited сомнительные rewards переводить в review без автоматического отрицательного wallet. |
| 8. Definition of Done | **Локальный technical DoD выполнен:** only-new immutable inviter; self/unknown/repeat safe; reward один раз после reconciled first eligible purchase/wait; refund отменяет pending, credited reversal идёт в `needs_review` без clawback; audit/metrics bounded; RU/KK bot/Mini App работают; flag off. |
| 9. Обязательные тесты | Реализованы valid/existing/self/unknown/repeat, deep-link parser/language retention, concurrent registration, first/repeat purchase, waiting/minimum/daily limits, refund-before-reward, chargeback-after-credit review, ledger/worker idempotency, RU/KK, admin auth/audit и flag off. |
| 10. Порядок внутри этапа | 1–9 выполнены локально: safe default economics → migration/states → deep-link attribution → reconciliation hook → reward worker/ledger → limits/review → bot → Mini App/admin → metrics/tests. Остался 10) allowlisted canary после payment live gate. |

---

## Внешние данные и проверки для production gates

1. **Observability:** выбрать Sentry project и Prometheus-compatible collector/hosting, определить private access к `/metrics`, retention и on-call recipients.
2. **Admin:** safe defaults уже приняты (`support` read-only, `admin` writes, grant 1–1 000 000, generation refund только captured/succeeded). Перед staging нужен только реальный bootstrap Telegram ID и последующий smoke test; до него `ADMIN_ENABLED=false`.
3. **Moderation/consent:** утвердить policy scope, режим fail-open/fail-closed для outage, нужен ли внешний provider, версии RU/KK consent/privacy/appeal text и правила для лиц/голоса.
4. **Templates:** утвердить канонический первый server catalog, поля product-card/toi-invite compositor, шрифт/лицензию и процесс публикации template versions.
5. **Telegram Stars:** предоставить опубликованные terms/refund/privacy URLs и version, seller identity, finance approval экономики Stars, support contact и решение о live-canary лимитах. До этого `PAYMENTS_ENABLED` остаётся `false`.
6. **Second image-provider:** после проверки official docs выбрать provider/region, обязательные capabilities (generation/edit/upscale), quality threshold и cost ceilings.
7. **Referral:** локальные MVP defaults зафиксированы в server config; до включения нужны completed payment live gate, allowlisted canary, operational fraud-review owner и опубликованные RU/KK условия.

Подтверждение владельца не блокирует локальную реализацию. Юридические, финансовые, provider-account и live production проверки считаются незавершёнными, пока нет проверяемого внешнего evidence; соответствующие flags остаются выключенными.
