from kelbet.i18n.keys import Msg

# Кнопки (Reply/Inline) и тексты для alert-попапов не должны содержать HTML-тегов:
# Telegram не парсит разметку в этих местах. HTML допустим только в телах сообщений.
TEXTS: dict[str, str] = {
    Msg.START_CHOOSE_LANG: "🌐 Выберите язык / Тілді таңдаңыз:",
    Msg.START_WELCOME: (
        "✨ <b>Добро пожаловать в KELBET AI!</b>\n\n"
        "Ваша творческая AI-студия прямо в Telegram:\n\n"
        "🎨 Генерация изображений\n"
        "🎬 Создание видео\n"
        "💬 Умный AI-чат\n\n"
        "🎁 Вам начислено <b>{credits} приветственных кредитов</b> ⚡\n\n"
        "👇 Нажмите «Создать изображение», опишите идею — и получите первую работу!"
    ),
    Msg.START_WELCOME_BACK: (
        "👋 <b>С возвращением в KELBET AI!</b>\n\nВыберите, что хотите создать сегодня 👇"
    ),
    Msg.LANG_RU: "🇷🇺 Русский",
    Msg.LANG_KK: "🇰🇿 Қазақша",
    Msg.LANG_SET: "✅ Язык сохранён: русский",
    Msg.MENU_CREATE: "🎨 Создать изображение",
    Msg.MENU_VIDEO: "🎬 Создать видео",
    Msg.MENU_TRENDS: "🔥 Тренды",
    Msg.MENU_AI_CHAT: "💬 AI-чат",
    Msg.MENU_MY_WORKS: "📁 Мои работы",
    Msg.MENU_TARIFFS: "💎 Тарифы",
    Msg.MENU_PARTNERSHIP: "🤝 Партнёрство",
    Msg.MENU_PROFILE: "👤 Профиль",
    Msg.MENU_TITLE: "🏠 <b>Главное меню</b>\n\nВыберите раздел 👇",
    Msg.MENU_BALANCE: "💰 Баланс",
    Msg.MENU_INVITE: "🎁 Пригласить друга",
    Msg.COMING_SOON: "🚧 Скоро будет доступно. Мы уже работаем над этим!",
    Msg.NEED_REGISTER: "👉 Сначала нажмите /start и выберите язык.",
    Msg.MINI_APP_OPEN: "🚀 <b>Студия KELBET AI</b>\n\nОткройте студию одним нажатием 👇",
    Msg.MINI_APP_UNAVAILABLE: (
        "⚙️ Mini App пока не настроен.\nМы уже работаем над запуском — попробуйте немного позже."
    ),
    Msg.MINI_APP_CREATE: "🎨 Открыть Image Studio",
    Msg.MINI_APP_VIDEO: "🎬 Открыть Video Studio",
    Msg.MINI_APP_TRENDS: "🔥 Открыть тренды",
    Msg.MINI_APP_HISTORY: "📁 Открыть мои работы",
    Msg.MINI_APP_PLANS: "💳 Пополнить баланс",
    Msg.BALANCE_TITLE: "💰 <b>Ваш баланс</b>",
    Msg.BALANCE_TOTAL: "💎 Всего: <b>{balance}</b> кредитов",
    Msg.BALANCE_RESERVED: "⏳ В работе: {reserved}",
    Msg.BALANCE_AVAILABLE: "✅ Доступно: <b>{available}</b>",
    Msg.BALANCE_TOP_UP: "💳 Пополнить",
    Msg.SETTINGS_TITLE: "⚙️ <b>Настройки</b>",
    Msg.SETTINGS_LANGUAGE: "🌐 Выберите язык интерфейса:",
    Msg.SUPPORT_TEXT: (
        "🛟 <b>Служба поддержки</b>\n\n"
        "Опишите вопрос одним сообщением. Если проблема связана с генерацией, "
        "приложите её ID."
    ),
    Msg.PAY_SUPPORT_TEXT: (
        "💳 <b>Помощь с оплатой</b>\n\n"
        "Укажите дату, сумму и Telegram ID.\n"
        "⚠️ Не отправляйте данные карты."
    ),
    Msg.SUPPORT_OPEN: "✍️ Написать в поддержку",
    Msg.SUPPORT_UNAVAILABLE: (
        "⚙️ Поддержка пока не настроена. Повторите попытку позже — ваши кредиты сохранятся."
    ),
    Msg.INVITE_COMING_SOON: (
        "🎁 <b>Реферальная программа скоро откроется!</b>\n\n"
        "Приглашайте друзей и получайте бонусные кредиты. "
        "Бонус начислим только за реальных друзей."
    ),
    Msg.INVITE_SUMMARY: (
        "🎁 <b>Приглашайте друзей</b>\n\n"
        "Ваша ссылка: <code>{link}</code>\n\n"
        "👥 Приглашено: <b>{invited}</b>\n"
        "⏳ Ожидают бонуса: <b>{pending}</b>\n"
        "💎 Начислено: <b>{credited}</b> кредитов\n\n"
        "Бонус {inviter_bonus} кредитов начисляется после первой подтверждённой "
        "покупки друга от {minimum} Stars и периода ожидания {waiting} ч. "
        "Возврат или спор отменяет неначисленный бонус."
    ),
    Msg.INVITE_SHARE: "📤 Поделиться ссылкой",
    Msg.INVITE_OPEN: "🎁 Открыть программу",
    Msg.PROFILE_TITLE: "👤 <b>Ваш профиль</b>\n",
    Msg.PROFILE_TELEGRAM_ID: "🆔 Telegram ID: <code>{telegram_id}</code>",
    Msg.PROFILE_USERNAME: "📛 Username: {username}",
    Msg.PROFILE_LANGUAGE: "🌐 Язык: {language}",
    Msg.PROFILE_BALANCE: "💎 Баланс: <b>{balance}</b>",
    Msg.PROFILE_PLAN: "⭐ Тариф: {plan}",
    Msg.PROFILE_NO_USERNAME: "не указан",
    Msg.PLAN_FREE: "Free",
    Msg.CHAT_PROMPT: (
        "💬 <b>AI-чат</b>\n\n"
        "Напишите ваш вопрос — отвечу на русском, қазақша "
        "или на смешанных сообщениях 👇"
    ),
    Msg.CHAT_CANCEL: "❌ Отмена",
    Msg.CHAT_ASK_AGAIN: "🔄 Ещё вопрос",
    Msg.CHAT_MAIN_MENU: "🏠 Главное меню",
    Msg.CHAT_CANCELLED: "✅ Чат завершён. Вы в главном меню.",
    Msg.CHAT_INSUFFICIENT: (
        "😔 <b>Недостаточно кредитов</b>\n\n"
        "Нужен минимум {cost}, у вас {balance}.\n"
        "⚡ Пополнить баланс: /buy"
    ),
    Msg.CHAT_PROVIDER_ERROR: (
        "⚠️ Не удалось получить ответ AI.\nКредит не списан. Попробуйте ещё раз."
    ),
    Msg.CHAT_TOO_LONG: "✂️ Сообщение слишком длинное. Максимум {max_chars} символов.",
    Msg.CHAT_EMPTY: "💬 Отправьте текстовое сообщение с вопросом.",
    Msg.CHAT_NEED_REGISTER: "👉 Сначала нажмите /start и выберите язык.",
    Msg.CHAT_BALANCE_LEFT: "💎 Остаток кредитов: <b>{balance}</b>",
    Msg.MODERATION_BLOCKED: (
        "⚠️ Запрос остановлен правилами безопасности. Кредит не списан. "
        "Если это ошибка, обратитесь в /support."
    ),
    Msg.MODERATION_RATE_LIMITED: (
        "⏳ Слишком много запросов за короткое время. Кредит не списан. Попробуйте позже."
    ),
    Msg.CMD_START: "Запустить KELBET AI",
    Msg.CMD_MENU: "Открыть главное меню",
    Msg.CMD_CREATE: "Создать изображение",
    Msg.CMD_VIDEO: "Создать видео",
    Msg.CMD_TRENDS: "Тренды: фото в вирусном стиле",
    Msg.CMD_CHAT: "Задать вопрос AI",
    Msg.CMD_HISTORY: "Открыть мои работы",
    Msg.CMD_BALANCE: "Проверить баланс",
    Msg.CMD_PROFILE: "Открыть профиль",
    Msg.CMD_SETTINGS: "Язык и настройки",
    Msg.CMD_SUPPORT: "Связаться с поддержкой",
    Msg.CMD_PAY_SUPPORT: "Помощь с оплатой",
    Msg.CMD_BUY: "Купить кредиты",
    Msg.CMD_TERMS: "Условия покупки",
    Msg.CMD_INVITE: "Пригласить друга",
    Msg.PAYMENT_UNAVAILABLE: (
        "⚙️ Оплата пока недоступна. Мы не принимаем деньги, пока условия "
        "и поддержка не настроены полностью."
    ),
    Msg.PAYMENT_CHOOSE: (
        "💳 <b>Пополнение баланса</b>\n\n"
        "Выберите пакет кредитов 👇\n\n"
        "<i>Нажимая кнопку пакета, вы подтверждаете согласие "
        "с условиями покупки.</i>"
    ),
    Msg.PAYMENT_PRODUCT_BUTTON: "{name} · {credits} 💎 · {stars} ⭐",
    Msg.PAYMENT_TERMS_OPEN: "📄 Условия покупки",
    Msg.PAYMENT_TERMS_ACCEPT: "✓ Принимаю актуальные условия",
    Msg.PAYMENT_TERMS_ACCEPTED: "Условия приняты. Выберите пакет кредитов:",
    Msg.PAYMENT_TERMS_TEXT: "📄 Условия покупки и возврата: {url}",
    Msg.PAYMENT_CREDITS_LABEL: "{credits} кредитов KELBET",
    Msg.PAYMENT_CHECKOUT_REJECTED: (
        "⚠️ Счёт устарел или его параметры изменились. Создайте новый через /buy."
    ),
    Msg.PAYMENT_SUCCESS: (
        "🎉 <b>Оплата получена!</b>\n\n"
        "⚡ Начислено: <b>{credits}</b> кредитов\n"
        "💎 Текущий баланс: <b>{balance}</b>"
    ),
    Msg.PAYMENT_REVIEW: (
        "⏳ Telegram подтвердил оплату, но начисление требует проверки.\n"
        "Напишите в /paysupport — платёж сохранён."
    ),
    Msg.SUBSCRIPTION_UNAVAILABLE: ("Подписки пока недоступны. Кредиты можно купить пакетом: /buy"),
    Msg.SUBSCRIPTION_CHOOSE: (
        "Подписка списывает звёзды раз в 30 дней и каждый раз начисляет кредиты. "
        "Отменить можно в любой момент — доступ останется до конца оплаченного периода. "
        "Неиспользованные кредиты не сгорают.\n\nВыберите тариф:"
    ),
    Msg.SUBSCRIPTION_PLAN_BUTTON: "{name} · {credits} 💎/мес · {stars} ⭐",
    Msg.SUBSCRIPTION_OPEN_PAYMENT: (
        "Тариф «{name}»: {credits} кредитов каждые 30 дней за {stars} ⭐.\n"
        "Нажмите кнопку ниже, чтобы оформить подписку."
    ),
    Msg.SUBSCRIPTION_PAY_BUTTON: "Оформить за {stars} ⭐",
    Msg.SUBSCRIPTION_ACTIVE: (
        "Тариф «{name}»: {credits} кредитов каждые 30 дней.\nСледующее списание: {until}."
    ),
    Msg.SUBSCRIPTION_NONE: "Активной подписки нет. Посмотреть тарифы: /subscribe",
    Msg.SUBSCRIPTION_STARTED: (
        "Подписка «{name}» оформлена. Начислено {credits} кредитов, на счету {balance}.\n"
        "Следующее списание: {until}."
    ),
    Msg.SUBSCRIPTION_RENEWED: (
        "Подписка «{name}» продлена. Начислено {credits} кредитов, на счету {balance}.\n"
        "Следующее списание: {until}."
    ),
    Msg.SUBSCRIPTION_REVIEW: (
        "Платёж получен, но подписку нужно проверить. Мы уже разбираемся, деньги не "
        "потеряются. Поддержка: /paysupport"
    ),
    Msg.SUBSCRIPTION_CANCEL_BUTTON: "Отменить продление",
    Msg.SUBSCRIPTION_CANCELLED: (
        "Продление отключено. Тариф и кредиты остаются до {until} — этот период уже оплачен."
    ),
    Msg.SUBSCRIPTION_RENEWAL_FAILED: (
        "Не удалось списать звёзды за продление тарифа «{name}». Доступ работает до "
        "{until}. Пополните баланс звёзд, чтобы не потерять тариф."
    ),
    Msg.CMD_SUBSCRIBE: "подписка с кредитами каждый месяц",
}
