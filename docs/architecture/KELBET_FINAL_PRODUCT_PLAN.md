# KELBET AI — мастер-план финального продукта

Статус: рабочий план разработки  
Дата: 30 июля 2026  
Фактические implementation-статусы актуализированы 1 августа 2026 года по коду,
миграциям и тестам; детальный порядок и gates вынесены в
[`IMPLEMENTATION_ROADMAP.md`](./IMPLEMENTATION_ROADMAP.md).
Горизонт: Казахстан → Центральная Азия  
Основной канал: Telegram Bot + Telegram Mini App

---

## 1. Видение

**KELBET AI — локальная AI-студия для креаторов, предпринимателей и обычных
пользователей Казахстана.**

Пользователь не должен разбираться в названиях моделей, API, промптах и тарифах
провайдеров. Он выбирает задачу, загружает материалы, видит точную стоимость,
получает готовый результат и может сразу повторить, изменить, скачать или
поделиться им.

Продукт должен ощущаться не как каталог нейросетей, а как удобный творческий
инструмент:

1. открыл Telegram;
2. выбрал, что нужно сделать;
3. загрузил фото или написал идею;
4. получил улучшенный промпт и понятные настройки;
5. увидел цену до запуска;
6. получил результат с уведомлением;
7. продолжил работу через «Повторить», «Изменить» или «Оживить».

### Позиционирование

> Лучший AI-инструмент для создания контента в Казахстане — на казахском и
> русском языках, прямо в Telegram.

### Что мы не строим

- не техническую панель со списком из десятков непонятных моделей;
- не дешёвую прокладку над одним API;
- не Telegram-меню из длинных цепочек кнопок;
- не безлимитный тариф с неконтролируемой себестоимостью;
- не универсальный AI-комбайн без главного пользовательского сценария.

---

## 2. Конкурентная стратегия

На 30 июля 2026 года `@VeoSeeBot | Neuroplace` показывает около 375 тысяч
пользователей в месяц. Neuroplace предлагает изображения, видео, текст, аудио,
аватары, подписки, кредиты и партнёрскую программу. Конкурировать только
количеством моделей поздно и дорого.

### Что берём как обязательный рыночный минимум

- изображения по тексту;
- редактирование изображений;
- text-to-video и image-to-video;
- несколько моделей разной цены и качества;
- история генераций;
- прозрачная кредитная система;
- пакеты и подписки;
- реферальная программа;
- сохранение исходников и результатов;
- единый аккаунт между ботом и Mini App.

### В чём KELBET должен быть лучше

| Направление | Преимущество KELBET |
|---|---|
| Локализация | Полноценные RU/KK, а не машинно переведённые подписи |
| Простота | Выбор по задаче, модель подбирается автоматически |
| Локальный контент | Шаблоны для Kaspi-магазинов, Instagram, TikTok, Наурыза, той, недвижимости, кафе и малого бизнеса |
| Цена | Стоимость показана до запуска; никаких неожиданных списаний |
| Надёжность | Автовозврат кредитов при технической ошибке |
| Поддержка | RU/KK-поддержка внутри Telegram с историей операции |
| Скорость | Fast/Quality режимы и автоматический fallback провайдера |
| Доверие | Понятная политика хранения фото, удаление данных и защита от deepfake-злоупотреблений |
| Удобство | «Повторить», «Сделать похожее», «Оживить фото», «Улучшить качество» в один шаг |
| Казахстан | Тенге в коммуникации, локальные примеры, локальное юрлицо и фискальные процессы |

### Главный продуктовый принцип

В обычном режиме пользователь выбирает **результат**, а не модель:

- «Создать изображение»;
- «Изменить фото»;
- «Оживить фото»;
- «Создать рекламный ролик»;
- «Сделать говорящий аватар»;
- «Улучшить качество»;
- «Написать текст».

Названия моделей доступны в режиме **Pro**.

---

## 3. Целевая аудитория

### P0 — креаторы и SMM-специалисты

Задачи:

- Reels/TikTok;
- обложки, сторис и рекламные креативы;
- оживление фотографий;
- product placement;
- быстрые варианты одного креатива;
- локализация RU ↔ KK.

Почему начнём с них: высокая частота использования, понятная ценность и
органическое распространение результатов.

### P1 — малый бизнес Казахстана

Сегменты:

- Kaspi-магазины;
- кафе и рестораны;
- салоны красоты;
- недвижимость;
- туризм;
- образовательные проекты;
- организаторы мероприятий.

Основные шаблоны:

