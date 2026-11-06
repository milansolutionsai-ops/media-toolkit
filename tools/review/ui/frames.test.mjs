import { test } from "node:test";
import assert from "node:assert/strict";
import { parseFps, frameToSeek, timeToFrame, clampFrame, contextWindow, reduceKey, initialKeyState } from "./frames.js";

const W = { picture_frames: 4, sound_seconds: 2, cut_seconds: 1 };

test("frameToSeek targets the frame centre", () => {
  assert.equal(frameToSeek(10, 30), 10.5 / 30);
});

test("seek and back is exact for every frame", () => {
  for (let n = 0; n <= 300; n++) assert.equal(timeToFrame(frameToSeek(n, 30), 30), n);
  for (let n = 0; n <= 300; n++) assert.equal(timeToFrame(frameToSeek(n, 30000 / 1001), 30000 / 1001), n);
});

test("parseFps", () => {
  assert.ok(Math.abs(parseFps("30000/1001") - 29.97) < 0.001);
  assert.equal(parseFps("30/1"), 30);
});

test("contextWindow per tag, clamped", () => {
  assert.deepEqual(contextWindow({ tag: "picture", start: 100, end: 102 }, W, 30, 600), [96, 106]);
  assert.deepEqual(contextWindow({ tag: "sound", start: 300, end: 300 }, W, 30, 600), [240, 360]);
  assert.deepEqual(contextWindow({ tag: "cut", start: 10, end: 20 }, W, 30, 600), [0, 50]);
  assert.deepEqual(contextWindow({ tag: "sound", start: 590, end: 599 }, W, 30, 600), [530, 599]);
});

test("clampFrame", () => {
  assert.equal(clampFrame(-3, 100), 0);
  assert.equal(clampFrame(150, 100), 99);
});

test("reduceKey: marks, steps, tags, save", () => {
  let s = { ...initialKeyState(), frame: 50, total: 100 };
  s = reduceKey(s, { key: "ArrowRight", shiftKey: true });
  assert.equal(s.frame, 60);
  s = reduceKey(s, { key: "ArrowLeft" });
  assert.equal(s.frame, 59);
  s = reduceKey(s, { key: "i" });
  s = reduceKey(s, { key: "ArrowRight", shiftKey: true });
  s = reduceKey(s, { key: "o" });
  assert.deepEqual([s.markIn, s.markOut], [59, 69]);
  s = reduceKey(s, { key: "s" });
  assert.equal(s.tag, "sound");
  s = reduceKey(s, { key: "Enter" });
  assert.equal(s.action, "save");
  s = reduceKey(s, { key: " " });
  assert.equal(s.action, "toggle-play");
  s = reduceKey(s, { key: "Escape" });
  assert.equal(s.markIn, null);
  assert.equal(s.action, "cancel");
});

test("reduceKey: out before in swaps the range", () => {
  let s = { ...initialKeyState(), frame: 40, total: 100 };
  s = reduceKey(s, { key: "i" });
  s = reduceKey({ ...s, frame: 30 }, { key: "o" });
  assert.deepEqual([s.markIn, s.markOut], [30, 40]);
});
