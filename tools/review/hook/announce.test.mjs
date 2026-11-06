import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), "announce.mjs");
const hoursAgo = (h) => new Date(Date.now() - h * 3600e3).toISOString();

function setup(videos) {
  const root = mkdtempSync(join(tmpdir(), "rv-"));
  mkdirSync(join(root, "milan-content"));
  if (videos !== undefined) writeFileSync(join(root, "_review-index.json"), typeof videos === "string" ? videos : JSON.stringify({ videos }));
  return root;
}
const video = (extra) => ({ id: "milan-content/03-x", title: "03 X", project: "milan-content", status: "sent",
  round: 1, round_label: "First cut", notes_count: 4, claimed_at: null, ...extra });

function run(root, cwd) {
  const t = Date.now();
  const r = spawnSync(process.execPath, [SCRIPT], { input: JSON.stringify({ cwd }),
    env: { ...process.env, REVIEW_ROOT: root }, encoding: "utf8" });
  return { ...r, ms: Date.now() - t };
}

test("announces unclaimed sent feedback", () => {
  const root = setup([video()]);
  const r = run(root, join(root, "milan-content"));
  assert.equal(r.status, 0);
  assert.match(r.stdout, /Feedback ready: milan-content \/ 03 X, First cut, 4 notes\./);
  assert.match(r.stdout, /review\.py claim milan-content\/03-x/);
});

test("silent outside the workspace", () => {
  const root = setup([video()]);
  const r = run(root, tmpdir());
  assert.equal(r.status, 0);
  assert.equal(r.stdout, "");
});

test("silent when claimed 1h ago, announces when claimed 5h ago", () => {
  const fresh = setup([video({ claimed_at: hoursAgo(1) })]);
  assert.equal(run(fresh, fresh).stdout, "");
  const root = setup([video({ claimed_at: hoursAgo(5) })]);
  assert.match(run(root, root).stdout, /Feedback ready/);
});

test("silent for other statuses", () => {
  const root = setup([video({ status: "waiting" }), video({ status: "fixes_ready" }), video({ status: "approved" })]);
  assert.equal(run(root, root).stdout, "");
});

test("silent and exit 0 when index missing or corrupt", () => {
  const a = setup(undefined);
  assert.deepEqual([run(a, a).status, run(a, a).stdout], [0, ""]);
  const b = setup("{not json");
  assert.deepEqual([run(b, b).status, run(b, b).stdout], [0, ""]);
});

test("fast", () => {
  const root = setup([video()]);
  assert.ok(run(root, root).ms < 500);
});