- карточка товара;
- рекламный баннер;
- вертикальный ролик;
- акция/скидка;
- меню;
- визуал объекта;
- поздравление;
- текст поста на RU/KK.

### P2 — массовый пользователь

Сценарии:

- аватар и стилизация;
- восстановление старых фото;
- оживление семейного фото;
- открытки и поздравления;
- фото для резюме;
- мемы;
- AI-чат.

### P3 — агентства и команды

Добавляется после подтверждения B2C-экономики:

- общий баланс;
- рабочие пространства;
- роли;
- библиотека бренда;
- экспорт без водяного знака;
- API и массовые генерации.

---

## 4. Идеальный пользовательский опыт

## 4.1 Telegram-бот

Бот является входом, системой уведомлений, поддержкой и быстрым меню.
Сложные формы находятся в Mini App.

Обязательные команды:

- `/start` — регистрация, язык и короткий onboarding;
- `/create` — открыть студию;
- `/balance` — баланс и покупка кредитов;
- `/history` — последние работы;
- `/invite` — реферальная программа;
- `/support` — поддержка;
- `/paysupport` — вопросы по платежам Telegram Stars;
- `/settings` — язык, уведомления, удаление аккаунта.

Главное меню:

- Создать;
- Мои работы;
- Баланс;
- AI-чат;
- Пригласить друга;
- Помощь.

Бот должен:

- уведомлять о завершении или ошибке;
- присылать превью результата;
- давать кнопки «Скачать», «Повторить», «Изменить», «Оживить»;
- сообщать о возврате кредитов;
- не отправлять технические коды ошибок пользователю.

## 4.2 Mini App

Навигация:

1. Главная;
2. Создать;
3. Работы;
4. Баланс;
5. Профиль.

### Главная

- крупная кнопка «Создать»;
- последние работы;
- популярные сценарии;
- персональные рекомендации;
- актуальный баланс;
- примеры с готовыми промптами;
- сезонные подборки.

### Экран создания

Два режима:

**Простой**

- пользователь выбирает задачу;
- KELBET сам выбирает модель;
- показываются только необходимые поля;
- доступны переключатели «Быстро» и «Лучшее качество».

**Pro**

- выбор модели;
- разрешение;
- соотношение сторон;
- длительность;
- seed;
- negative prompt;
- количество вариантов;
- reference strength;
- motion/camera controls;
- дополнительные референсы.

Перед запуском всегда показываются:

- итоговая цена;
- ожидаемое время;
- формат результата;
- предупреждения по входным файлам;
- остаток после списания.

### Результат

- полноэкранный просмотр;
- скачать;
- поделиться;
- удалить;
- повторить;
- изменить промпт;
- сделать вариацию;
- оживить изображение;
- upscale;
- добавить в избранное;
- показать использованную модель, цену и параметры.

---

## 5. Продуктовый состав финальной версии

## 5.1 Изображения

Обязательные возможности:

- text-to-image;
- image-to-image;
- редактирование по инструкции;
- несколько референсов;
- удаление и замена фона;
- замена предмета;
- сохранение лица/персонажа;
- генерация текста на изображении;
- upscale 2×/4×;
- восстановление старых фото;
- удаление объектов;
- варианты и remix.

Минимальная матрица моделей:

- одна дешёвая быстрая модель;
- одна универсальная;
- одна premium-модель;
- отдельная модель редактирования;
- отдельный upscale.

Модели не зашиваются в интерфейс. Каталог и цены управляются из БД и
админ-панели.

## 5.2 Видео

Обязательные возможности:

- text-to-video;
- image-to-video;
- первый/последний кадр;
- видео с нативным звуком, если поддерживается;
- управление движением камеры;
- motion transfer;
- видеоредактирование;
- upscale;
- очередь с честным ожиданием;
- несколько длительностей и разрешений.

На запуске достаточно трёх продуктовых вариантов:

- Fast — недорого и быстро;
- Quality — основной режим;
- Cinema — лучший доступный результат.

Конкретные Veo, Kling, Seedance, Runway или другие SKU должны меняться через
каталог без релиза приложения.

## 5.3 Текст и AI-чат

- общий чат RU/KK;
- генератор рекламных текстов;
- пост для Instagram/Threads/Telegram;
- описание товара для Kaspi-магазина;
- перевод и адаптация RU ↔ KK;
- сценарий короткого видео;
- улучшение промпта для изображения/видео;
- сохранённые диалоги;
- выбор «быстро / умно» вместо длинного списка моделей.

## 5.4 Аудио и аватары

После стабильного image/video-релиза:

