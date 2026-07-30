# KELBET AI: полный запуск, деплой и самостоятельное тестирование

Инструкция рассчитана на Windows PowerShell и первый самостоятельный деплой.
Секреты нельзя записывать в файлы репозитория или отправлять в чат.

## 1. Что и где будет работать

```text
Telegram
   │
   ├── Bot (Railway, long polling)
   │
   └── Mini App (Vercel)
          │
          └── API (Railway)
                 ├── PostgreSQL (Railway)
                 ├── Redis (Railway)
                 ├── Worker bundle (Railway)
                 └── Cloudflare R2 / S3 (файлы генераций)
```

В Railway будет пять блоков:

1. `Postgres`;
2. `Redis`;
3. `kelbet-api`;
4. `kelbet-bot`;
5. `kelbet-worker`.

Один `kelbet-worker` запускает четыре внутренние очереди: image, text, video и
maintenance. Не создавайте четыре отдельных worker-сервиса на первом этапе.

## 2. Что подготовить

- аккаунт GitHub;
- аккаунт Vercel;
- аккаунт Railway с подключённым способом оплаты;
- Telegram и доступ к `@BotFather`;
- Cloudflare аккаунт для R2 — нужен для загрузок и результатов генерации;
- установленный Docker Desktop;
- Python 3.12;
- Node.js 22;
- Git.

Проверка установленных программ:

```powershell
git --version
python --version
node --version
docker --version
```

## 3. Создание Telegram-бота

1. Откройте официальный `@BotFather`.
2. Отправьте `/newbot`.
3. Укажите отображаемое имя, например `KELBET AI`.
4. Укажите username, заканчивающийся на `bot`, например `kelbet_ai_bot`.
5. Сохраните полученный token в менеджере паролей.

Token выглядит примерно так:

```text
1234567890:AAExampleSecret
```

Если token когда-либо попал в GitHub, скриншот или чужой чат:

1. откройте `@BotFather`;
2. выполните `/revoke`;
3. создайте новый token;
4. замените его во всех Railway-сервисах.

Оформление можно сделать сразу:

- `/setuserpic` — аватар;
- `/setdescription` — описание;
- `/setabouttext` — короткое описание профиля.

Menu Button и Main Mini App настраиваются после получения Vercel URL.

## 4. Локальная проверка до хостинга

### 4.1. Backend

Из корня проекта:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Откройте `.env` и замените:

```text
BOT_TOKEN=replace-with-telegram-bot-token
```

на настоящий token. Файл `.env` уже исключён из Git.

Запустите базы:

```powershell
docker compose up -d postgres redis
```

Создайте таблицы:

```powershell
alembic upgrade head
```

Запустите API в отдельном терминале:

```powershell
.\.venv\Scripts\Activate.ps1
python -m apps.api
```

Откройте:

```text
http://localhost:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

Запустите бота во втором терминале:

```powershell
.\.venv\Scripts\Activate.ps1
python -m apps.bot
```

### 4.2. Mini App в mock-режиме

В третьем терминале:

```powershell
Set-Location apps\web
Copy-Item .env.example .env.local
npm install
npm run dev
```

Откройте `http://localhost:5173`.

`VITE_API_MODE=mock` позволяет проверить дизайн без Telegram, Railway и платных
AI API. Настоящую Telegram-авторизацию проверяем позже через опубликованного бота.

### 4.3. Локальные проверки

Из корня проекта:

```powershell
ruff check .
mypy
pytest
```

Frontend:

```powershell
Set-Location apps\web
npm run lint
npm run typecheck
npm run build
```

## 5. Загрузка проекта в GitHub

Создайте приватный репозиторий на GitHub и отправьте туда проект.

Перед отправкой обязательно проверьте:

```powershell
git status --short
git grep -n "1234567890:AA"
```

Вторая команда не должна находить настоящий BotFather token.

Не добавляйте:

