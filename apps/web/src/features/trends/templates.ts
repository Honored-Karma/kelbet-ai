import trendAlive from "../../assets/trends/alive.webp";
import trendAnime from "../../assets/trends/anime.webp";
import trendBlueprint from "../../assets/trends/blueprint.webp";
import trendChrome from "../../assets/trends/chrome.webp";
import trendDoodle from "../../assets/trends/doodle.webp";
import trendFigurine from "../../assets/trends/figurine.webp";
import trendFlash from "../../assets/trends/flash.webp";
import trendOrbit from "../../assets/trends/orbit.webp";
import trendPolaroid from "../../assets/trends/polaroid.webp";
import trendUnderwater from "../../assets/trends/underwater.webp";
import type { Language } from "../../shared/api/types";

export type TrendKind = "image" | "video";

export type TrendTemplate = {
  id: string;
  kind: TrendKind;
  badge?: "hot" | "new";
  title: Record<Language, string>;
  description: Record<Language, string>;
  /**
   * Скрытый пресет-промпт тренда. Английский — модели стабильнее держат стиль,
   * пользователь этот текст не видит и не редактирует.
   */
  prompt: string;
  aspectRatio: string;
  durationSec?: number;
  preview: string;
};

/** Модели, через которые исполняются тренды (в порядке предпочтения). */
export const TREND_EDIT_SLUGS = [
  "runway-seedream5-pro-edit",
  "runway-seedream5-lite-edit",
];
export const TREND_VIDEO_SLUGS = [
  "runway-gemini-omni-video-fast",
  "runway-gen45-video-quality",
];