- text-to-speech RU/KK;
- speech-to-text;
- очистка голоса;
- звуковые эффекты;
- музыка;
- talking avatar;
- lipsync;
- клонирование голоса только с явным согласием и защитой от злоупотреблений.

## 5.5 Шаблоны для Казахстана

Это один из главных конкурентных рвов.

Первая коллекция:

- карточка товара Kaspi;
- объявление о скидке;
- меню кафе;
- афиша;
- Instagram Story 9:16;
- TikTok/Reels-реклама;
- поздравление с Наурызом;
- приглашение на той;
- свадебный ролик;
- недвижимость;
- тур по Казахстану;
- национальный стиль без стереотипной перегрузки;
- двуязычный пост RU/KK.

Каждый шаблон содержит:

- понятную форму;
- системный промпт;
- рекомендуемую модель;
- безопасные значения параметров;
- пример результата;
- локализованные подсказки;
- рассчитанную цену.

---

## 6. Монетизация и экономика

## 6.1 Денежная модель

Основная единица внутри продукта — **кредиты**.

Пользователь видит:

- цену каждой генерации;
- баланс;
- зарезервированные кредиты;
- историю начислений и списаний;
- возвраты.

Техническая формула цены:

`provider cost + storage + payment fee + failure reserve + support + target margin`

Целевая валовая маржа:

- изображения: не ниже 55%;
- текст: не ниже 65%;
- видео: не ниже 40%;
- средняя по продукту: не ниже 50%.

Цена хранится как целое число. Для каждого SKU задаются:

- себестоимость;
- пользовательская цена;
- минимальная маржа;
- лимит параллельных задач;
- цена по параметрам;
- fallback-маршрут.

## 6.2 Платёжные продукты

Запускать в таком порядке:

1. разовые пакеты кредитов;
2. Telegram Stars;
3. промокоды и бонусы;
4. реферальные начисления;
5. подписки с включёнными кредитами;
6. B2B-счета и командные балансы.

Внутри Telegram цифровые услуги оплачиваются Telegram Stars. Платёжный контур
обязан поддерживать:

- invoice;
- pre-checkout;
- successful payment;
- идемпотентное зачисление;
- хранение `telegram_payment_charge_id`;
- возврат Stars;
- `/paysupport`;
- сверку платежей;
- журнал операций.

Внешний сайт может иметь отдельный легальный checkout в тенге после юридической
проверки. Он не должен использоваться для обхода правил Telegram.

## 6.3 Предлагаемые пакеты

Финальные суммы определяются после тестов себестоимости:

- Trial — небольшой welcome bonus;
- Start — низкий порог первой покупки;
- Creator — основной пакет с лучшей конверсией;
- Pro — пакет для активных креаторов;
- Business — общий баланс и приоритетная очередь.

На старте не обещаем настоящий безлимит. Допустимы только:

- fair-use;
- дневные лимиты;
- отдельная очередь;
- ограничения на дорогие модели;
- чётко описанные условия.

---

## 7. Retention и рост

## 7.1 Активация

Пользователь считается активированным, когда:

1. прошёл onboarding;
2. запустил первую генерацию;
3. получил успешный результат;
4. скачал, повторил или поделился им.

Цель: довести до первого результата менее чем за 3 минуты.

## 7.2 Удержание

- история и избранное;
- повтор генерации в один клик;
- персональные шаблоны;
- ежедневные идеи;
- уведомление о готовности;
- бесплатная генерация за полезное действие;
- серии и проекты;
- недельный отчёт «что вы создали»;
- напоминание только при наличии релевантного сценария;
- отсутствие спама.

## 7.3 Реферальная система

- персональная deep-link ссылка;
- бонус пригласившему только после первой покупки приглашённого;
- небольшой стартовый бонус приглашённому;
- защита от self-referral и мультиаккаунтов;
- уровни партнёра;
- выплаты или кредиты после anti-fraud hold;
- отдельная программа для блогеров и SMM-агентств;
- Telegram Star affiliate program как дополнительный канал.

## 7.4 Запуск в Казахстане

Пилотные сообщества:

- SMM и мобилография;
- предприниматели Kaspi;
- дизайнеры;
- свадебные фотографы и видеографы;
- организаторы мероприятий;
- студенты creative-направлений;
- локальные Telegram-каналы.

Контент-маркетинг:

- короткие видео «до/после»;
- бесплатные локальные шаблоны;
- сравнение моделей на одной задаче;
- обучение промптам на RU/KK;
- кейсы малого бизнеса;
- челленджи к локальным праздникам;
- работы пользователей с разрешения авторов.