- `.env`;
- `.env.local`;
- R2 secret key;
- OpenRouter/Runway/Google ключи;
- Railway public/private URLs с паролями.

## 6. Создание Railway-проекта

### 6.1. PostgreSQL и Redis

1. Создайте новый Railway Project.
2. Нажмите `New` → `Database` → `PostgreSQL`.
3. Оставьте имя сервиса `Postgres`.
4. Добавьте Redis через `New` → `Database`/template → `Redis`.
5. Оставьте имя сервиса `Redis`.

Имена важны для reference variables:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
```

Если назвали сервисы иначе, измените имена внутри `${{...}}`.

### 6.2. API service

1. Нажмите `New` → `GitHub Repo`.
2. Выберите репозиторий KELBET.
3. Назовите сервис `kelbet-api`.
4. Root Directory оставьте пустым: backend использует общие папки из корня.
5. В Settings найдите Railway Config File.
6. Укажите абсолютный путь:

```text
/deploy/railway/api.json
```

Конфиг уже задаёт:

- production Dockerfile;
- `python -m apps.api`;
- `alembic upgrade head` перед запуском;
- healthcheck `/health`;
- restart policy.

### 6.3. Переменные API

Откройте:

```text
deploy/railway/variables.example
```

Скопируйте переменные в `kelbet-api` → Variables → Raw Editor.

До появления Vercel URL временно можно поставить:

```text
MINI_APP_URL=https://example.vercel.app
CORS_ORIGINS=https://example.vercel.app
```

Обязательные значения:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
BOT_TOKEN=ваш_token_от_BotFather
APP_ENV=production
GENERATION_QUEUE_BACKEND=arq
```

`BOT_TOKEN` нужен API для серверной проверки Telegram `initData`. API и bot
обязаны использовать один и тот же token.

Создать случайный `WEBHOOK_SECRET` в PowerShell:

```powershell
[Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLower()
```

Секреты в Railway рекомендуется отметить как `Sealed`.

### 6.4. Первый запуск API

Запустите Deploy. После успешного запуска:

1. откройте `kelbet-api` → Settings → Networking;
2. нажмите Generate Domain;
3. получите адрес вида:

```text
https://kelbet-api-production.up.railway.app
```

Проверьте:

```text
https://kelbet-api-production.up.railway.app/health
```

Если API не запускается:

- откройте Deploy Logs;
- проверьте `DATABASE_URL`;
- убедитесь, что Config File равен `/deploy/railway/api.json`;
- убедитесь, что pre-deploy migration завершилась кодом 0.

## 7. Деплой Mini App на Vercel

1. Нажмите `Add New` → `Project`.
2. Импортируйте тот же GitHub-репозиторий.
3. Установите Root Directory:

```text
apps/web
```

4. Framework Preset: `Vite`.
5. Build Command и Output Directory уже заданы в `apps/web/vercel.json`.
6. Добавьте Production Environment Variables:

```text
VITE_API_MODE=live
VITE_API_BASE_URL=https://ВАШ_API.up.railway.app
```

В `VITE_*` нельзя помещать секреты: эти значения попадают в браузерный bundle.

7. Нажмите Deploy.
8. Сохраните production URL:

```text
https://kelbet-ai.vercel.app
```

Проверьте SPA-маршруты напрямую:

```text
https://kelbet-ai.vercel.app/
https://kelbet-ai.vercel.app/create
https://kelbet-ai.vercel.app/history
https://kelbet-ai.vercel.app/plans
```

Все должны открываться без Vercel 404. Это обеспечивает `vercel.json`.

После изменения `VITE_API_BASE_URL` нужно сделать новый Vercel Redeploy: Vite
встраивает переменную во время сборки.

## 8. Связывание Vercel и Railway

Во всех трёх Railway application services должны быть:

```text
MINI_APP_URL=https://kelbet-ai.vercel.app
CORS_ORIGINS=https://kelbet-ai.vercel.app
```

Правила:

