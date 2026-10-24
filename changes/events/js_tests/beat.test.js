// node --test changes/events/js_tests/  -- the beat helper of beat.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const beat = require(path.join(__dirname, "..", "templates", "events", "beat.js"));

test("no beat until a gap has been seen", () => {
  const b = beat.createBeat();
  assert.equal(b.observe("a", null), null);
  assert.equal(b.observe("a", 1000), null);        // the first gap has nothing before it
});

test("a steady rhythm sits on the centre", () => {
  const b = beat.createBeat();
  b.observe("a", 1000);
  for (let i = 0; i < 6; i++) assert.equal(b.observe("a", 1000).pos, 0.5);
});

test("early is left, late is right, clamped at the ends", () => {
  const b = beat.createBeat();
  for (let i = 0; i < 5; i++) b.observe("a", 1000);
  assert.ok(b.observe("a", 900).pos < 0.5);
  assert.ok(b.observe("a", 1100).pos > 0.5);
  assert.equal(b.observe("a", 5000).pos, 1);
  assert.equal(b.observe("a", 1).pos, 0);
});

test("half a beat out reaches the end", () => {
  const b = beat.createBeat();
  for (let i = 0; i < 5; i++) b.observe("a", 1000);
  assert.equal(b.observe("a", 1500).pos, 1);
});

test("handstroke and backstroke gaps are kept apart", () => {
  const b = beat.createBeat();
  let last;
  for (let i = 0; i < 12; i++) last = b.observe("a", i % 2 ? 1000 : 1200);
  assert.equal(last.pos, 0.5);                      // a real 1000 after 1200s is on its own beat
  assert.equal(last.beat, 1000);
});

test("a null gap starts a new run", () => {
  const b = beat.createBeat();
  for (let i = 0; i < 5; i++) b.observe("a", 1000);
  b.observe("a", null);
  assert.equal(b.observe("a", 2000), null);
});

test("keys do not mix", () => {
  const b = beat.createBeat();
  for (let i = 0; i < 4; i++) b.observe("a", 1000);
  assert.equal(b.observe("b", 3000), null);
});