---

## 8. Техническая архитектура

Текущий модульный монолит является правильной основой. До подтверждения
масштаба переход к микросервисам не нужен.

### Сохраняем

- Python 3.12;
- aiogram 3;
- FastAPI;
- PostgreSQL как source of truth;
- SQLAlchemy async + Alembic;
- Redis для FSM, очередей, replay protection и rate limit;
- ARQ workers;
- React/Vite Mini App;
- S3-compatible object storage;
- provider adapters;
- DB-backed catalog;
- integer credit ledger;
- reserve/capture/release/refund;
- generation state machine;
- idempotency keys;
- webhooks + polling fallback.

### Целевая схема

```text
Telegram Bot ─┐
              ├── FastAPI ── Services ── PostgreSQL
Mini App ─────┘       │          │
                     Redis      Object Storage
                       │          │
                    ARQ Workers ──┼── Provider A
                                 ├── Provider B
                                 └── Provider C
```

### Новые функциональные модули

1. `payments`
   - products;
   - orders;
   - payment attempts;
   - Telegram Stars;
   - refunds;
   - reconciliation.

2. `notifications`
   - generation completed;
   - generation failed/refunded;
   - payment;
   - referral;
   - user preferences;
   - retry/outbox.

3. `templates`
   - localized form schema;
   - prompt builder;
   - model routing;
   - preview examples;
   - versioning.

4. `moderation`
   - prompt/input/output checks;
   - decision log;
   - manual review;
   - abuse strikes;
   - appeals.

5. `referrals`
   - attribution;
   - reward rules;
   - anti-fraud;
   - partner levels.

6. `admin`
   - catalog;
   - prices;
   - provider health;
   - user lookup;
   - jobs;
   - ledger;
   - refunds;
   - feature flags;
   - support;
   - audit log.

7. `analytics`
   - product events;
   - funnels;
   - provider cost;
   - revenue;
   - cohort retention;
   - experiment assignment.

8. `projects`
   - favorites;
   - collections;
   - saved presets;
   - brand kit;
   - team workspace.

### Фактический статус таблиц следующего цикла на 10 августа 2026

Уже реализованы миграциями:

- `payment_products`, `payment_orders`, `payment_receipts` — migration `0011`;
- `operator_memberships`, append-only `audit_events` и user block — migration `0012`;
- `moderation_decisions`, `user_consents` — migration `0013`;
- `generation_templates` и immutable template snapshots — migration `0014`;
- `payment_refunds`, Stars observations/reconciliation runs/issues — migration `0015`;
- immutable image `routing_snapshot` и fallback controls — migration `0016`;
- `referral_codes`, immutable `referral_attributions`, ledger-backed `referral_rewards` —
  migration `0017`;
- `notification_outbox` и настройка уведомлений в `users.notify_generation_ready` —
  migration `0008`;
- `feature_flags` и DB-backed catalog — migration `0004`.
- `generation_workflow_steps` для durable Veo extended flow — migration `0021`;
- payment checkout/reconciliation hardening — migration `0022`;
- `subscription_plans`, `user_subscriptions`, `subscription_grants` и Telegram-native renewal
  identity — migrations `0023`–`0024`;
- Veo consistency catalog route и disabled feature flag — migration `0025`.
- durable normalized Telegram payment/subscription update inbox — migration `0026`.

Ещё отсутствуют и должны добавляться только additive revisions после `0026`:

- отдельный `payment_attempts`, если reconciliation/refund state machine потребует
  историю попыток помимо durable receipts;
- `favorites`, `saved_presets`, `provider_health_samples`.

### Provider routing

У каждой продуктовой модели должен быть маршрут:

1. основной provider/SKU;
2. fallback;
3. timeout;
4. retry policy;
5. cost ceiling;
6. региональные ограничения;
7. capability map;
8. health status.

Fallback разрешён только если результат совместим по качеству, параметрам и
цене. Пользователь не должен платить больше подтверждённой цены.

---

## 9. Надёжность и безопасность

## 9.1 Финансовые инварианты

- баланс никогда не отрицательный;
- `reserved <= balance`;
- одна внешняя оплата даёт одно начисление;
- одна генерация создаёт не более одного capture;
- ошибка до capture освобождает hold;
- ошибка после capture приводит к идемпотентному refund;
- ручная корректировка только через ledger и audit log;
- цена генерации фиксируется snapshot-ом;
- повтор webhook/job безопасен.

## 9.2 Контент и злоупотребления

