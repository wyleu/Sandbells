// node --test changes/bells/js_tests/  -- bell_motion.js, the small diagonal movement per stroke or trigger
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const BM = require("../static/js/bell_motion.js");

function fakeEl() {
  const set = new Set();
  return {
    set,
    classList: { add: (c) => set.add(c), remove: (c) => set.delete(c) },
  };
}
const stroke = { schema: "sand.event/v1", type: "stroke", src: "sandswing", body: { ch: 3 } };
const trigger = { schema: "sand.event/v1", type: "stroke", body: { ch: 1, test: true, src: "trigger" } };
const triggerFlat = { ch: 2, test: true, src: "trigger" };

test("a stroke and a trigger event (either shape) move the element", () => {
  for (const m of [stroke, trigger, triggerFlat]) {
    const el = fakeEl();
    BM.create(el)(m);
    assert.deepEqual([...el.set], ["bell-motion-1"]);
  }
});

test("heartbeats, link and channel events, and junk do not move it", () => {
  const el = fakeEl();
  const move = BM.create(el);
  for (const m of [
    { schema: "sand.panel/v1", type: "heartbeat", body: { chan: [["trigger", "why"]] } },
    { schema: "sand.panel/v1", type: "stroke" },
    { schema: "sand.event/v1", type: "link", body: { what: "client" } },
    { schema: "sand.event/v1", type: "channel", body: { ch: 1, kind: "trigger" } },
    { tick: 5 }, {}, null, undefined, "stroke", 7,
  ]) move(m);
  assert.equal(el.set.size, 0);
});

test("every event switches to the other of two animation names, so a burst restarts it", () => {
  const el = fakeEl();
  const move = BM.create(el);
  const seen = [];
  for (let i = 0; i < 5; i++) { move(stroke); seen.push([...el.set].join()); }
  assert.deepEqual(seen, ["bell-motion-1", "bell-motion-0", "bell-motion-1", "bell-motion-0", "bell-motion-1"]);
});

test("no element: nothing happens", () => {
  assert.doesNotThrow(() => BM.create(null)(stroke));
});
