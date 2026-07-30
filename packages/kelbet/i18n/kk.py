from kelbet.i18n.keys import Msg

TEXTS: dict[str, str] = {
    Msg.START_CHOOSE_LANG: "Тілді таңдаңыз / Выберите язык:",
    Msg.START_WELCOME: (
        "KELBET AI-ға қош келдіңіз!\n\n"
        "Сізге {credits} сәлемдесу кредиті берілді.\n"
        "«Жасау» батырмасын басып, идеяңызды сипаттап, алғашқы жұмысыңызды алыңыз."
    ),
    Msg.START_WELCOME_BACK: "KELBET AI-ға қайта қош келдіңіз! Қажетті әрекетті таңдаңыз.",
    Msg.LANG_RU: "Русский",
    Msg.LANG_KK: "Қазақша",
    Msg.LANG_SET: "Тіл сақталды: қазақша",
    Msg.MENU_CREATE: "Сурет жасау",
    Msg.MENU_VIDEO: "Видео жасау",
    Msg.MENU_AI_CHAT: "AI-чат",
    Msg.MENU_MY_WORKS: "Менің жұмыстарым",
    Msg.MENU_TARIFFS: "Тарифтер",
    Msg.MENU_PARTNERSHIP: "Серіктестік",
    Msg.MENU_PROFILE: "Профиль",
    Msg.MENU_TITLE: "Басты мәзір",
    Msg.MENU_BALANCE: "Баланс",
    Msg.MENU_INVITE: "Дос шақыру",
    Msg.COMING_SOON: "Жақында қолжетімді болады.",
    Msg.NEED_REGISTER: "Алдымен /start басып, тілді таңдаңыз.",
    Msg.MINI_APP_OPEN: "KELBET AI студиясын ашыңыз:",
    Msg.MINI_APP_UNAVAILABLE: (
        "Mini App әлі бапталмаған. Іске қосуға дайындалып жатырмыз — кейінірек қайталап көріңіз."
    ),
    Msg.MINI_APP_CREATE: "Image Studio ашу",
    Msg.MINI_APP_VIDEO: "Video Studio ашу",
    Msg.MINI_APP_HISTORY: "Жұмыстарымды ашу",
    Msg.MINI_APP_PLANS: "Балансты толтыру",
    Msg.BALANCE_TITLE: "Сіздің балансыңыз",
    Msg.BALANCE_TOTAL: "Барлығы: {balance} кредит",
    Msg.BALANCE_RESERVED: "Жұмыста: {reserved}",
    Msg.BALANCE_AVAILABLE: "Қолжетімді: {available}",
    Msg.BALANCE_TOP_UP: "Толтыру",
    Msg.SETTINGS_TITLE: "Баптаулар",
    Msg.SETTINGS_LANGUAGE: "Интерфейс тілін таңдаңыз:",
    Msg.SUPPORT_TEXT: (
        "Сұрағыңызды бір хабарламамен жазыңыз. Мәселе генерацияға қатысты болса, "
        "оның ID нөмірін тіркеңіз."
    ),
    Msg.PAY_SUPPORT_TEXT: (
        "Төлем сұрағы бойынша күнін, сомасын және Telegram ID көрсетіңіз. "
        "Карта деректерін жібермеңіз."
    ),
    Msg.SUPPORT_OPEN: "Қолдауға жазу",
    Msg.SUPPORT_UNAVAILABLE: (
        "Қолдау қызметі әлі бапталмаған. Кейінірек қайталаңыз — кредиттеріңіз сақталады."
    ),
    Msg.INVITE_COMING_SOON: (
        "Рефералдық бағдарлама жақында ашылады. Бонус тек нақты достар үшін беріледі."
    ),
    Msg.PROFILE_TITLE: "Сіздің профиліңіз",
    Msg.PROFILE_TELEGRAM_ID: "Telegram ID: {telegram_id}",
    Msg.PROFILE_USERNAME: "Username: {username}",
    Msg.PROFILE_LANGUAGE: "Тіл: {language}",
    Msg.PROFILE_BALANCE: "Баланс: {balance}",
    Msg.PROFILE_PLAN: "Тариф: {plan}",
    Msg.PROFILE_NO_USERNAME: "көрсетілмеген",
    Msg.PLAN_FREE: "Free",
    Msg.CHAT_PROMPT: ("Сұрағыңызды жазыңыз. Мен орысша, қазақша және аралас хабарларды түсінемін."),
    Msg.CHAT_CANCEL: "Болдырмау",
    Msg.CHAT_ASK_AGAIN: "Тағы сұрау",
    Msg.CHAT_MAIN_MENU: "Басты мәзір",
    Msg.CHAT_CANCELLED: "Чат болдырылмады. Сіз басты мәзірдесіз.",
    Msg.CHAT_INSUFFICIENT: "Кредит жеткіліксіз. Кемінде {cost} керек, сізде {balance}.",
    Msg.CHAT_PROVIDER_ERROR: ("AI жауабын алу мүмкін болмады. Кредит шегерілмеді. Қайта көріңіз."),
    Msg.CHAT_TOO_LONG: "Хабар тым ұзын. Ең көбі {max_chars} таңба.",
    Msg.CHAT_EMPTY: "Сұрақ бар мәтіндік хабар жіберіңіз.",
    Msg.CHAT_NEED_REGISTER: "Алдымен /start басып, тілді таңдаңыз.",
    Msg.CHAT_BALANCE_LEFT: "Қалған кредит: {balance}",
    Msg.CMD_START: "KELBET AI іске қосу",
    Msg.CMD_MENU: "Басты мәзірді ашу",
    Msg.CMD_CREATE: "Сурет жасау",
    Msg.CMD_VIDEO: "Видео жасау",
    Msg.CMD_CHAT: "AI-ға сұрақ қою",
    Msg.CMD_HISTORY: "Жұмыстарымды ашу",
    Msg.CMD_BALANCE: "Балансты тексеру",
    Msg.CMD_PROFILE: "Профильді ашу",
    Msg.CMD_SETTINGS: "Тіл және баптаулар",
    Msg.CMD_SUPPORT: "Қолдау қызметіне жазу",
    Msg.CMD_PAY_SUPPORT: "Төлем бойынша көмек",
    Msg.CMD_BUY: "Кредит сатып алу",
    Msg.CMD_TERMS: "Сатып алу шарттары",
    Msg.PAYMENT_UNAVAILABLE: (
        "Төлем әзірге қолжетімсіз. Шарттар мен қолдау толық бапталғанша ақша қабылдамаймыз."
    ),
    Msg.PAYMENT_CHOOSE: (
        "Пакетті таңдаңыз. Пакет батырмасын басу арқылы сатып алу шарттарына келісесіз."
    ),
    Msg.PAYMENT_PRODUCT_BUTTON: "{name} · {credits} кредит · {stars} ⭐",
    Msg.PAYMENT_TERMS_OPEN: "Сатып алу шарттарын ашу",
    Msg.PAYMENT_TERMS_TEXT: "Сатып алу және қайтару шарттары: {url}",
    Msg.PAYMENT_CREDITS_LABEL: "{credits} KELBET кредиті",
    Msg.PAYMENT_CHECKOUT_REJECTED: (
        "Шоттың мерзімі өтті немесе параметрлері өзгерді. /buy арқылы жаңасын жасаңыз."
    ),
    Msg.PAYMENT_SUCCESS: (
        "Төлем қабылданды. {credits} кредит қосылды.\nАғымдағы баланс: {balance}."
    ),
    Msg.PAYMENT_REVIEW: (
        "Telegram төлемді растады, бірақ кредитті қосу тексеруді қажет етеді. "
        "/paysupport қызметіне жазыңыз — төлем сақталды."
    ),
}