Текущий статус на 1 августа 2026: локальный moderation/anti-abuse minimum реализован.
Generation/chat/prompt assistant используют provider-independent text moderation;
generation проверяется до reserve/enqueue. Решения содержат hash/policy/safe codes без
сырого prompt, default mode — `report`. Image edit и image-to-video требуют versioned
подтверждение прав/согласия с timestamp. Support/admin имеют metadata-only queue и
идемпотентный audited review. Встроенный RU/KK baseline является phrase/obfuscation
filter, а не semantic classifier; image content moderation отсутствует и не заявляется.

Нужны правила и технические проверки для:

- сексуализированного контента с несовершеннолетними;
- несанкционированных deepfake;
- клонирования голоса без согласия;
- мошенничества и поддельных документов;
- травли;
- экстремистского и незаконного контента;
- обхода ограничений провайдера;
- массовых автоматизированных атак.

Для лица и голоса:

- явное подтверждение прав;
- отдельное согласие;
- журнал операции;
- ограничения для публичных лиц;
- быстрый канал жалобы;
- удаление исходников по запросу.

## 9.3 Персональные данные

До production-запуска обязательна юридическая проверка в Казахстане.

Базовые требования:

- минимизация собираемых данных;
- согласие RU/KK;
- политика конфиденциальности;
- пользовательское соглашение;
- сроки хранения;
- удаление аккаунта;
- экспорт истории;
- локализация базы персональных данных в Казахстане;
- документированная трансграничная передача файлов AI-провайдерам;
- шифрование секретов и приватных файлов;
- короткоживущие signed URLs;
- раздельный доступ support/admin;
- журнал действий сотрудников.

Пользовательские фото не используются для обучения KELBET без отдельного
добровольного согласия.

## 9.4 Production SLO

- API availability: 99.9%;
- успешная постановка задачи: 99.5%;
- финансовые расхождения: 0;
- потерянные generation jobs: 0;
- уведомление после terminal status: p95 < 30 секунд;
- API p95 без provider wait: < 400 мс;
- автоматическое обнаружение stuck job: < 5 минут;
- восстановление после отказа worker без ручного списания.

---

## 10. Аналитика и критерии продукта

### North Star Metric

**Количество успешно полученных и использованных результатов за неделю.**

Использованный результат — скачан, повторён, изменён или опубликован.

### Воронка

1. Start bot;
2. Complete onboarding;
3. Open create;
4. Select use case;
5. Receive quote;
6. Start generation;
7. Generation succeeds;
8. Result used;
9. First purchase;
10. Repeat purchase.

### Целевые показатели beta

- onboarding completion ≥ 75%;
- first generation started ≥ 55% от onboarding;
- first generation success ≥ 90%;
- результат использован ≥ 60% от success;
- D1 ≥ 30%;
- D7 ≥ 15%;
- конверсия в первую покупку ≥ 5%;
- refund по техническим причинам < 5%;
- support contacts из-за непонимания интерфейса < 3%;
- средняя валовая маржа ≥ 50%.

### События

Каждое событие имеет:

- `event_name`;
- `user_id`;
- `session_id`;
- `timestamp`;
- `language`;
- `source`;
- `template_id`;
- `model_slug`;
- `provider`;
- `generation_id`;
- `experiment_id`;
- безопасные свойства без prompt/PII.

Промпты, токены, initData и приватные URL в аналитику и логи не отправляются.

---

## 11. Админ-панель

Без админ-панели продукт нельзя считать финальным.

Текущий статус на 1 августа 2026: технический operator minimum реализован и выключен
по умолчанию. Есть server-only `/api/v1/admin`, отдельный `/admin`, RBAC `support`/`admin`,
env bootstrap, ledger-backed grant и generation refund, block/unblock, inspectors/controls
и append-only audit. CLI `packages/kelbet/ops/grant_credits.py` переиспользуется API, второго
пути прямого изменения balance нет. Production bootstrap/staging smoke test не подтверждены.

### Dashboard

- DAU/WAU/MAU;
- выручка;
- provider cost;
- gross margin;
- активные/зависшие задачи;
- success rate по моделям;
- p50/p95 времени;
- платежные ошибки;
- возвраты;
- support backlog.

### Управление

- модели и локализация;
- pricing rules;
- enabled/disabled;
- feature flags;
- provider routing;
- шаблоны;
- пакеты кредитов;
- промокоды;
- пользователи;
- операции кошелька;
- генерации и attempts;
- ручной retry;
- refund;
- блокировки;
- moderation review;
- рассылки;
- audit log.