- только origin, без `/create`;
- без завершающего `/`;
- обязательно `https://`;
- Preview URL Vercel отличается от Production URL и не будет разрешён
  автоматически.

После изменения переменных сделайте Redeploy API.

## 9. Bot и Worker в Railway

### 9.1. Bot

Добавьте ещё один service из того же GitHub repository:

```text
Name: kelbet-bot
Root Directory: пусто
Config File: /deploy/railway/bot.json
```

Скопируйте в него те же переменные из `deploy/railway/variables.example`.

Для bot не создавайте Public Domain. Он использует Telegram long polling.

Запустите только одну реплику bot. Две реплики с одним token будут конфликтовать
при получении Telegram updates.

В логах должны появиться запуск aiogram и настройка команд. Ошибки вида
`BOT_TOKEN is not set` означают, что token не добавлен в этот service.

### 9.2. Worker bundle

Добавьте третий application service:

```text
Name: kelbet-worker
Root Directory: пусто
Config File: /deploy/railway/worker.json
```

Скопируйте те же переменные.

В логах должны запуститься:

```text
ImageWorkerSettings
TextWorkerSettings
VideoWorkerSettings
MaintainWorkerSettings
```

На первом этапе оставьте одну реплику worker-bundle. Maintenance queue содержит
периодические задачи; бессистемное масштабирование может запустить лишние cron
процессы.

Порядок первого деплоя:

1. Postgres;
2. Redis;
3. API и миграции;
4. bot;
5. worker.

## 10. Cloudflare R2 для загрузок и результатов

Без S3/R2 можно проверить `/start`, профиль, язык, баланс и mock-чат. Полную
загрузку файлов и выдачу результатов между API и worker проверяйте только с R2:
память разных Railway-контейнеров не является общей и исчезает при redeploy.

### 10.1. Bucket и ключи

1. Cloudflare Dashboard → R2 Object Storage.
2. Создайте bucket `kelbet-assets`.
3. Создайте R2 API token с Object Read & Write только для этого bucket.
4. Сохраните Access Key ID и Secret Access Key.
5. Скопируйте Account ID.

Railway variables:

```text
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://ACCOUNT_ID.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=ваш_access_key
S3_SECRET_ACCESS_KEY=ваш_secret_key
S3_BUCKET=kelbet-assets
S3_REGION=auto
```

Добавьте их в API и worker. Bot может получать те же shared variables, но сам
не загружает файлы.

### 10.2. R2 CORS

Откройте bucket → Settings → CORS Policy и вставьте содержимое:

```text
deploy/railway/r2-cors.example.json
```

Сначала замените:

```text
https://REPLACE_WITH_VERCEL_DOMAIN
```

на точный production origin, например:

```text
https://kelbet-ai.vercel.app
```

Не добавляйте путь или завершающий `/`.

После настройки Redeploy API и worker.

## 11. BotFather: подключение Mini App

### 11.1. Menu Button

1. Откройте `@BotFather`.
2. Отправьте `/setmenubutton`.
3. Выберите вашего бота.
4. Текст кнопки: `Открыть KELBET`.
5. URL: production Vercel URL.

### 11.2. Main Mini App

В `@BotFather`:

1. `/mybots`;
2. выберите бота;
3. `Bot Settings`;
4. `Configure Mini App` / `Main Mini App`;
5. включите Mini App;
6. укажите тот же Vercel URL.

После этого в профиле бота появится заметная кнопка запуска, а приложение можно
будет открывать ссылкой:

```text
https://t.me/ВАШ_BOT_USERNAME?startapp
```

Кнопки reply keyboard уже создаются самим KELBET через `MINI_APP_URL`.

## 12. Первый полный тест

Откройте бота в обычном Telegram-клиенте.

### Тест 1. Bot

