import assert from "node:assert/strict";
import test from "node:test";

import { generationPassportSchema, generationSchema } from "../src/shared/api/types.ts";

const succeeded = {
  id: "1f1c3c40-6f4a-4a5e-8f0c-2b6a5f9d1e77",
  status: "succeeded",
  modality: "video",
  model_slug: "kelbet-video-quality",
  template_slug: null,
  template_version: null,
  user_credit_price: 240,
  progress_pct: 100,
  progress_stage: null,
  error_code: null,
  cancelable: false,
  output_asset_ids: ["8d2f9c11-4a3b-4f6e-9c1d-77a0b5e4c332"],
  created_at: "2026-08-12T09:00:00Z",
};

test("паспорт доезжает до интерфейса вместе с генерацией", () => {
  const generation = generationSchema.parse({
    ...succeeded,
    passport: {
      provider: "google",
      provider_model_id: "veo-3.1-fast",
      requested_provider: "runway",
      requested_provider_model_id: "gen4_turbo",
      substituted: true,
      credits_charged: 240,
      attempts: 2,
      aspect_ratio: "9:16",
      resolution: "720p",
      duration_sec: 8,
      width: 720,
      height: 1280,
    },
  });

  // Регрессия: схема отбрасывает неизвестные поля, поэтому до объявления
  // passport сервер честно присылал чек, а интерфейс молча его терял.
  assert.ok(generation.passport, "паспорт не должен вырезаться при разборе");
  assert.equal(generation.passport?.substituted, true);
  assert.equal(generation.passport?.provider, "google");
  assert.equal(generation.passport?.requested_provider, "runway");
});

test("генерация без паспорта остаётся валидной", () => {
  const generation = generationSchema.parse(succeeded);
  assert.equal(generation.passport ?? null, null);
});

test("паспорт без подмены не обещает второго маршрута", () => {
  const passport = generationPassportSchema.parse({
    provider: "runway",
    provider_model_id: "gen4_image",
    requested_provider: "runway",
    requested_provider_model_id: "gen4_image",
    substituted: false,
    credits_charged: 80,
    attempts: 1,
    aspect_ratio: "1:1",
    resolution: "1024x1024",
    duration_sec: null,
    width: 1024,
    height: 1024,
  });

  assert.equal(passport.substituted, false);
  assert.equal(passport.provider, passport.requested_provider);
  assert.equal(passport.duration_sec, null);
});

test("измеренные пиксели могут отсутствовать, и это не ломает разбор", () => {
  // Ширина и высота читаются из выходного ассета. Для модальностей без
  // растрового вывода их просто нет — паспорт обязан это допускать.
  const passport = generationPassportSchema.parse({
    provider: "openrouter",
    provider_model_id: "mock-text-v1",
    requested_provider: "openrouter",
    requested_provider_model_id: "mock-text-v1",
    substituted: false,
    credits_charged: 1,
    attempts: 1,
    aspect_ratio: null,
    resolution: null,
    duration_sec: null,
    width: null,
    height: null,
  });

  assert.equal(passport.width, null);
  assert.equal(passport.height, null);
});