Любое финансовое или модерационное действие записывает:

- кто выполнил;
- когда;
- причину;
- старое значение;
- новое значение;
- correlation ID.

---

## 12. План разработки

Оценка дана для одного сильного разработчика с AI-инструментами. При небольшой
команде независимые этапы можно выполнять параллельно.

## Этап 0 — стабилизация репозитория

Срок: 3–5 дней.

Статус на 1 августа 2026: локальный baseline воспроизводим частично — CI,
`.env.example`, deployment manifests и OpenAPI baseline существуют; `143` backend
tests, Ruff, mypy, frontend typecheck и production build проходят. Чистый Alembic
upgrade на новой production-like БД и фактический staging deployment этой
актуализацией не подтверждены.

Работы:

- разобрать и зафиксировать текущие незакоммиченные изменения;
- восстановить `.env.example`;
- создать рабочее окружение Python 3.12;
- запустить весь pytest;
- исправить Ruff/mypy;
- проверить все миграции на чистой БД;
- собрать Mini App;
- добавить CI quality gates;
- создать staging-конфигурацию;
- зафиксировать baseline OpenAPI.

Готово, когда:

- чистый воспроизводимый setup;
- все тесты зелёные;
- один commit соответствует одной завершённой задаче;
- staging поднимается одной командой.

## Этап 1 — продуктовая основа

Срок: 4–6 дней.

Работы:

- утвердить позиционирование;
- выбрать P0-аудиторию;
- описать 10 главных use cases;
- подготовить финансовую модель провайдеров;
- определить beta-пакеты;
- утвердить RU/KK tone of voice;
- определить event taxonomy;
- подготовить Figma-прототип ключевого пути.

Готово, когда 5 тестовых пользователей проходят прототип без объяснений.

## Этап 2 — единый Telegram UX

Срок: 1 неделя.

Работы:

- новое меню бота;
- Web App кнопка;
- onboarding в 3 шага;
- deep links;
- переход bot ↔ Mini App;
- настройки уведомлений;
- базовые `/support` и `/paysupport`;
- общий дизайн-токен RU/KK;
- корректная обработка незарегистрированного пользователя.

Готово, когда первая генерация доступна за ≤ 3 перехода после onboarding.

## Этап 3 — Image MVP

Срок: 2 недели.

Статус на 1 августа 2026: image generation/edit/upscale adapters, catalog-driven
flow и автоматические проверки реализованы локально; UI evidence-артефакты есть.
Все production image SKU завязаны на Runway. Шесть RU/KK image-шаблонов теперь приходят
из server catalog; `template_id`/version/inputs/full snapshot сохраняются в quote/job, а
product-card получает детерминированный text compositor.
Работа реальных ключей, storage/CORS и полный путь на production-like staging этой
актуализацией не подтверждены.

Работы:

- [x] подключить реальные image-generation и image-edit SKU;
- [x] реализовать capability-driven форму;
- [x] загрузку нескольких референсов;
- [x] prompt assistant RU/KK;
- [x] Smart/Fast/Quality;
- [x] output delivery;
- [x] preview/download/share;
- [x] повтор/remix/upscale;
- [x] уведомление в Telegram;
- [x] автоматический release/refund;
- [x] 6 server-backed RU/KK image-шаблонов;
- [x] сохранение template ID/version/inputs/snapshot;
- [x] детерминированный product-card text compositor.

Готово, когда полный путь payment-ready проходит на production-like staging.

## Этап 4 — Video MVP

Срок: 2–3 недели.

Статус на 1 августа 2026: production-hardening реализован на уровне кода и
contract/integration tests. Runway и прямой Google Veo представлены независимыми
маршрутами, временные ошибки получают cost-bounded fallback, а цена пользователя
не меняется после quote. Google completion использует подписанный callback,
Runway — polling с jitter. Автоматический тест сверяет 100 задач по lifecycle,
ledger, reservation, provider usage и output. Это не подтверждает реальные
provider accounts или production gate: нужны боевые ключи и успешный прогон
партии на production-like staging.

Работы:

- [x] минимум два независимых video provider route;
- [x] text-to-video;
- [x] image-to-video;
- [x] длительность/формат/качество;
- [x] честный ETA;
- [x] polling с provider-safe интервалом и jitter;
- [x] Google provider-specific webhook signature и replay protection;
- [x] atomic webhook deduplication и fast acknowledgement;
- [x] progress stages;
- [x] cancel;
- [x] timeout;
- [x] fallback;
- [x] Telegram delivery;
- [x] cost ceiling;
- [x] 5 server-backed видео-шаблонов и deterministic toi-invitation compositor.
- [x] автоматическая 100-job financial/lifecycle reconciliation.

