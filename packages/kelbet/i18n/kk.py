from kelbet.i18n.keys import Msg

# Батырмалар (Reply/Inline) мен alert-попап мәтіндерінде HTML-тег болмауы тиіс:
# Telegram бұл жерлерде разметканы өңдемейді. HTML тек хабарлама мәтінінде қолданылады.
TEXTS: dict[str, str] = {
    Msg.START_CHOOSE_LANG: "🌐 Тілді таңдаңыз / Выберите язык:",
    Msg.START_WELCOME: (
        "✨ <b>KELBET AI-ға қош келдіңіз!</b>\n\n"
        "Telegram-дағы шығармашылық AI-студияңыз:\n\n"
        "🎨 Сурет генерациясы\n"
        "🎬 Видео жасау\n"
        "💬 Ақылды AI-чат\n\n"
        "🎁 Сізге <b>{credits} сәлемдесу кредиті</b> берілді ⚡\n\n"
        "👇 «Сурет жасау» батырмасын басып, идеяңызды сипаттаңыз — "
        "алғашқы жұмысыңызды алыңыз!"
    ),
    Msg.START_WELCOME_BACK: (
        "👋 <b>KELBET AI-ға қайта қош келдіңіз!</b>\n\nБүгін не жасағыңыз келеді? 👇"
    ),
    Msg.LANG_RU: "🇷🇺 Русский",
    Msg.LANG_KK: "🇰🇿 Қазақша",
    Msg.LANG_SET: "✅ Тіл сақталды: қазақша",
    Msg.MENU_CREATE: "🎨 Сурет жасау",
    Msg.MENU_VIDEO: "🎬 Видео жасау",
    Msg.MENU_TRENDS: "🔥 Трендтер",
    Msg.MENU_AI_CHAT: "💬 AI-чат",
    Msg.MENU_MY_WORKS: "📁 Менің жұмыстарым",
    Msg.MENU_TARIFFS: "💎 Тарифтер",
    Msg.MENU_PARTNERSHIP: "🤝 Серіктестік",
    Msg.MENU_PROFILE: "👤 Профиль",
    Msg.MENU_TITLE: "🏠 <b>Басты мәзір</b>\n\nБөлімді таңдаңыз 👇",
    Msg.MENU_BALANCE: "💰 Баланс",
    Msg.MENU_INVITE: "🎁 Дос шақыру",
    Msg.COMING_SOON: "🚧 Жақында қолжетімді болады. Біз бұл бағытта жұмыс істеп жатырмыз!",
    Msg.NEED_REGISTER: "👉 Алдымен /start басып, тілді таңдаңыз.",
    Msg.MINI_APP_OPEN: "🚀 <b>KELBET AI студиясы</b>\n\nСтудияны бір басып ашыңыз 👇",
    Msg.MINI_APP_UNAVAILABLE: (
        "⚙️ Mini App әлі бапталмаған.\nІске қосуға дайындалып жатырмыз — кейінірек қайталап көріңіз."
    ),
    Msg.MINI_APP_CREATE: "🎨 Image Studio ашу",
    Msg.MINI_APP_VIDEO: "🎬 Video Studio ашу",
    Msg.MINI_APP_TRENDS: "🔥 Трендтерді ашу",
    Msg.MINI_APP_HISTORY: "📁 Жұмыстарымды ашу",
    Msg.MINI_APP_PLANS: "💳 Балансты толтыру",
    Msg.VIDEO_MODEL_CHOOSE: (
        "🎬 <b>Модельді таңдаңыз</b>\n\nБағасы ұзақтығы мен сапасына байланысты 👇"
    ),
    Msg.VIDEO_MODEL_BUTTON: "{name} · {credits} кр.",
    Msg.VIDEO_MODEL_PAGE: "{page} / {total}",
    Msg.VIDEO_MODEL_PREV: "‹ Артқа",
    Msg.VIDEO_MODEL_NEXT: "Әрі ›",
    Msg.VIDEO_MODEL_PICKED: (
        "🎬 <b>{name}</b>\n{description}\n\n"
        "Бағасы: <b>{credits}</b> кредит — нақты сомасы ұзақтығы мен сапасына "
        "байланысты, оны іске қосу алдында көресіз."
    ),
    Msg.VIDEO_MODEL_OPEN: "Студияны ашу",
    Msg.VIDEO_MODEL_EMPTY: "Әзірге бейне модельдері қолжетімсіз. Кейінірек көріңіз.",
    Msg.VIDEO_MODEL_GONE: "Бұл модель енді қолжетімсіз. Тізімді қайта ашыңыз.",
    Msg.BALANCE_TITLE: "💰 <b>Сіздің балансыңыз</b>",
    Msg.BALANCE_TOTAL: "💎 Барлығы: <b>{balance}</b> кредит",
    Msg.BALANCE_RESERVED: "⏳ Жұмыста: {reserved}",
    Msg.BALANCE_AVAILABLE: "✅ Қолжетімді: <b>{available}</b>",
    Msg.BALANCE_TOP_UP: "💳 Толтыру",
    Msg.SETTINGS_TITLE: "⚙️ <b>Баптаулар</b>",
    Msg.SETTINGS_LANGUAGE: "🌐 Интерфейс тілін таңдаңыз:",
    Msg.SUPPORT_TEXT: (
        "🛟 <b>Қолдау қызметі</b>\n\n"
        "Сұрағыңызды бір хабарламамен жазыңыз. Мәселе генерацияға қатысты болса, "
        "оның ID нөмірін тіркеңіз."
    ),
    Msg.PAY_SUPPORT_TEXT: (
        "💳 <b>Төлем бойынша көмек</b>\n\n"
        "Күнін, сомасын және Telegram ID көрсетіңіз.\n"
        "⚠️ Карта деректерін жібермеңіз."
    ),
    Msg.SUPPORT_OPEN: "✍️ Қолдауға жазу",
    Msg.SUPPORT_UNAVAILABLE: (
        "⚙️ Қолдау қызметі әлі бапталмаған. Кейінірек қайталаңыз — кредиттеріңіз сақталады."
    ),
    Msg.INVITE_COMING_SOON: (
        "🎁 <b>Рефералдық бағдарлама жақында ашылады!</b>\n\n"
        "Достарыңызды шақырып, бонус кредиттер алыңыз. "
        "Бонус тек нақты достар үшін беріледі."
    ),
    Msg.INVITE_SUMMARY: (
        "🎁 <b>Достарыңызды шақырыңыз</b>\n\n"
        "Сілтемеңіз: <code>{link}</code>\n\n"
        "👥 Шақырылғандар: <b>{invited}</b>\n"
        "⏳ Бонус күтіп тұр: <b>{pending}</b>\n"
        "💎 Есептелді: <b>{credited}</b> кредит\n\n"
        "{inviter_bonus} кредит бонус досыңыздың кемінде {minimum} Stars сомасындағы "
        "алғашқы расталған сатып алуынан және {waiting} сағ. күту мерзімінен кейін "
        "беріледі. Қайтарым немесе дау есептелмеген бонусты жояды."
    ),
    Msg.INVITE_SHARE: "📤 Сілтемені бөлісу",
    Msg.INVITE_OPEN: "🎁 Бағдарламаны ашу",
    Msg.PROFILE_TITLE: "👤 <b>Сіздің профиліңіз</b>\n",
    Msg.PROFILE_TELEGRAM_ID: "🆔 Telegram ID: <code>{telegram_id}</code>",
    Msg.PROFILE_USERNAME: "📛 Username: {username}",
    Msg.PROFILE_LANGUAGE: "🌐 Тіл: {language}",
    Msg.PROFILE_BALANCE: "💎 Баланс: <b>{balance}</b>",
    Msg.PROFILE_PLAN: "⭐ Тариф: {plan}",
    Msg.PROFILE_NO_USERNAME: "көрсетілмеген",
    Msg.PLAN_FREE: "Free",
    Msg.CHAT_PROMPT: (
        "💬 <b>AI-чат</b>\n\n"
        "Сұрағыңызды жазыңыз — қазақша, орысша немесе аралас хабарларға "
        "жауап беремін 👇"
    ),
    Msg.CHAT_CANCEL: "❌ Болдырмау",
    Msg.CHAT_ASK_AGAIN: "🔄 Тағы сұрау",
    Msg.CHAT_MAIN_MENU: "🏠 Басты мәзір",
    Msg.CHAT_CANCELLED: "✅ Чат аяқталды. Сіз басты мәзірдесіз.",
    Msg.CHAT_INSUFFICIENT: (
        "😔 <b>Кредит жеткіліксіз</b>\n\n"
        "Кемінде {cost} керек, сізде {balance}.\n"
        "⚡ Балансты толтыру: /buy"
    ),
    Msg.CHAT_PROVIDER_ERROR: (
        "⚠️ AI жауабын алу мүмкін болмады.\nКредит шегерілмеді. Қайта көріңіз."
    ),
    Msg.CHAT_TOO_LONG: "✂️ Хабар тым ұзын. Ең көбі {max_chars} таңба.",
    Msg.CHAT_EMPTY: "💬 Сұрақ бар мәтіндік хабар жіберіңіз.",
    Msg.CHAT_NEED_REGISTER: "👉 Алдымен /start басып, тілді таңдаңыз.",
    Msg.CHAT_BALANCE_LEFT: "💎 Қалған кредит: <b>{balance}</b>",
    Msg.MODERATION_BLOCKED: (
        "⚠️ Сұрау қауіпсіздік ережелері бойынша тоқтатылды. Кредит шегерілмеді. "
        "Бұл қате болса, /support бөліміне жазыңыз."
    ),
    Msg.MODERATION_RATE_LIMITED: (
        "⏳ Қысқа уақытта тым көп сұрау жіберілді. Кредит шегерілмеді. Кейінірек қайталаңыз."
    ),
    Msg.CMD_START: "KELBET AI іске қосу",
    Msg.CMD_MENU: "Басты мәзірді ашу",
    Msg.CMD_CREATE: "Сурет жасау",
    Msg.CMD_VIDEO: "Видео жасау",
    Msg.CMD_TRENDS: "Трендтер: фотоны вирусты стильге",
    Msg.CMD_CHAT: "AI-ға сұрақ қою",
    Msg.CMD_HISTORY: "Жұмыстарымды ашу",
    Msg.CMD_BALANCE: "Балансты тексеру",
    Msg.CMD_PROFILE: "Профильді ашу",
    Msg.CMD_SETTINGS: "Тіл және баптаулар",
    Msg.CMD_SUPPORT: "Қолдау қызметіне жазу",
    Msg.CMD_PAY_SUPPORT: "Төлем бойынша көмек",
    Msg.CMD_BUY: "Кредит сатып алу",
    Msg.CMD_TERMS: "Сатып алу шарттары",
    Msg.CMD_INVITE: "Дос шақыру",
    Msg.PAYMENT_UNAVAILABLE: (
        "⚙️ Төлем әзірге қолжетімсіз. Шарттар мен қолдау толық бапталғанша ақша қабылдамаймыз."
    ),
    Msg.PAYMENT_CHOOSE: (
        "💳 <b>Балансты толтыру</b>\n\n"
        "Кредит пакетін таңдаңыз 👇\n\n"
        "<i>Пакет батырмасын басу арқылы сатып алу шарттарына келісесіз.</i>"
    ),
    Msg.PAYMENT_PRODUCT_BUTTON: "{name} · {credits} 💎 · {stars} ⭐",
    Msg.PAYMENT_TERMS_OPEN: "📄 Сатып алу шарттары",
    Msg.PAYMENT_TERMS_ACCEPT: "✓ Қолданыстағы шарттарды қабылдаймын",
    Msg.PAYMENT_TERMS_ACCEPTED: "Шарттар қабылданды. Кредит пакетін таңдаңыз:",
    Msg.PAYMENT_TERMS_TEXT: "📄 Сатып алу және қайтару шарттары: {url}",
    Msg.PAYMENT_CREDITS_LABEL: "{credits} KELBET кредиті",
    Msg.PAYMENT_CHECKOUT_REJECTED: (
        "⚠️ Шоттың мерзімі өтті немесе параметрлері өзгерді. /buy арқылы жаңасын жасаңыз."
    ),
    Msg.PAYMENT_SUCCESS: (
        "🎉 <b>Төлем қабылданды!</b>\n\n"
        "⚡ Қосылды: <b>{credits}</b> кредит\n"
        "💎 Ағымдағы баланс: <b>{balance}</b>"
    ),
    Msg.PAYMENT_REVIEW: (
        "⏳ Telegram төлемді растады, бірақ кредитті қосу тексеруді қажет етеді.\n"
        "/paysupport қызметіне жазыңыз — төлем сақталды."
    ),
    Msg.SUBSCRIPTION_UNAVAILABLE: (
        "Жазылым әзірге қолжетімсіз. Кредитті пакетпен алуға болады: /buy"
    ),
    Msg.SUBSCRIPTION_CHOOSE: (
        "Жазылым 30 күнде бір рет жұлдыз шешіп, әр жолы кредит қосады. "
        "Кез келген уақытта тоқтатуға болады — төленген кезең соңына дейін қолжетімділік "
        "қалады. Жұмсалмаған кредит жойылмайды.\n\nТарифті таңдаңыз:"
    ),
    Msg.SUBSCRIPTION_PLAN_BUTTON: "{name} · {credits} 💎/ай · {stars} ⭐",
    Msg.SUBSCRIPTION_OPEN_PAYMENT: (
        "«{name}» тарифі: 30 күн сайын {stars} ⭐ үшін {credits} кредит.\n"
        "Жазылу үшін төмендегі түймені басыңыз."
    ),
    Msg.SUBSCRIPTION_PAY_BUTTON: "{stars} ⭐ үшін жазылу",
    Msg.SUBSCRIPTION_ACTIVE: (
        "«{name}» тарифі: 30 күн сайын {credits} кредит.\nКелесі төлем: {until}."
    ),
    Msg.SUBSCRIPTION_NONE: "Белсенді жазылым жоқ. Тарифтерді көру: /subscribe",
    Msg.SUBSCRIPTION_STARTED: (
        "«{name}» жазылымы рәсімделді. {credits} кредит қосылды, шотта {balance}.\n"
        "Келесі төлем: {until}."
    ),
    Msg.SUBSCRIPTION_RENEWED: (
        "«{name}» жазылымы жаңартылды. {credits} кредит қосылды, шотта {balance}.\n"
        "Келесі төлем: {until}."
    ),
    Msg.SUBSCRIPTION_REVIEW: (
        "Төлем қабылданды, бірақ жазылымды тексеру қажет. Біз тексеріп жатырмыз, ақша "
        "жоғалмайды. Қолдау: /paysupport"
    ),
    Msg.SUBSCRIPTION_CANCEL_BUTTON: "Жаңартуды тоқтату",
    Msg.SUBSCRIPTION_CANCELLED: (
        "Жаңарту өшірілді. Тариф пен кредит {until} дейін сақталады — бұл кезең төленген."
    ),
    Msg.SUBSCRIPTION_RENEWAL_FAILED: (
        "«{name}» тарифін жаңарту үшін жұлдыз шешілмеді. Қолжетімділік {until} дейін "
        "жұмыс істейді. Тарифті жоғалтпау үшін жұлдыз балансын толтырыңыз."
    ),
    Msg.CMD_SUBSCRIBE: "ай сайын кредит алуға жазылу",
}