1. Отправьте `/start`.
2. Проверьте русское/казахское приветствие.
3. Проверьте кнопки изображения, видео, AI-чата, работ, баланса и профиля.
4. Выполните `/menu`, `/create`, `/video`, `/history`, `/balance`, `/profile`.

### Тест 2. Авторизация Mini App

1. Откройте Mini App из кнопки бота, не из обычного браузера.
2. Проверьте профиль Telegram.
3. Новый пользователь должен получить welcome balance.
4. Переключите RU → KK.
5. Закройте и снова откройте Mini App: KK должен сохраниться.

Прямое открытие production URL в Chrome не содержит настоящего Telegram
`initData`, поэтому live API вправе отклонить авторизацию. Это не ошибка, если
через Telegram всё работает.

### Тест 3. Бесплатный AI mock

До покупки API-ключей:

```text
CHAT_PROVIDER=mock
```

В Image Studio включите Pro и выберите mock-модель. Создайте тест с коротким
prompt. Проверьте:

- статус переходит из queued/running в succeeded;
- worker обработал queue;
- результат появился в History;
- баланс и ledger изменились один раз;
- повторное обновление страницы не списывает кредиты повторно.

Для теста ошибки используйте prompt:

```text
fail
```

Mock provider должен вернуть контролируемый failed state, а reserved credits
не должны потеряться.

### Тест 4. Загрузка файла

1. Добавьте изображение-референс.
2. В DevTools/логах не должно быть R2 CORS ошибки.
3. В R2 bucket должен появиться input object.
4. Worker должен прочитать input и сохранить output.

### Тест 5. Уведомления

1. В профиле включите уведомление о готовом результате.
2. Запустите генерацию.
3. Maintain worker должен отправить сообщение в Telegram только после готовности.

## 13. Автоматический публичный smoke test

После деплоя запустите из корня:

```powershell
python scripts\smoke_deployment.py `
  --api https://ВАШ_API.up.railway.app `
  --web https://ВАШ_WEB.vercel.app