Готово, когда 100 тестовых задач проходят без финансовых расхождений и
потерянных jobs.

## Этап 5 — платежи

Срок: 1–2 недели.

Статус на 1 августа 2026: безопасный технический контур реализован локально. Цены
фиксируются в order snapshot, pre-checkout проверяет владельца/валюту/сумму,
`successful_payment` создаёт durable receipt и ровно одно ledger-начисление.
Refund/recovery, reverse ledger и reconciliation/chargeback classification покрыты fake-gateway
тестами. Платежи по умолчанию выключены до юридической, финансовой и live-проверки.

Работы:

- [x] payment products и immutable snapshot;
- [x] Telegram Stars `XTR` invoice;
- [x] pre-checkout owner/currency/amount/expiry validation;
- [x] durable successful-payment receipt;
- [x] идемпотентное ledger-начисление по Telegram charge ID;
- [x] operator-only refunds с recovery и audit;
- [x] purchase history;
- [x] rejected receipt + `/paysupport` flow;
- [x] Telegram Star reconciliation job;
- [x] chargeback/dispute ingestion и fraud limits/review;
- [x] редактируемые beta-пакеты;
- [ ] юридически утверждённые правовые тексты RU/KK.

Готово, когда повтор любого Telegram update не удваивает начисление.

## Этап 6 — админка, поддержка и модерация

Срок: 2 недели.

Статус на 1 августа 2026: admin/operator minimum и metadata-only moderation queue
реализованы локально. Support читает очередь, admin фиксирует review outcome через
idempotent action + append-only audit. Admin/moderation production gates не пройдены до
реального bootstrap, report-mode staging smoke test и false-positive review. Подробности
и границы зафиксированы в `IMPLEMENTATION_ROADMAP.md`.

Работы:

- admin auth + RBAC;
- catalog/pricing;
- provider health;
- generation inspector;
- wallet ledger;
- refund;
- support case;
- moderation queue;
- block/unblock;
- audit log;
- operational dashboards.

Готово, когда типовая проблема пользователя решается без доступа к БД и
терминалу.

## Этап 7 — закрытая beta

Срок: 2 недели.

Выборка:

- 30 креаторов/SMM;
- 20 владельцев малого бизнеса;
- 30 обычных пользователей;
- RU/KK представлены отдельно.

Работы:

- интервью;
- funnel review;
- prompt/template tuning;
- provider quality score;
- price sensitivity;
- support taxonomy;
- исправление P0/P1;
- нагрузочный тест;
- security review.

Gate:

- ≥ 90% generation success;
- ≥ 50% пользователей получают полезный результат;
- нет финансовых P0;
- unit economics положительная;
- нет открытых security P0/P1.

## Этап 8 — публичный запуск Казахстан

Срок: 1 неделя подготовки + 2 недели наблюдения.

Текущий статус referral: MVP реализован локально и выключен через `referrals=false`.
`/start ref_<code>`, immutable new-user attribution, reconciliation-confirmed first purchase,
reward worker/ledger, limits/review, `/invite`, Mini App RU/KK и read-only admin покрыты тестами.
Production rollout разрешён только после payment live gate и стабильной reconciliation.

Работы:

- [x] referral MVP (локальный technical gate; canary ещё не выполнен);
- промокоды;
- landing page;
- demo gallery с согласиями;
- канал с примерами;
- база знаний RU/KK;
- support schedule;
- мониторинг;
- alerting;
- incident runbooks;
- backup/restore drill;
- launch campaign.

Первые две недели запрещены крупные новые функции: только надёжность,
конверсия, качество и экономика.

## Этап 9 — рост

Срок: постоянный.

Порядок:

1. улучшение activation;
2. локальные шаблоны;
3. referral/affiliate;
4. подписки;
5. audio/avatars;
6. проекты и brand kit;
7. команды/B2B;
8. API;
9. Узбекистан/Кыргызстан;
10. отдельное мобильное приложение только при доказанной необходимости.

---

## 13. Приоритетный backlog

### P0 — до первой платной beta

- стабильный Python/CI baseline;
- реальный image provider;
- реальный video provider;
- prompt RU/KK;
- Mini App create flow;
- загрузка и outputs;
- Telegram notifications;
- Stars payments;
- ledger/reconciliation;
- admin minimum;
- support;
- privacy/terms/consents;
- analytics funnel;
- 10 локальных шаблонов;
- moderation minimum;
- staging/monitoring/backups.

