import assert from "node:assert/strict";
import test from "node:test";

import { adminModerationDecisionSchema } from "../src/features/admin/types.ts";
import { moderationConfigSchema } from "../src/shared/api/types.ts";

test("moderation config exposes an honest text-only photo contract", () => {
  const config = moderationConfigSchema.parse({
    mode: "report",
    policy_version: "2026-08-01-v1",
    photo_rights_consent_version: "2026-08-01-v1",
    support_route: "/support",
    image_moderation_supported: false,
  });
  assert.equal(config.image_moderation_supported, false);
  assert.equal(config.support_route, "/support");
});

test("moderation queue schema rejects accidental raw input fields", () => {
  const result = adminModerationDecisionSchema.safeParse({
    id: "4763b49b-478a-45e6-befd-5c9f25e92579",
    user_id: "9f54d1a5-6536-4227-88e6-5282275f695d",
    generation_id: null,
    asset_ids: [],
    context: "generation",
    input_hash: "sha256:privacy-safe",
    mode: "report",
    outcome: "report",
    reason_codes: ["rules.flagged"],
    policy_version: "2026-08-01-v1",
    provider: "rules",
    provider_model: null,
    error_code: null,
    review_status: "open",
    review_outcome: null,
    reviewed_at: null,
    created_at: "2026-08-01T10:00:00Z",
    raw_input: "must never reach the operator UI",
  });
  assert.equal(result.success, false);
});
