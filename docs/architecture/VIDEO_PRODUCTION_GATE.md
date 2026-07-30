# KELBET AI — Video Production Gate

Status: ready for production-like staging  
Updated: 30 July 2026

Этот runbook закрывает последний технический gate Video MVP. Боевой запуск
разрешается только после подписанного Google callback, завершённой партии
минимум из 100 video jobs и успешной автоматической сверки.

## Completion transport

### Google Veo

Для Google используется статический webhook Gemini API:

- событие: `video.generated`;
- endpoint: `POST https://<api-host>/api/v1/webhooks/google`;
- подпись: Standard Webhooks по точному исходному телу запроса;
- replay window: 300 секунд;
- дедупликация: `(provider, webhook-id)`;
- callback только будит video worker и немедленно возвращает `2xx`;
- polling остаётся страховкой, если callback задержан или потерян.

Создание project-level webhook:

```bash
curl -X POST \
  "https://generativelanguage.googleapis.com/v1/webhooks" \
  -H "Content-Type: application/json" \
  -H "x-goog-api-key: $GOOGLE_API_KEY" \
  -d '{
    "name": "KELBET video completion",
    "uri": "https://<api-host>/api/v1/webhooks/google",
    "subscribed_events": ["video.generated"]
  }'
```

Google возвращает signing secret только один раз. Его необходимо сразу положить
в secret manager и передать API как:

```env
GOOGLE_WEBHOOK_SIGNING_SECRETS=whsec_<base64-secret>
GOOGLE_WEBHOOK_MAX_AGE_SECONDS=300
WEBHOOK_MAX_BODY_BYTES=65536
```

Секрет нельзя писать в Git, логи, Telegram или reconciliation-артефакт.

При ротации Google может оставить предыдущий secret рабочим на 24 часа. На этот
период API принимает оба секрета через запятую:

```env
GOOGLE_WEBHOOK_SIGNING_SECRETS=whsec_<old>,whsec_<new>
```

После grace period старый secret удаляется из secret manager и окружения.

### Runway

В актуальной официальной документации Runway completion webhook не описан.
Поэтому KELBET использует документированный `GET /v1/tasks/{id}`:

- базовый интервал не меньше 5 секунд;
- дополнительный jitter 0–2 секунды, стабильный для конкретной задачи;
- 30-минутный deadline;
- идемпотентная финализация;
- временная ошибка допускает только cost-bounded Google fallback.

Это намеренный гибридный контур, а не эмуляция неподтверждённого callback API.

## Environment gate

```env
RUNWAY_API_KEY=...
RUNWAY_POLL_INTERVAL_SECONDS=5
RUNWAY_POLL_JITTER_SECONDS=2

GOOGLE_API_KEY=...
GOOGLE_WEBHOOK_SIGNING_SECRETS=...

STORAGE_BACKEND=s3
S3_BUCKET=...
S3_ENDPOINT_URL=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

Перед партией проверить:

1. применены все миграции;
2. API и video worker используют одну production-like БД;
3. S3 bucket приватный, CORS и signed URL работают;
4. provider keys не являются mock/test ключами;
5. callback URL публичный, HTTPS и отвечает без редиректа;
6. alerting видит `dead_letter`, `timed_out`, webhook `401` и очередь старше SLA.

## Партия из 100 задач

Партия должна включать оба provider route, оба aspect ratio, длительности 4/8
секунд и хотя бы несколько photo-to-video запросов. Не включать в выборку старые
ручные тесты: используйте отдельное окно времени или staging database.

После того как все задачи получили terminal status:

```bash
python scripts/reconcile_video_batch.py \
  --hours 24 \
  --minimum-jobs 100 \
  --output artifacts/video-reconciliation.json
```

Команда завершится кодом `0` только при полном совпадении. Код `1` блокирует
релиз. `--allow-active` существует только для промежуточной диагностики и не
может использоваться как production gate.

Автоматическая сверка проверяет:

- минимум 100 выбранных задач и отсутствие active jobs;
- `finished_at` и отсутствие `next_poll_at` у terminal jobs;
- связь job → reservation и неизменность quote price;
- capture успешных задач и release/expire неуспешных;
- сумму, reason и idempotency key ledger capture;
- уникальность capture transaction;
- provider usage, положительную production cost и сохранённую user price;
- ровно одну успешную попытку и usage у успешной задачи;
- готовый приватный `video/*` output;
- отсутствие зависших jobs старше допустимого возраста.

JSON-отчёт содержит агрегаты по статусам и провайдерам, ожидаемые/captured/released
кредиты, provider cost и точные issue codes. В нём нет prompt, ключей или URL
пользовательских файлов.

## Решение о релизе

`GO`, только если одновременно:

- reconciliation завершён с `passed: true`;
- `selected_jobs >= 100` и `active_jobs == 0`;
- нет повторного списания или потерянного резерва;
- Google callback принят с валидной подписью, а повтор доставлен как duplicate;
- Runway polling не превышает provider rate limits;
- все реальные MP4 открываются после переноса в приватное хранилище.

При любом issue code релиз остаётся закрытым. Сначала устраняется причина,
создаётся новая чистая партия и только затем повторяется gate.

## Official references

- Google Gemini webhooks: <https://ai.google.dev/gemini-api/docs/webhooks>
- Standard Webhooks specification:
  <https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md>
- Runway SDK task polling: <https://docs.dev.runwayml.com/api-details/sdks/>
