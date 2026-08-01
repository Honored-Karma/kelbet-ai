import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AdminCapabilityGate } from "../src/features/admin/CapabilityGate.ts";
import type { AdminMe } from "../src/features/admin/types.ts";

function operator(capabilities: string[]): AdminMe {
  return {
    user_id: "4763b49b-478a-45e6-befd-5c9f25e92579",
    telegram_id: 123456,
    username: "operator",
    role: capabilities.includes("write") ? "admin" : "support",
    bootstrap: false,
    capabilities,
  };
}

function renderWriteControls(capabilities: string[]): string {
  return renderToStaticMarkup(
    createElement(
      AdminCapabilityGate,
      { operator: operator(capabilities), action: "wallet.grant" },
      createElement("button", { type: "button", "data-testid": "grant-credits" }, "Grant"),
    ),
  );
}

test("rendered write control is absent for server capabilities read only", () => {
  assert.equal(renderWriteControls(["read"]), "");
});

test("rendered write control is present when server grants write", () => {
  assert.match(renderWriteControls(["read", "write"]), /data-testid="grant-credits"/);
});
