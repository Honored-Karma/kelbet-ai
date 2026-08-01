import assert from "node:assert/strict";
import test from "node:test";

import { SUPPORT_COMMAND, supportCopy } from "../src/features/support/contract.ts";

test("support contract uses the real bot command in both languages", () => {
  assert.equal(SUPPORT_COMMAND, "/support");
  for (const language of ["ru", "kk"] as const) {
    assert.match(supportCopy[language].stepCommand, /\/support/);
    assert.match(supportCopy[language].body, /Telegram/);
  }
});

test("support copy does not invent a bot username or contact URL", () => {
  const renderedCopy = JSON.stringify(supportCopy);
  assert.doesNotMatch(renderedCopy, /@[A-Za-z0-9_]+/);
  assert.doesNotMatch(renderedCopy, /t\.me\//);
});
