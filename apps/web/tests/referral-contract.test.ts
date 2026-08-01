import assert from "node:assert/strict";
import test from "node:test";

import { referralSummarySchema } from "../src/shared/api/types.ts";

test("referral summary accepts enabled and disabled server-owned states", () => {
  const enabled = referralSummarySchema.parse({
    enabled: true,
    code: "KELBETDEMO",
    link: "https://t.me/kelbet_demo_bot?start=ref_KELBETDEMO",
    invited_count: 3,
    pending_rewards_count: 1,
    credited_rewards_count: 1,
    credited_bonus_credits: 5,
    inviter_bonus_credits: 5,
    invitee_bonus_credits: 2,
    minimum_purchase_stars: 50,
    waiting_period_hours: 72,
  });
  assert.equal(enabled.link?.includes("start=ref_"), true);

  const disabled = referralSummarySchema.parse({
    ...enabled,
    enabled: false,
    code: null,
    link: null,
    invited_count: 0,
    pending_rewards_count: 0,
    credited_rewards_count: 0,
    credited_bonus_credits: 0,
  });
  assert.equal(disabled.link, null);
});

test("referral contract rejects client-invented mutable reward fields", () => {
  const result = referralSummarySchema.safeParse({
    enabled: true,
    code: "KELBETDEMO",
    link: "https://t.me/kelbet_demo_bot?start=ref_KELBETDEMO",
    invited_count: 0,
    pending_rewards_count: 0,
    credited_rewards_count: 0,
    credited_bonus_credits: 0,
    inviter_bonus_credits: 5,
    invitee_bonus_credits: 2,
    minimum_purchase_stars: 50,
    waiting_period_hours: 72,
    reward_now: true,
  });
  assert.equal(result.success, false);
});