```

Ожидается пять `PASS`:

- API health;
- главная Mini App;
- `/create`;
- `/history`;
- `/plans`.

Этот тест не подделывает Telegram `initData` и не проверяет личные API-методы.
Их проверяем только через реальный запуск из Telegram.

## 14. Подключение настоящих AI

Подключайте провайдеры по одному.

### OpenRouter для AI-чата и Prompt Lab

```text
CHAT_PROVIDER=openrouter
OPENROUTER_API_KEY=ваш_ключ
OPENROUTER_MODEL=выбранная_модель
OPENROUTER_HTTP_REFERER=https://kelbet-ai.vercel.app
OPENROUTER_APP_TITLE=KELBET AI
```

Ключ нужен API, bot и worker только там, где соответствующий код обращается к
провайдеру. Проще хранить его как sealed shared variable.

### Runway

```text
RUNWAY_API_KEY=ваш_ключ
```

Сначала проверьте одну дешёвую image-задачу, затем video. Установите лимиты
расходов в кабинете провайдера.

### Google Veo fallback

```text
GOOGLE_API_KEY=ваш_ключ
GOOGLE_WEBHOOK_SIGNING_SECRETS=whsec_...
```

Не включайте fallback до проверки подписей webhook и лимита стоимости.

После добавления любого ключа:

1. Redeploy API и worker;
2. выполните одну генерацию;
3. проверьте Railway logs;
4. сравните provider charge и списанные KELBET credits;
5. установите billing alerts у провайдера.

## 15. Telegram Stars

По умолчанию:

```text
PAYMENTS_ENABLED=false
```

Это правильно для первого теста.

Перед включением Stars обязательны:

- публичная страница условий покупки и возврата;
- актуальная версия условий;
- рабочий support username;
- проверенные цены и экономика;
- ручной сценарий возврата;
- тест идемпотентности повторного Telegram update.

После подготовки:

```text
PAYMENTS_ENABLED=true
PAYMENT_TERMS_URL=https://ваш-домен/terms
PAYMENT_TERMS_VERSION=YYYY-MM-DD
SUPPORT_USERNAME=username_без_@
```

Redeploy API и bot. Затем выполните одну минимальную покупку Stars и проверьте:

- invoice использует валюту `XTR`;
- checkout проходит;
- credits начисляются один раз;
- повторная доставка update не начисляет credits повторно;
- `/paysupport` открывает поддержку.

## 16. Где смотреть ошибки

### API

- Railway → `kelbet-api` → Deploy Logs;
- `/health`;
- CORS origin;
- миграции Alembic;
- Telegram auth validation.

### Bot

- Railway → `kelbet-bot` → Deploy Logs;
- наличие `BOT_TOKEN`;
- только одна реплика;
- доступность Redis/Postgres;
- одинаковый token у API и bot.

### Worker

- Railway → `kelbet-worker` → Deploy Logs;
- запуск всех четырёх `WorkerSettings`;
- `GENERATION_QUEUE_BACKEND=arq`;
- Redis reference;
- R2 credentials;
- ключ нужного AI provider.

### Vercel

- Build Logs;
- Root Directory `apps/web`;
- `VITE_API_MODE=live`;
- production `VITE_API_BASE_URL`;
- Redeploy после изменения Vite variables.

## 17. Частые проблемы

### На `/create` Vercel показывает 404

Проверьте:

```text
Root Directory = apps/web
apps/web/vercel.json существует
```

### Mini App открывается, но API пишет CORS

`CORS_ORIGINS` должен точно совпадать с origin Vercel:

```text
https://kelbet-ai.vercel.app
```

Без пути и без завершающего `/`.

### `Invalid Telegram init data`

- запускайте Mini App из Telegram;
- API и bot должны использовать один `BOT_TOKEN`;
- проверьте время на сервере/устройстве;
- не используйте устаревшую открытую вкладку.

### Bot не отвечает

- проверьте Deploy Logs;
- не запущена ли вторая копия bot локально;
- не запущены ли две Railway replicas;
- проверьте token и Redis.

### Генерация навсегда queued

- worker должен быть запущен;
- `GENERATION_QUEUE_BACKEND=arq`;
- API и worker должны ссылаться на один Redis;
- в worker logs должны быть четыре очереди.

### Upload выдаёт CORS/403

- проверьте R2 CORS;
- origin без `/`;
- `Content-Type` должен совпадать с подписанным;
- API и worker используют один bucket и одну пару ключей.

### После изменения Vercel variable ничего не изменилось

Сделайте Redeploy: Vite variables встраиваются на этапе build.

## 18. Финальный production checklist

- [ ] GitHub repository не содержит секретов.
- [ ] PostgreSQL и Redis доступны только через Railway references.
- [ ] API `/health` возвращает 200.
- [ ] Alembic migration завершилась.
- [ ] Vercel SPA-маршруты не дают 404.
- [ ] CORS содержит точный production origin.
- [ ] Bot работает в одной реплике.
- [ ] Worker запускает четыре очереди.
- [ ] R2 CORS разрешает production Vercel origin.
- [ ] RU/KK сохраняются после перезапуска.
- [ ] Mock success и mock failure протестированы.
- [ ] History, balance и notification проверены.
- [ ] Настоящие AI ключи sealed и имеют billing limits.
- [ ] Stars остаются выключенными до готовности legal/support.
- [ ] Railway и провайдеры имеют spending alerts.

## Официальные источники

- Vercel SPA routing:
  https://vercel.com/kb/guide/why-is-my-deployed-project-giving-404
- Railway Config as Code:
  https://docs.railway.com/config-as-code/reference
- Railway monorepo:
  https://docs.railway.com/deployments/monorepo
- Railway variables:
  https://docs.railway.com/variables
- Telegram Mini Apps:
  https://core.telegram.org/bots/webapps
- Cloudflare R2 CORS:
  https://developers.cloudflare.com/r2/buckets/cors/
