# KELBET AI — operator runbook

## Назначение и границы

`/admin` — внутренний интерфейс поддержки поверх `/api/v1/admin`. Он использует ту же
проверенную Telegram Mini App session, но роль всегда повторно определяется сервером.
Знание URL не даёт доступа. Контур не выполняет Telegram Stars refund. Он содержит
metadata-only moderation queue: сырой prompt и provider response в неё не попадают.

Роли:

- `support` — поиск и просмотр профиля, wallet/ledger, generations, payment orders/receipts,
  controls, moderation queue и append-only audit;
- `admin` — всё выше плюс ledger-backed credit grant, refund стоимости завершённой generation,
  block/unblock, moderation review и enable/disable catalog/payment SKU или существующего
  feature flag.

Прямое редактирование `wallets.balance` запрещено. Финансовые операции выполняются только
через `WalletService` и immutable `credit_transactions`.

## Безопасное включение

1. Применить Alembic migration `0012_admin_operator_audit`.
2. Оставить `ADMIN_ENABLED=false`, войти нужным Telegram-пользователем в Mini App, чтобы запись
   пользователя уже существовала.
3. Задать `ADMIN_BOOTSTRAP_TELEGRAM_IDS` как список положительных Telegram ID через sealed
   variables платформы. Не хранить production IDs в Git.
4. Установить `ADMIN_ENABLED=true`, выполнить redeploy API и проверить `GET /api/v1/admin/me`.
5. Проверить: обычная сессия получает 403; bootstrap admin видит `role=admin`; mutation без
   `Idempotency-Key` UUID отклоняется; audit получает correlation ID.
6. После создания постоянных membership записей удалить временные bootstrap IDs и redeploy.

`ADMIN_ENABLED=false` полностью закрывает API/UI независимо от bootstrap списка.

## Правила операторских действий

- Каждая mutation требует новый UUID в `Idempotency-Key`.
- Повтор того же UUID и того же тела возвращает первоначальный результат без второго изменения.
- Тот же UUID с другим телом возвращает conflict.
- `reason` и `reference` — только безопасные коды длиной 3–64 символа: буквы, цифры,
  `. _ : -`. Не вставлять туда имя, телефон, prompt, invoice payload, токен или ответ provider.
- Credit grant требует положительную сумму до 1 000 000 и использует существующий
  `grant_credits()`/ledger path.
- Generation refund допустим только для `succeeded` generation с `captured` reservation.
  Он возвращает внутренние credits; Telegram Stars refund здесь отсутствует.
- Block запрещает новые платные generation/chat/prompt-assistant/payment-order операции.
  Повтор уже созданной идемпотентной generation/order остаётся доступен, а завершение ранее
  оплаченного receipt не блокируется.

## Audit и приватность

`audit_events` содержит operator, role, action, object, безопасные before/after, reason,
reference, UTC timestamp, correlation ID и request hash. Migration создаёт DB trigger,
запрещающий UPDATE/DELETE. Не удалять trigger и строки при rollback.

Admin DTO намеренно не отдают prompt, generation params, storage keys, provider raw response,
invoice payload, payment charge IDs, ledger meta или bearer/initData.

## Moderation queue

- Queue содержит только user/generation/asset UUID, SHA-256 входа, mode/outcome, policy
  version, bounded reason/error codes и provider/model name.
- `support` может читать open/reviewed queue, но не видит кнопок review и получает 403 на API.
- `admin` выбирает `confirmed_violation`, `false_positive` или `needs_escalation`; действие
  требует UUID `Idempotency-Key`, safe reason/reference и попадает в append-only audit.
- Review не блокирует пользователя навсегда и не меняет wallet. При необходимости account block
  выполняется отдельной осознанной admin-командой с собственной причиной.
- При спорном решении пользователь направляется на `/support`; оператор не просит прислать
  prompt, токен или исходный файл в reason/reference.

## Инцидент и rollback

При подозрении на компрометацию:

1. Немедленно установить `ADMIN_ENABLED=false` и redeploy API.
2. Удалить скомпрометированный Telegram ID из bootstrap списка и отозвать membership запись.
3. Отозвать активные auth sessions пользователя.
4. Сохранить `audit_events`, ledger и correlation IDs; не исправлять их задним числом.
5. Сверить credit transactions и generation reservations по объектам из audit.
6. Возвращать write-доступ только после ротации доступа и проверки повторов/concurrency.

Rollback кода выполняется без удаления `operator_memberships`, `audit_events` и user block state.
