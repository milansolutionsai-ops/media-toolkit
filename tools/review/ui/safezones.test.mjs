import { test } from "node:test";
import assert from "node:assert/strict";
import { zones, PLATFORMS } from "./safezones.js";

test("instagram zones on a full-size vertical frame", () => {
  const z = zones("instagram", 1080, 1920);
  const bottom = z.find((r) => r.label.includes("caption"));
  assert.deepEqual([bottom.y, bottom.h], [1500, 420]);
  const right = z.find((r) => r.label.includes("buttons"));
  assert.deepEqual([right.x, right.w], [940, 140]);
});

test("zones scale with the video", () => {
  const bottom = zones("tiktok", 540, 960).find((r) => r.label.includes("caption"));
  assert.equal(bottom.h, 240);
});

test("horizontal video has no vertical-platform zones", () => {
  assert.deepEqual(zones("instagram", 1920, 1080), []);
});

test("every platform defined", () => {
  assert.deepEqual(Object.keys(PLATFORMS).sort(), ["instagram", "linkedin", "shorts", "tiktok"]);
});
