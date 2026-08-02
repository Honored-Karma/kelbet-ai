import type { Language } from "../api/types";

/**
 * Page-scoped copy for the profile screen.
 *
 * These strings belong in `messages.ts` next to the rest of the dictionary.
 * They live here only because `messages.ts` has grown past the point where it
 * can be edited through the GitHub contents API, which rewrites whole files.
 * Fold them into the main dictionary on the next local pass and delete this
 * module — nothing else imports it.
 */
const ru = {
  walletAvailable: "доступно",
  walletTotal: "всего на счету",
  walletReserved: "в резерве",
  walletActive: "в работе",
  walletReservedHint: "Резерв держится, пока идёт генерация. Если она не удастся, кредиты вернутся на счёт.",
  walletHistory: "История",

  activityEyebrow: "Осы айда",
  activityTitle: "За 30 дней",
  activityImages: "изображений",
  activityVideos: "видео",
  activityCredits: "кредитов",
  activityAll: "Вся история",
  activityEmpty: "Здесь появятся ваши работы",
  activityStart: "Создать первую",

  referralEyebrow: "Серіктестік",
  referralTitle: "Партнёрская программа",
  referralInvited: "приглашено",
  referralEarned: "начислено",
  referralPending: "ожидают",
  referralCopy: "Копировать",
  referralCopied: "Скопировано",
  referralReward: "За друга вы получаете {inviter} кредитов, друг — {invitee}.",
  referralCondition: "Награда приходит после первой покупки друга от {stars} звёзд, через {hours} ч.",
  referralOff: "Программа скоро откроется",
  referralOffHint: "Мы включим приглашения в одном из ближайших обновлений.",

  refundPolicy: "Политика возвратов",
  refundPolicyHelp: "Условия возврата звёзд и кредитов",
} as const;

export type ProfileCopyKey = keyof typeof ru;

const kk: Record<ProfileCopyKey, string> = {
  walletAvailable: "қолжетімді",
  walletTotal: "шотта барлығы",
  walletReserved: "резервте",
  walletActive: "жұмыста",
  walletReservedHint: "Генерация жүріп жатқанда резерв ұсталады. Сәтсіз аяқталса, кредиттер шотқа қайтады.",
  walletHistory: "Тарих",

  activityEyebrow: "Осы айда",
  activityTitle: "30 күн ішінде",
  activityImages: "сурет",
  activityVideos: "бейне",
  activityCredits: "кредит",
  activityAll: "Барлық тарих",
  activityEmpty: "Мұнда сіздің жұмыстарыңыз көрінеді",
  activityStart: "Алғашқысын жасау",

  referralEyebrow: "Серіктестік",
  referralTitle: "Серіктестік бағдарламасы",
  referralInvited: "шақырылды",
  referralEarned: "есептелді",
  referralPending: "күтілуде",
  referralCopy: "Көшіру",
  referralCopied: "Көшірілді",
  referralReward: "Дос үшін сіз {inviter} кредит аласыз, досыңыз — {invitee}.",
  referralCondition: "Сыйақы дос {stars} жұлдыздан бастап алғаш сатып алғаннан кейін, {hours} сағаттан соң келеді.",
  referralOff: "Бағдарлама жақында ашылады",
  referralOffHint: "Шақыруларды жақын жаңартулардың бірінде қосамыз.",

  refundPolicy: "Қайтару саясаты",
  refundPolicyHelp: "Жұлдыздар мен кредиттерді қайтару шарттары",
};

const profileCopy: Record<Language, Record<ProfileCopyKey, string>> = { ru, kk };

export function profileText(
  language: Language,
  key: ProfileCopyKey,
  vars?: Record<string, string | number>,
): string {
  const template = profileCopy[language][key];
  if (!vars) return template;
  return Object.entries(vars).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template,
  );
}
