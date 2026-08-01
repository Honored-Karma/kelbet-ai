# Server templates and controlled compositor runbook

## Что реализовано

Migration `0014_generation_templates` добавляет единый каталог из 6 image- и 5 video-шаблонов,
а также неизменяемые template-снимки в quote и generation job. Production-клиент получает каталог
через `GET /api/v1/catalog/templates`; локальные массивы допустимы только как явно обозначенный
mock/dev fallback.

Quote и create обязаны передавать одинаковые `template_id` и `template_inputs`. Сервер проверяет
активность шаблона, modality, aspect ratio, duration, число assets, обязательные поля, длину,
control characters и неизвестные ключи. Цена по-прежнему берётся только из server quote.

## Controlled compositor

- `marketplace-product` после image provider накладывает headline, body, price и contact в
  фиксированный слой и сохраняет PNG без исходных metadata.
- `toi` после video provider накладывает headline, body, date и contact в фиксированный слой,
  перекодирует MP4 в H.264/yuv420p и сохраняет fast-start output.
- Клиент не может передать font, координаты, цвет, URL или markup.
- Ошибка compositor завершает job как `failed`, освобождает reservation и никогда не выдаёт
  provider output без обязательного контролируемого текста.

Шрифт `packages/kelbet/assets/fonts/NotoSans-Variable.ttf` взят из официального каталога Google
Fonts и распространяется вместе с `OFL.txt` по SIL Open Font License 1.1. SHA-256 закреплённой
копии: `BFB7BB691513F12E734DC346C03A03F784912432D7E3FA8E56EFCF906FE86B3D`. Обновлять файл можно
только вместе с проверкой лицензии, checksum и RU/KK glyph/layout tests.

## Deploy

1. Применить `alembic upgrade head` до запуска новой версии API/worker.
2. Оставить `SERVER_TEMPLATES_ENABLED=true` и `TEMPLATE_COMPOSITOR_ENABLED=true`.
3. Проверить RU и KK ответы каталога, quote/create parity, product-card PNG и toi MP4.
4. В admin убедиться, что support видит catalog, а admin может менять только `enabled` и
   `display_order`; каждое изменение требует reason/reference и создаёт audit event.
5. Следить за `template.selected`, `template.started`, `template.terminal` и `template.reused`.

## Безопасный rollback

Сначала установить `SERVER_TEMPLATES_ENABLED=false`, чтобы остановить новые template quotes. Не
выключать compositor, пока существуют активные template jobs: иначе обязательный текстовый слой
будет пропущен. После завершения/остановки активных jobs можно установить
`TEMPLATE_COMPOSITOR_ENABLED=false` и откатить приложение. Не удалять catalog rows и не изменять
снимки старых quote/jobs.

## Gate перед production

Локальные тесты и FFmpeg smoke test не подтверждают production-like среду. Перед rollout нужны
миграционный smoke test на staging, проверка наличия FFmpeg в worker image, визуальная RU/KK QA на
типовых разрешениях и canary с реальным image/video provider. До этих проверок внешний rollout
считается неподтверждённым.
