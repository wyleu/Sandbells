// node --test changes/events/js_tests/  -- pure helpers of clock.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const clock = require(path.join(__dirname, "..", "templates", "events", "clock.js"));

const TZ = "Europe/London";

test("hms pads and wraps the hour", () => {
  assert.equal(clock.hms(9, 5, 7), "09:05:07");
  assert.equal(clock.hms(23, 59, 59), "23:59:59");
  assert.equal(clock.hms(24, 0, 1), "00:00:01");   // some engines say 24 at midnight
});

test("delay aims just past the next whole second", () => {
  const m = clock.TICK_MARGIN_MS;
  assert.equal(clock.delayToNextSecond(1_700_000_000_000), 1000 + m);
  assert.equal(clock.delayToNextSecond(1_700_000_000_250), 750 + m);
  assert.equal(clock.delayToNextSecond(1_700_000_000_999), 1 + m);
});

test("quarter marks and countdown", () => {
  assert.deepEqual(clock.quarter(0),
    { index: 0, toNext: 15, next: 15, onMark: true, onMinute: true });
  assert.deepEqual(clock.quarter(14),
    { index: 0, toNext: 1, next: 15, onMark: false, onMinute: false });
  assert.deepEqual(clock.quarter(15),
    { index: 1, toNext: 15, next: 30, onMark: true, onMinute: false });
  assert.deepEqual(clock.quarter(44),
    { index: 2, toNext: 1, next: 45, onMark: false, onMinute: false });
  assert.deepEqual(clock.quarter(52),
    { index: 3, toNext: 8, next: 0, onMark: false, onMinute: false });
  assert.equal(clock.nextLabel(clock.quarter(52)), ":00");
  assert.equal(clock.nextLabel(clock.quarter(20)), ":30");
});

test("UK time: BST before 25 Oct 2026, GMT after", () => {
  const f = clock.makeFormatter(TZ);
  assert.ok(f);
  const bst = clock.partsOf(f, new Date(Date.UTC(2026, 9, 22, 10, 14, 45)));
  assert.equal(clock.hms(bst.h, bst.m, bst.s), "11:14:45");
  assert.equal(bst.zone, "BST");
  const gmt = clock.partsOf(f, new Date(Date.UTC(2026, 9, 26, 23, 0, 30)));
  assert.equal(clock.hms(gmt.h, gmt.m, gmt.s), "23:00:30");
  assert.equal(gmt.zone, "GMT");
  const midnight = clock.partsOf(f, new Date(Date.UTC(2026, 9, 22, 23, 0, 0)));
  assert.equal(clock.hms(midnight.h, midnight.m, midnight.s), "00:00:00");
});

test("unknown zone falls back to local time", () => {
  assert.equal(clock.makeFormatter("Not/AZone"), null);
  const d = new Date(2026, 9, 22, 7, 8, 9);
  assert.deepEqual(clock.partsOf(null, d), { h: 7, m: 8, s: 9, zone: "" });
});
