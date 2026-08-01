import type { GenerationTemplate, Language } from "../../shared/api/types";

export type CreateIntentHint = "scratch" | "photo";

export type CreateTemplate = {
  id: string;
  glyph: string;
  title: Record<Language, string>;
  description: Record<Language, string>;
  prompt: Record<Language, string>;
  aspectRatio: string;
  intentHint?: CreateIntentHint;
};

export const CREATE_TEMPLATES: CreateTemplate[] = [
  {
    id: "marketplace-product",
    glyph: "▱",
    title: { ru: "Карточка товара", kk: "Тауар карточкасы" },
    description: {
      ru: "Чистый кадр для местного маркетплейса",
      kk: "Жергілікті маркетплейске арналған таза кадр",
    },
    prompt: {
      ru: "Премиальная карточка товара: предмет в центре, светлый нейтральный фон, мягкая естественная тень, реалистичные материалы, чистая коммерческая композиция",
      kk: "Премиум тауар карточкасы: зат ортада, ашық бейтарап фон, жұмсақ табиғи көлеңке, шынайы материалдар, таза коммерциялық композиция",
    },
    aspectRatio: "1:1",
    intentHint: "photo",
  },
  {
    id: "cafe-promo",
    glyph: "◒",
    title: { ru: "Кафе и доставка", kk: "Кафе және жеткізу" },
    description: {
      ru: "Аппетитный промо-кадр для меню",
      kk: "Мәзірге арналған тәбетті промо-кадр",
    },
    prompt: {
      ru: "Аппетитный рекламный кадр блюда для городского кафе в Казахстане, тёплый направленный свет, свежие ингредиенты, аккуратная сервировка, место для короткого заголовка",
      kk: "Қазақстандағы қалалық кафеге арналған тәбетті тағам жарнамасы, жылы бағытталған жарық, балғын өнімдер, ұқыпты ұсыну, қысқа тақырыпқа бос орын",
    },
    aspectRatio: "1:1",
    intentHint: "photo",
  },
  {
    id: "local-service-story",
    glyph: "▯",
    title: { ru: "Сторис для услуги", kk: "Қызметке сторис" },
    description: {
      ru: "Вертикальный анонс для локального бизнеса",
      kk: "Жергілікті бизнеске тік анонс",
    },
    prompt: {
      ru: "Вертикальный рекламный сторис для локального сервиса в Алматы или Астане, уверенная современная композиция, живой городской контекст, свободные зоны для цены и контактов",
      kk: "Алматы немесе Астанадағы жергілікті қызметке арналған тік жарнамалық сторис, заманауи сенімді композиция, жанды қала ортасы, баға мен байланысқа бос аймақтар",
    },
    aspectRatio: "9:16",
  },
  {
    id: "kazakh-fashion",
    glyph: "◇",
    title: { ru: "Новая казахская мода", kk: "Жаңа қазақ сәні" },
    description: {
      ru: "Современный editorial без костюмных клише",
      kk: "Костюмдік клишесіз заманауи editorial",
    },
    prompt: {
      ru: "Современная fashion-съёмка молодого казахстанского бренда, выразительный силуэт, натуральные ткани и архитектурный свет, актуальный городской editorial без этнографических костюмных клише",
      kk: "Жас қазақстандық брендтің заманауи fashion түсірілімі, айқын силуэт, табиғи маталар мен сәулеттік жарық, этнографиялық костюм клишесінсіз өзекті қалалық editorial",
    },
    aspectRatio: "9:16",
    intentHint: "photo",
  },
  {
    id: "real-estate",
    glyph: "⌂",
    title: { ru: "Интерьер и недвижимость", kk: "Интерьер және баспана" },
    description: {
      ru: "Светлый кадр для объявления",
      kk: "Хабарландыруға арналған жарық кадр",
    },
    prompt: {
      ru: "Светлый реалистичный интерьер современной квартиры в Казахстане, широкоугольная композиция без искажений, естественный дневной свет, аккуратный декор, ощущение пространства и уюта",
      kk: "Қазақстандағы заманауи пәтердің жарық әрі шынайы интерьері, бұрмаланусыз кең бұрышты композиция, табиғи күндізгі жарық, ұқыпты декор, кеңістік пен жайлылық сезімі",
    },
    aspectRatio: "16:9",
    intentHint: "photo",
  },
  {
    id: "nauryz",
    glyph: "✦",
    title: { ru: "Наурыз", kk: "Наурыз" },
    description: {
      ru: "Тёплая современная открытка",
      kk: "Жылы заманауи ашықхат",
    },
    prompt: {
      ru: "Современная открытка к Наурызу: весенний свет, тёплая гостеприимная атмосфера, натуральные материалы, свежая зелень и изящная композиция с местом для поздравления",
      kk: "Наурызға арналған заманауи ашықхат: көктемгі жарық, жылы қонақжай көңіл күй, табиғи материалдар, балғын жасыл реңк және құттықтау мәтініне орын",
    },
    aspectRatio: "1:1",
  },
];

const MOCK_IMAGE_TEMPLATE_IDS = [
  "22222222-2222-2222-2222-222222222201",
  "22222222-2222-2222-2222-222222222202",
  "22222222-2222-2222-2222-222222222203",
  "22222222-2222-2222-2222-222222222204",
  "22222222-2222-2222-2222-222222222205",
  "22222222-2222-2222-2222-222222222206",
] as const;

/** Checked-in preview data is intentionally reachable only in explicit mock mode. */
export function mockImageTemplates(language: Language): GenerationTemplate[] {
  return CREATE_TEMPLATES.map((template, index) => ({
    id: MOCK_IMAGE_TEMPLATE_IDS[index]!,
    slug: template.id,
    version: 1,
    kind: "image",
    display_order: index + 10,
    localization: {
      name: template.title[language],
      description: template.description[language],
    },
    prompt_preset: template.prompt[language],
    aspect_ratio: template.aspectRatio,
    duration_sec: null,
    compatible_modalities:
      template.id === "local-service-story" || template.id === "nauryz"
        ? ["image"]
        : ["image", "image_edit"],
    required_inputs: {
      assets: { min: 0, max: 4 },
      fields:
        template.id === "marketplace-product"
          ? [
              { key: "headline", type: "text", required: true, max_length: 80, label: language === "ru" ? "Название" : "Атауы" },
              { key: "body", type: "text", required: false, max_length: 120, label: language === "ru" ? "Описание" : "Сипаттама" },
              { key: "price", type: "text", required: true, max_length: 32, label: language === "ru" ? "Цена" : "Бағасы" },
              { key: "contact", type: "text", required: true, max_length: 80, label: language === "ru" ? "Контакт" : "Байланыс" },
            ]
          : [],
    },
    preview_metadata: { marker: template.glyph, source: "mock-local-v1" },
    compositor: template.id === "marketplace-product" ? "product_card_v1" : null,
  }));
}