### P1 — первый месяц после запуска

- второй **image-provider** для generation/edit fallback — локально реализован через Google
  Gemini native image, но не подтверждён live-прогоном; upscale остаётся primary-only;
- referral — локально реализован, rollout ждёт payment gate и canary;
- промокоды;
- favorites;
- presets;
- remix/upscale;
- provider quality dashboard;
- subscription Mini App flow и production rollout (backend/API/bot/worker уже реализованы,
  feature flag выключен);
- расширенная галерея;
- локальные бизнес-шаблоны;
- A/B onboarding и pricing.

### P2 — после product-market signal

- audio;
- avatars;
- brand kit;
- teams;
- API;
- batch generation;
- public template marketplace;
- creator affiliate cabinet;
- multi-country localization.

---

## 14. Правила разработки

Каждая функция проходит:

1. короткий PRD;
2. UX-сценарий RU/KK;
3. acceptance criteria;
4. threat/abuse check;
5. unit economics check;
6. migration/API implementation;
7. tests;
8. observability;
9. documentation;
10. staged rollout через feature flag.

### Definition of Done

Задача не завершена, пока:

- есть happy path;
- обработаны ошибки;
- RU и KK проверены человеком;
- деньги идемпотентны;
- ownership проверен;
- есть unit/integration tests;
- метрики и безопасные логи добавлены;
- администратор может диагностировать проблему;
- rollback понятен;
- документация обновлена.

### Приоритет при конфликте

1. безопасность и корректность денег;
2. полезность результата;
3. простота интерфейса;
4. надёжность;
5. скорость;
6. количество моделей и функций.

---

## 15. Что означает «финальный продукт»

Финальная первая версия — это не момент, когда подключены все модели мира.
Это момент, когда:

- человек без опыта получает хороший результат за несколько минут;
- интерфейс одинаково полноценен на RU и KK;
- есть изображения, редактирование и видео;
- платежи и возвраты надёжны;
- цена понятна до запуска;
- провайдер можно заменить без поломки продукта;
- пользователь видит историю и продолжает работу с результатом;
- support решает проблему по ID операции;
- админ управляет моделями и ценами без релиза;
- экономика каждой генерации измеряется;
- персональные данные и пользовательские файлы защищены;
- продукт выдерживает публичный трафик;
- команда понимает следующий приоритет из данных, а не из догадок.

---

## 16. Первый практический цикл

Следующую разработку вести строго в dependency order из актуального roadmap:

1. observability;
2. admin auth, audit и operator minimum;
3. moderation и consent;
4. доведение локальных шаблонов до server-backed snapshots и compositor minimum;
5. production gates Telegram Stars;
6. второй image-provider и ограниченный fallback;
7. referral MVP.

Все семь технических этапов dependency order реализованы локально: observability,
admin/audit, moderation/consent, server templates/compositor, Stars refunds/reconciliation,
Google image generation/edit fallback и referral MVP. Safe defaults и экономика MVP зафиксированы
в server config без ожидания подтверждения владельца. Следующая работа — не новый внутренний
контур, а последовательные внешние gates: Sentry/metrics staging drill, admin bootstrap,
moderation/template canary, legal/finance/support и Telegram Stars live gate, Google provider
canary, затем allowlisted referral canary. Внешние проверки нельзя считать выполненными без
проверяемого evidence; соответствующие flags остаются выключенными.

---

## 17. Источники для продуктовых решений

- Neuroplace: категории, модели и тарифы — <https://neuroplace.ai/pricing>
- Neuroplace video UX — <https://neuroplace.ai/video>
- Telegram-профиль VeoSeeBot — <https://t.me/VeoSeeBot>
- Telegram Stars для цифровых товаров —
  <https://core.telegram.org/bots/payments-stars>
- Telegram Stars и affiliate programs —
  <https://core.telegram.org/api/stars>
- Электронная коммерция Казахстана за 2025 год —
  <https://stat.gov.kz/ru/industries/economy/local-market/publications/346330/>
- Разъяснение по хранению персональных данных в Казахстане —
  <https://www.gov.kz/memleket/entities/zhetysu-eskeldy-kokzhazyk/press/article/details/218955>
- Требования ККМ и электронных чеков в 2026 году —
  <https://www.gov.kz/memleket/entities/kgd-zhetysu/press/news/details/1245690?lang=ru>

Юридические разделы являются требованиями к проверке, а не заменой заключения
юриста и бухгалтера в Республике Казахстан.
