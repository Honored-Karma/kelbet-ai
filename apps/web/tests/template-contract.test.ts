import assert from "node:assert/strict";
import test from "node:test";

import { adminControlsSchema } from "../src/features/admin/types.ts";
import {
  buildTemplateSelection,
  isTemplateUnavailable,
  templateFieldLabel,
  templateFieldsValid,
  templateSelectionFromQuote,
} from "../src/features/templates/selection.ts";
import {
  generationDraftSchema,
  generationTemplateSchema,
  quoteSchema,
} from "../src/shared/api/types.ts";

const template = generationTemplateSchema.parse({
  id: "22222222-2222-2222-2222-222222222210",
  slug: "toi",
  version: 1,
  kind: "video",
  display_order: 103,
  localization: { name: "Тойға шақыру", description: "Шақыру үлгісі" },
  prompt_preset: "Алтын түсті ою баяу ашылады",
  aspect_ratio: "9:16",
  duration_sec: 8,
  compatible_modalities: ["video"],
  required_inputs: {
    assets: { min: 0, max: 1 },
    fields: [
      {
        key: "headline",
        type: "text",
        required: true,
        max_length: 80,
        label: { ru: "Имена", kk: "Есімдер" },
      },
    ],
  },
  preview_metadata: { marker: "T" },
  compositor: "toi_invite_v1",
});

test("catalog template keeps RU/KK dynamic labels", () => {
  assert.equal(templateFieldLabel(template.required_inputs.fields[0]!, "ru"), "Имена");
  assert.equal(templateFieldLabel(template.required_inputs.fields[0]!, "kk"), "Есімдер");
});

test("one normalized template snapshot is valid for quote and create", () => {
  assert.equal(templateFieldsValid(template, { headline: "  Аян және Аружан  " }), true);
  const quoteSelection = buildTemplateSelection(template, {
    headline: "  Аян және Аружан  ",
    ignored: "must not leave the client",
  });
  const createSelection = buildTemplateSelection(template, {
    headline: "  Аян және Аружан  ",
    ignored: "different ignored value",
  });
  assert.deepEqual(createSelection, quoteSelection);
  assert.deepEqual(quoteSelection, {
    templateId: template.id,
    templateInputs: { headline: "Аян және Аружан" },
  });
});

test("create replays the fresh quote canonical Unicode snapshot", () => {
  const decomposedKazakh = "Аян және Мереи\u0306";
  const canonicalKazakh = decomposedKazakh.normalize("NFC");
  assert.notEqual(decomposedKazakh, canonicalKazakh);

  const clientSelection = buildTemplateSelection(template, {
    headline: decomposedKazakh,
  });
  const freshQuote = quoteSchema.parse({
    quote_id: "quote-canonical-unicode",
    model_slug: "runway-gen45-video-quality",
    user_credit_price: 40,
    currency: "credits",
    expires_at: "2026-08-01T12:00:00Z",
    params: { aspect_ratio: "9:16", duration_sec: 8 },
    template_id: template.id,
    template_slug: template.slug,
    template_version: template.version,
    template_inputs: { headline: canonicalKazakh },
  });

  const createSelection = templateSelectionFromQuote(freshQuote);
  assert.notDeepEqual(createSelection.templateInputs, clientSelection.templateInputs);
  assert.deepEqual(createSelection, {
    templateId: freshQuote.template_id,
    templateInputs: freshQuote.template_inputs,
  });
});

test("required template inputs gate quoting", () => {
  assert.equal(templateFieldsValid(template, {}), false);
  assert.equal(templateFieldsValid(template, { headline: "x".repeat(81) }), false);
});

test("missing template is reported only after a successful catalog load", () => {
  assert.equal(isTemplateUnavailable(template.id, null, false), false);
  assert.equal(isTemplateUnavailable(template.id, null, true), true);
  assert.equal(isTemplateUnavailable(template.id, template, true), false);
  assert.equal(isTemplateUnavailable(null, null, true), false);
});

test("quote and draft contracts preserve the immutable template snapshot", () => {
  const snapshot = {
    template_id: template.id,
    template_slug: template.slug,
    template_version: template.version,
    template_inputs: { headline: "Аян және Аружан" },
  };
  assert.equal(
    quoteSchema.parse({
      quote_id: "quote-1",
      model_slug: "runway-gen45-video-quality",
      user_credit_price: 40,
      currency: "credits",
      expires_at: "2026-08-01T12:00:00Z",
      params: { aspect_ratio: "9:16", duration_sec: 8 },
      ...snapshot,
    }).template_id,
    template.id,
  );
  assert.deepEqual(
    generationDraftSchema.parse({
      source_generation_id: "generation-1",
      mode: "repeat",
      model_slug: "runway-gen45-video-quality",
      modality: "video",
      prompt: template.prompt_preset,
      params: { aspect_ratio: "9:16", duration_sec: 8 },
      input_asset_ids: [],
      unavailable_asset_ids: [],
      missing_input_assets: 0,
      model_available: true,
      replacement_slug: null,
      ...snapshot,
    }).template_inputs,
    snapshot.template_inputs,
  );
});

test("admin controls expose support-readable template state", () => {
  const controls = adminControlsSchema.parse({
    models: [],
    feature_flags: [],
    provider_health: [],
    payment_products: [],
    templates: [
      {
        slug: template.slug,
        version: 1,
        kind: "video",
        enabled: true,
        display_order: 103,
        localization: { ru: { name: "Той-приглашение" }, kk: { name: "Тойға шақыру" } },
      },
    ],
  });
  assert.equal(controls.templates[0]?.display_order, 103);
});
