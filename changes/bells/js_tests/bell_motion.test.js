// node --test changes/bells/js_tests/  -- bell_motion.js: a stroke swings the struck bell's clapper,
// with the pad press movement (bell_band.js settleDemo)
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const BM = require("../static/js/bell_motion.js");

/* #bell-circle with a .bell-pad per drawn bell (1..8), as bell_band.js draws it */
function fakeHost(bells) {
  const drawn = new Set(bells || [1, 2, 3, 4, 5, 6, 7, 8]);
  const asked = [];
  return {
    asked,
    querySelector: (sel) => {
      asked.push(sel);
      const m = /^\.bell-pad\[data-bell="(\d+)"\]$/.exec(sel);
      return m && drawn.has(Number(m[1])) ? {} : null;
    },
  };
}
function rig(bells) {
  const struck = [];
  const host = fakeHost(bells);
  return { host, struck, move: BM.create(host, (bell) => struck.push(bell)) };
}

// what /events/api/since/ gives: "bell" from the channel map, null when the channel is unmapped
const stroke = (bell) => ({ schema: "sand.event/v1", type: "stroke", src: "sandswing", ch: 3, bell, body: { ch: 3 } });
const trigger = (bell) => ({ type: "stroke", src: "sandswing", ch: 1, bell, body: { ch: 1, test: true, src: "trigger" } });

test("a stroke for bell 8 strikes bell 8 (the press movement), nothing else", () => {
  const r = rig();
  r.move(stroke(8));
  assert.deepEqual(r.struck, [8]);
  assert.deepEqual(r.host.asked, ['.bell-pad[data-bell="8"]']);
});

test("a trigger plug test stroke strikes its bell too; each stroke strikes again", () => {
  const r = rig();
  r.move(trigger(2)); r.move(stroke(2)); r.move(stroke(5));
  assert.deepEqual(r.struck, [2, 2, 5]);
});

test("no bell number (unmapped channel, or none given) or a bell not drawn: nothing moves", () => {
  const r = rig();
  for (const m of [stroke(null), stroke(undefined), trigger(null), { ch: 2, test: true, src: "trigger" },
    stroke(9), stroke(0), stroke(-1), stroke(2.5), stroke("8")]) r.move(m);
  assert.deepEqual(r.struck, []);
  assert.deepEqual(r.host.asked, ['.bell-pad[data-bell="9"]']);   // asked, not drawn
});

test("isBellStroke: only strokes and triggers that carry a bell, so the feed queues nothing else", () => {
  assert.equal(BM.isBellStroke(stroke(8)), true);
  assert.equal(BM.isBellStroke(trigger(1)), true);
  assert.equal(BM.isBellStroke(stroke(null)), false);
  assert.equal(BM.isBellStroke({ type: "link", bell: 3 }), false);
  assert.equal(BM.bellOf(stroke(8)), 8);
  assert.equal(BM.bellOf(stroke(null)), null);
  assert.equal(BM.bellOf(null), null);
});

test("heartbeats, link and channel events, and junk do not move anything", () => {
  const r = rig();
  for (const m of [
    { schema: "sand.panel/v1", type: "heartbeat", bell: 1, body: { chan: [["trigger", "why"]] } },
    { schema: "sand.panel/v1", type: "stroke", bell: 1 },
    { schema: "sand.event/v1", type: "link", bell: 1, body: { what: "client" } },
    { schema: "sand.event/v1", type: "channel", ch: 1, bell: 1, body: { ch: 1, kind: "trigger" } },
    { tick: 5 }, {}, null, undefined, "stroke", 7,
  ]) r.move(m);
  assert.deepEqual(r.struck, []);
  assert.equal(BM.isStrokeOrTrigger(stroke(null)), true, "the older rule is kept as it was");
});

test("no element or no strike function: nothing happens", () => {
  assert.doesNotThrow(() => BM.create(null, () => assert.fail("struck"))(stroke(8)));
  assert.doesNotThrow(() => BM.create(fakeHost(), null)(stroke(8)));
});

