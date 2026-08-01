import type { Language } from "../../shared/api/types";

export const SUPPORT_COMMAND = "/support";

export const supportCopy: Record<Language, {
  eyebrow: string;
  title: string;
  body: string;
  stepChat: string;
  stepCommand: string;
  copy: string;
  copied: string;
  copyFailed: string;
  returnToChat: string;
  browserNote: string;
  back: string;
}> = {
  ru: {
    eyebrow: "KELBET / ПОДДЕРЖКА",
    title: "Связаться с командой",
    body: "Поддержка работает в том же Telegram-чате с ботом, из которого вы открыли KELBET.",
    stepChat: "Вернитесь в Telegram-чат с ботом KELBET.",
    stepCommand: "Отправьте команду /support отдельным сообщением.",
    copy: "Скопировать команду",
    copied: "Команда скопирована",
    copyFailed: "Не удалось скопировать автоматически. Выделите команду вручную.",
    returnToChat: "Вернуться в чат Telegram",
    browserNote: "Если KELBET открыт в браузере, найдите чат с ботом вручную.",
    back: "Назад в профиль",
  },
  kk: {
    eyebrow: "KELBET / ҚОЛДАУ",
    title: "Командаға хабарласу",
    body: "Қолдау KELBET ашылған Telegram-дағы сол бот чатында жұмыс істейді.",
    stepChat: "Telegram-дағы KELBET бот чатына оралыңыз.",
    stepCommand: "/support командасын жеке хабарлама ретінде жіберіңіз.",
    copy: "Команданы көшіру",
    copied: "Команда көшірілді",
    copyFailed: "Автоматты көшіру мүмкін болмады. Команданы қолмен белгілеңіз.",
    returnToChat: "Telegram чатына оралу",
    browserNote: "KELBET браузерде ашылса, бот чатын қолмен табыңыз.",
    back: "Профильге оралу",
  },
};
