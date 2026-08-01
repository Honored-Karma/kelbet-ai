import assert from "node:assert/strict";
import test from "node:test";

import { currentAppPath, resolveBootReturnTo } from "../src/app/navigation.ts";

test("preserves Telegram button destinations through authentication", () => {
  for (const path of ["/create", "/video", "/trends", "/history", "/plans", "/profile", "/support", "/invite", "/admin"]) {
    assert.equal(resolveBootReturnTo({ returnTo: path }), path);
  }
});

test("preserves safe query strings and generation routes", () => {
  assert.equal(
    currentAppPath({ pathname: "/create", search: "?recipe=product", hash: "" }),
    "/create?recipe=product",
  );
  assert.equal(
    resolveBootReturnTo({ returnTo: "/generations/4763b49b-478a-45e6-befd-5c9f25e92579" }),
    "/generations/4763b49b-478a-45e6-befd-5c9f25e92579",
  );
});

test("rejects external, boot, and unknown return destinations", () => {
  for (const value of [
    "https://evil.example/",
    "//evil.example/",
    "/\\evil.example/",
    "/boot",
    "/not-a-real-page",
    null,
  ]) {
    assert.equal(resolveBootReturnTo({ returnTo: value }), "/");
  }
});