/* bell_band.js in a sandbox: a fake document, a manual requestAnimationFrame, a host with
 * one clapper group per bell that records the transforms setTape gives it */
function band() {
  const frames = [];
  const claps = {};
  const host = {
    __bellBand: { mouthByBell: {}, tape: {} },
    querySelector: (sel) => {
      const m = /^\.bell-pad\[data-bell="(\d+)"\] \.bell-clapper-g$/.exec(sel);
      if (!m) return null;
      const b = m[1];
      claps[b] = claps[b] || { moves: [], setAttribute(k, v) { if (k === "transform") this.moves.push(v); } };
      return claps[b];
    },
  };
  for (let b = 1; b <= 8; b++) host.__bellBand.mouthByBell[b] = 20;
  const win = {};
  const sandbox = { window: win, document: {}, requestAnimationFrame: (fn) => frames.push(fn), Math };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "static", "js", "bell_band.js"), "utf8"), sandbox);
  const run = (n, ms) => {
    for (let i = 0; i < n && frames.length; i++) {
      const due = frames.splice(0);
      due.forEach((fn) => fn(i * ms));
    }
  };
  return { BB: win.BellBand, host, claps, frames, run };
}

test("settleDemo (the press movement) moves only that bell's clapper, and dies away to rest", () => {
  const b = band();
  b.BB.settleDemo(b.host, 8);
  b.run(2000, 16);
  assert.deepEqual(Object.keys(b.claps), ["8"]);
  const moves = b.claps[8].moves;
  assert.ok(new Set(moves).size > 10, "it swings");
  assert.equal(moves[moves.length - 1], "translate(0,0)", "back at rest at the end");
  assert.equal(b.frames.length, 0, "and stops asking for frames");
});

test("a second settle of the same bell takes over: one loop per bell, never two fighting", () => {
  const b = band();
  b.BB.settleDemo(b.host, 8);
  b.run(5, 16);
  b.BB.settleDemo(b.host, 8);
  b.BB.settleDemo(b.host, 3);
  assert.equal(b.frames.length, 3, "two queued frames for bell 8 and one for bell 3");
  b.run(1, 16);
  assert.equal(b.frames.length, 2, "the older bell 8 loop has stopped; the new one and bell 3 go on");
});

test("bell_band.js: each pad is placed by its own transform and its click is the press", () => {
  function node(tag) {
    return {
      tag, attrs: {}, children: [], style: {}, listeners: {},
      setAttribute(k, v) { this.attrs[k] = String(v); },
      appendChild(c) { this.children.push(c); return c; },
      addEventListener(ev, fn) { this.listeners[ev] = fn; },
      set innerHTML(v) { this.children = []; },
    };
  }
  const win = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "static", "js", "bell_band.js"), "utf8"),
    { window: win, document: { createElementNS: (ns, tag) => node(tag) } });
  const host = node("div");
  const pressed = [];
  win.BellBand.draw(host, { width: 250, height: 250, bells: [1, 2, 3, 4, 5, 6, 7, 8], onPadClick: (bell) => pressed.push(bell) });
  const pads = host.children[0].children.filter((c) => c.attrs.class === "bell-pad");
  assert.equal(pads.length, 8);
  for (const pad of pads) {
    assert.match(pad.attrs.transform, /^translate\(/);
    assert.ok(pad.children.some((c) => c.attrs.class === "bell-clapper-g"), "the clapper is in the pad");
  }
  const eight = pads.find((p) => p.attrs["data-bell"] === "8");
  eight.listeners.click({});
  assert.deepEqual(pressed, [8]);
  const clap = eight.children.find((c) => c.attrs.class === "bell-clapper-g").children.find((c) => c.attrs.class === "bell-clapper");
  assert.equal(clap.attrs.fill, "#8b0000", "bell 8's clapper is the brown one");
});
