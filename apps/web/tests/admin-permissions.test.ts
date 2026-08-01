import assert from "node:assert/strict";
import test from "node:test";

import { canRenderAdminAction, hasAdminWriteCapability } from "../src/features/admin/permissions.ts";
import type { AdminMe } from "../src/features/admin/types.ts";

const base: AdminMe = {
  user_id: "4763b49b-478a-45e6-befd-5c9f25e92579",
  telegram_id: 123456,
  username: "operator",
  role: "support",
  bootstrap: false,
  capabilities: ["read"],
};

test("support role cannot render mutation controls without a server write capability", () => {
  assert.equal(hasAdminWriteCapability(base), false);
  assert.equal(canRenderAdminAction(base, "wallet.grant"), false);
  assert.equal(canRenderAdminAction(base, "control.toggle"), false);
  assert.equal(canRenderAdminAction(base, "moderation.review"), false);
});

test("role name alone never unlocks writes", () => {
  const namedAdmin: AdminMe = { ...base, role: "admin", capabilities: ["read"] };
  assert.equal(hasAdminWriteCapability(namedAdmin), false);
  assert.equal(canRenderAdminAction(namedAdmin, "generation.refund"), false);
});

test("server write capability unlocks the minimal admin action set", () => {
  const authorized: AdminMe = { ...base, role: "admin", capabilities: ["read", "write"] };
  assert.equal(hasAdminWriteCapability(authorized), true);
  assert.equal(canRenderAdminAction(authorized, "wallet.grant"), true);
  assert.equal(canRenderAdminAction(authorized, "user.block"), true);
  assert.equal(canRenderAdminAction(authorized, "generation.refund"), true);
  assert.equal(canRenderAdminAction(authorized, "control.toggle"), true);
  assert.equal(canRenderAdminAction(authorized, "moderation.review"), true);
});