export const TREND_TEMPLATES: TrendTemplate[] = [
  {
    id: "figurine",
    kind: "image",
    badge: "hot",
    title: { ru: "3D-фигурка", kk: "3D мүсінше" },
    description: {
      ru: "Вы — коллекционная фигурка в упаковке",
      kk: "Сіз — қаптамадағы коллекциялық мүсінше",
    },
    prompt:
      "Turn the person from the photo into a highly detailed collectible action figure, "
      + "sealed inside a retail blister pack with printed cardboard backing, product name "
      + "and small accessories in separate compartments. Keep the face and outfit clearly "
      + "recognizable. The boxed figure stands on a desk near a computer monitor, shallow "
      + "depth of field, soft studio light, photorealistic product shot.",
    aspectRatio: "3:4",
    preview: trendFigurine,
  },
  {
    id: "anime",
    kind: "image",
    badge: "hot",
    title: { ru: "Аниме", kk: "Аниме" },
    description: {
      ru: "Кадр из аниме-фильма с вашим героем",
      kk: "Сіз кейіпкер болған аниме кадры",
    },
    prompt:
      "Redraw the photo as a frame from a modern high-budget anime film: clean expressive "
      + "line art, large detailed eyes, soft cel shading, dramatic golden-hour lighting, "
      + "painterly background with depth. Keep the person's identity, hairstyle and clothing "
      + "recognizable. Cinematic composition, vibrant colors.",
    aspectRatio: "3:4",
    preview: trendAnime,
  },
  {
    id: "alive",
    kind: "video",
    badge: "new",
    title: { ru: "Оживи фото", kk: "Фотоны жандандыр" },
    description: {
      ru: "Снимок задышит: ветер, свет, взгляд",
      kk: "Сурет тіріледі: жел, жарық, көзқарас",
    },
    prompt:
      "Bring this photo to life with subtle natural motion: gentle breathing, soft blinking, "
      + "hair and clothing moving in a light breeze, delicate light shifts in the background. "
      + "Keep the framing of the original photo, smooth realistic motion, no camera shake.",
    aspectRatio: "9:16",
    durationSec: 4,
    preview: trendAlive,
  },
  {
    id: "polaroid",
    kind: "image",
    title: { ru: "Ретро-полароид", kk: "Ретро-полароид" },
    description: {
      ru: "Тёплый снимок 90-х с белой рамкой",
      kk: "90-жылдардағы ақ жиекті жылы кадр",
    },
    prompt:
      "Restyle the photo as an authentic vintage instant polaroid from the 90s: white film "
      + "frame with a wider bottom border, harsh direct flash, slightly faded warm colors, "
      + "soft film grain and mild vignette, casual candid framing. Keep the person clearly "
      + "recognizable. The polaroid lies on a plain surface, photographed from above.",
    aspectRatio: "3:4",
    preview: trendPolaroid,
  },
  {
    id: "chrome",
    kind: "image",
    title: { ru: "Хром и диско", kk: "Хром және диско" },
    description: {
      ru: "Жидкий металл и блеск дискотеки",
      kk: "Сұйық металл және диско жарқылы",
    },
    prompt:
      "Transform the subject of the photo into a sculpture of liquid chrome metal: mirror-like "
      + "reflective surface, smooth melted forms, colorful disco lights and bokeh reflecting in "
      + "the metal, dark glossy studio background. Keep the pose and silhouette of the original "
      + "subject recognizable. Photorealistic render, dramatic rim light.",
    aspectRatio: "1:1",
    preview: trendChrome,
  },
  {
    id: "orbit",
    kind: "video",
    title: { ru: "Кино-облёт", kk: "Кино-айналым" },
    description: {
      ru: "Камера медленно облетает героя",
      kk: "Камера кейіпкерді баяу айналып өтеді",
    },
    prompt:
      "Cinematic slow orbit shot around the subject of the photo: the camera smoothly circles "
      + "the hero while they stay nearly still, shallow depth of field, atmospheric volumetric "
      + "light, subtle dust particles in the air, film color grading. Elegant, epic mood.",
    aspectRatio: "9:16",
    durationSec: 4,
    preview: trendOrbit,
  },
  {
    id: "doodle",
    kind: "image",
    title: { ru: "Каракули", kk: "Шимай сурет" },
    description: {
      ru: "Наивный рисунок фломастером",
      kk: "Фломастермен салған аңғал сурет",
    },
    prompt:
      "Redraw the photo as a charming naive doodle made with felt-tip markers and crayons: "
      + "wobbly confident outlines, flat bright colors that slightly miss the lines, simple "
      + "shapes, white paper background with small stars and scribbles around. Keep the "
      + "person's key features recognizable in a funny cute way.",
    aspectRatio: "1:1",
    preview: trendDoodle,
  },
  {
    id: "underwater",
    kind: "image",
    title: { ru: "Под водой", kk: "Су астында" },
    description: {
      ru: "Солнечные блики сквозь толщу воды",
      kk: "Су қабатынан өткен күн шағылысы",
    },
    prompt:
      "Place the person from the photo underwater in clear turquoise water: sun rays and "
      + "caustic light patterns dancing on the skin, hair floating weightlessly, tiny air "
      + "bubbles, dreamy serene expression. Keep the face clearly recognizable. Cinematic "
      + "photorealistic underwater photography.",
    aspectRatio: "3:4",
    preview: trendUnderwater,
  },
  {
    id: "flash",
    kind: "image",
    title: { ru: "Ночная вспышка", kk: "Түнгі жарқыл" },
    description: {
      ru: "Резкий свет камеры, ночная улица",
      kk: "Камераның өткір жарығы, түнгі көше",
    },
    prompt:
      "Restyle the photo as a night street shot taken with a harsh direct on-camera flash: "
      + "brightly lit subject against a dark city street, deep shadows, slight overexposure "
      + "on the face, paparazzi aesthetic, 2000s digital camera look with mild noise. Keep "
      + "the person clearly recognizable.",
    aspectRatio: "3:4",
    preview: trendFlash,
  },
  {
    id: "blueprint",
    kind: "image",
    title: { ru: "Постер-чертёж", kk: "Сызба-постер" },
    description: {
      ru: "Технический чертёж вашего объекта",
      kk: "Нысаныңыздың техникалық сызбасы",
    },
    prompt:
      "Turn the subject of the photo into a detailed technical blueprint poster: white line "
      + "drawing on deep blue paper, orthographic views, measurement lines, annotations and "
      + "part numbers, subtle paper texture and fold marks. Keep the silhouette of the "
      + "original subject clearly recognizable. Elegant engineering aesthetic.",
    aspectRatio: "3:4",
    preview: trendBlueprint,
  },
];
