from kelbet.i18n.keys import Msg

TEXTS: dict[str, str] = {
    Msg.START_CHOOSE_LANG: "Выберите язык / Тілді таңдаңыз:",
    Msg.START_WELCOME: (
        "Добро пожаловать в KELBET AI!\n\n"
        "Вам начислено {credits} приветственных кредитов.\n"
        "Нажмите «Создать», опишите идею и получите первую работу."
    ),
    Msg.START_WELCOME_BACK: "С возвращением в KELBET AI! Выберите, что хотите сделать.",
    Msg.LANG_RU: "Русский",
    Msg.LANG_KK: "Қазақша",
    Msg.LANG_SET: "Язык сохранён: русский",
    Msg.MENU_CREATE: "Создать изображение",
    Msg.MENU_VIDEO: "Создать видео",
    Msg.MENU_AI_CHAT: "AI-чат",
    Msg.MENU_MY_WORKS: "Мои работы",
    Msg.MENU_TARIFFS: "Тарифы",
    Msg.MENU_PARTNERSHIP: "Партнёрство",
    Msg.MENU_PROFILE: "Профиль",
    Msg.MENU_TITLE: "Главное меню",
    Msg.MENU_BALANCE: "Баланс",
    Msg.MENU_INVITE: "Пригласить друга",
    Msg.COMING_SOON: "Скоро будет доступно.",
    Msg.NEED_REGISTER: "Сначала нажмите /start и выберите язык.",
    Msg.MINI_APP_OPEN: "Откройте студию KELBET AI:",
    Msg.MINI_APP_UNAVAILABLE: (
        "Mini App пока не настроен. Мы уже работаем над запуском — попробуйте немного позже."
    ),
    Msg.MINI_APP_CREATE: "Открыть Image Studio",
    Msg.MINI_APP_VIDEO: "Открыть Video Studio",
    Msg.MINI_APP_HISTORY: "Открыть мои работы",
    Msg.MINI_APP_PLANS: "Пополнить баланс",
    Msg.BALANCE_TITLE: "Ваш баланс",
    Msg.BALANCE_TOTAL: "Всего: {balance} кредитов",
    Msg.BALANCE_RESERVED: "В работе: {reserved}",
    Msg.BALANCE_AVAILABLE: "Доступно: {available}",
    Msg.BALANCE_TOP_UP: "Пополнить",
    Msg.SETTINGS_TITLE: "Настройки",
    Msg.SETTINGS_LANGUAGE: "Выберите язык интерфейса:",
    Msg.SUPPORT_TEXT: (
        "Опишите вопрос одним сообщением. Если проблема связана с генерацией, "
        "приложите её ID."
    ),
    Msg.PAY_SUPPORT_TEXT: (
        "По вопросам оплаты укажите дату, сумму и Telegram ID. Не отправляйте данные карты."
    ),
    Msg.SUPPORT_OPEN: "Написать в поддержку",
    Msg.SUPPORT_UNAVAILABLE: (
        "Поддержка пока не настроена. Повторите попытку позже — ваши кредиты сохранятся."
    ),
    Msg.INVITE_COMING_SOON: (
        "Реферальная программа скоро откроется. Бонус начислим только за реальных друзей."
    ),
    Msg.PROFILE_TITLE: "Ваш профиль",
    Msg.PROFILE_TELEGRAM_ID: "Telegram ID: {telegram_id}",
    Msg.PROFILE_USERNAME: "Username: {username}",
    Msg.PROFILE_LANGUAGE: "Язык: {language}",
    Msg.PROFILE_BALANCE: "Баланс: {balance}",
    Msg.PROFILE_PLAN: "Тариф: {plan}",
    Msg.PROFILE_NO_USERNAME: "не указан",
    Msg.PLAN_FREE: "Free",
    Msg.CHAT_PROMPT: ("Напишите ваш вопрос. Я понимаю русский, қазақша и смешанные сообщения."),
    Msg.CHAT_CANCEL: "Отмена",
    Msg.CHAT_ASK_AGAIN: "Ещё вопрос",
    Msg.CHAT_MAIN_MENU: "Главное меню",
    Msg.CHAT_CANCELLED: "Чат отменён. Вы в главном меню.",
    Msg.CHAT_INSUFFICIENT: ("Недостаточно кредитов. Нужен минимум {cost}, у вас {balance}."),
    Msg.CHAT_PROVIDER_ERROR: (
        "Не удалось получить ответ AI. Кредит не списан. Попробуйте ещё раз."
    ),
    Msg.CHAT_TOO_LONG: "Сообщение слишком длинное. Максимум {max_chars} символов.",
    Msg.CHAT_EMPTY: "Отправьте текстовое сообщение с вопросом.",
    Msg.CHAT_NEED_REGISTER: "Сначала нажмите /start и выберите язык.",
    Msg.CHAT_BALANCE_LEFT: "Остаток кредитов: {balance}",
    Msg.CMD_START: "Запустить KELBET AI",
    Msg.CMD_MENU: "Открыть главное меню",
    Msg.CMD_CREATE: "Создать изображение",
    Msg.CMD_VIDEO: "Создать видео",
    Msg.CMD_CHAT: "Задать вопрос AI",
    Msg.CMD_HISTORY: "Открыть мои работы",
    Msg.CMD_BALANCE: "Проверить баланс",
    Msg.CMD_PROFILE: "Открыть профиль",
    Msg.CMD_SETTINGS: "Язык и настройки",
    Msg.CMD_SUPPORT: "Связаться с поддержкой",
    Msg.CMD_PAY_SUPPORT: "Помощь с оплатой",
    Msg.CMD_BUY: "Купить кредиты",
    Msg.CMD_TERMS: "Условия покупки",
    Msg.PAYMENT_UNAVAILABLE: (
        "Оплата пока недоступна. Мы не принимаем деньги, пока условия и поддержка "
        "не настроены полностью."
    ),
    Msg.PAYMENT_CHOOSE: (
        "Выберите пакет. Нажимая кнопку пакета, вы подтверждаете согласие с условиями покупки."
    ),
    Msg.PAYMENT_PRODUCT_BUTTON: "{name} · {credits} кредитов · {stars} ⭐",
    Msg.PAYMENT_TERMS_OPEN: "Открыть условия покупки",
    Msg.PAYMENT_TERMS_TEXT: "Условия покупки и возврата: {url}",
    Msg.PAYMENT_CREDITS_LABEL: "{credits} кредитов KELBET",
    Msg.PAYMENT_CHECKOUT_REJECTED: (
        "Счёт устарел или его параметры изменились. Создайте новый через /buy."
    ),
    Msg.PAYMENT_SUCCESS: (
        "Оплата получена. Начислено {credits} кредитов.\nТекущий баланс: {balance}."
    ),
    Msg.PAYMENT_REVIEW: (
        "Telegram подтвердил оплату, но начисление требует проверки. "
        "Напишите в /paysupport — платёж сохранён."
    ),
}
