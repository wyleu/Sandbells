// node --test changes/bells/js_tests/  -- bell_motion.js, the small diagonal movement of the bell that struck
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const BM = require("../static/js/bell_motion.js");

const LOOK = { ms: 350, px: 4 };

function fakeEl() {
  const set = new Set();
  return { set, classList: { add: (c) => set.add(c), remove: (c) => set.delete(c) } };
}
/* #bell-circle with one .bell-quiver group per drawn bell (1..8), as bell_band.js draws it */
function fakeHost(bells) {
  const groups = {};
  const props = {};
  const asked = [];
  for (const b of bells || [1, 2, 3, 4, 5, 6, 7, 8]) groups[b] = fakeEl();
  return {
    groups, props, asked,
    style: { setProperty: (k, v) => { props[k] = v; } },
    querySelector: (sel) => {
      asked.push(sel);
      const m = /^\.bell-pad\[data-bell="(\d+)"\] \.bell-quiver$/.exec(sel);
      return m && groups[m[1]] ? groups[m[1]] : null;
    },
  };
}
const moving = (host) => Object.keys(host.groups).filter((b) => host.groups[b].set.size).map(Number);

// what /events/api/since/ gives: "bell" from the channel map, null when the channel is unmapped
const stroke = (bell) => ({ schema: "sand.event/v1", type: "stroke", src: "sandswing", ch: 3, bell, body: { ch: 3 } });
const trigger = (bell) => ({ type: "stroke", src: "sandswing", ch: 1, bell, body: { ch: 1, test: true, src: "trigger" } });

test("a stroke for bell 8 moves only bell 8's group, not the circle or another bell", () => {
  const host = fakeHost();
  BM.create(host, LOOK)(stroke(8));
  assert.deepEqual(moving(host), [8]);
  assert.deepEqual([...host.groups[8].set], ["bell-motion-1"]);
  assert.deepEqual(host.asked, ['.bell-pad[data-bell="8"] .bell-quiver']);
});

test("a trigger plug test stroke moves its bell too", () => {
  const host = fakeHost();
  BM.create(host, LOOK)(trigger(2));
  assert.deepEqual(moving(host), [2]);
});

test("the length and distance come from the page (data-quiver-*), as CSS variables on the circle", () => {
  const host = fakeHost();
  BM.create(host, LOOK);
  assert.deepEqual(host.props, { "--bell-motion-ms": "350ms", "--bell-motion-px": "4px" });
});

test("no bell number (unmapped channel, or none given) or a bell not drawn: nothing moves", () => {
  const host = fakeHost();
  const move = BM.create(host, LOOK);
  for (const m of [stroke(null), stroke(undefined), trigger(null), { ch: 2, test: true, src: "trigger" },
    stroke(9), stroke(0), stroke(-1), stroke(2.5), stroke("8")]) move(m);
  assert.deepEqual(moving(host), []);
  assert.deepEqual(host.asked, ['.bell-pad[data-bell="9"] .bell-quiver']);   // asked, not drawn
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
  const host = fakeHost();
  const move = BM.create(host, LOOK);
  for (const m of [
    { schema: "sand.panel/v1", type: "heartbeat", bell: 1, body: { chan: [["trigger", "why"]] } },
    { schema: "sand.panel/v1", type: "stroke", bell: 1 },
    { schema: "sand.event/v1", type: "link", bell: 1, body: { what: "client" } },
    { schema: "sand.event/v1", type: "channel", ch: 1, bell: 1, body: { ch: 1, kind: "trigger" } },
    { tick: 5 }, {}, null, undefined, "stroke", 7,
  ]) move(m);
  assert.deepEqual(moving(host), []);
  assert.equal(BM.isStrokeOrTrigger(stroke(null)), true, "the older rule is kept as it was");
});

test("each bell switches between two animation names on its own, so a burst restarts that bell", () => {
  const host = fakeHost();
  const move = BM.create(host, LOOK);
  const seen = [];
  for (let i = 0; i < 3; i++) { move(stroke(8)); seen.push([...host.groups[8].set].join()); }
  assert.deepEqual(seen, ["bell-motion-1", "bell-motion-0", "bell-motion-1"]);
  move(stroke(1));
  assert.deepEqual([...host.groups[1].set], ["bell-motion-1"], "bell 1 starts its own alternation");
  assert.deepEqual([...host.groups[8].set], ["bell-motion-1"], "bell 8 is left as it was");
});

test("no element: nothing happens", () => {
  assert.doesNotThrow(() => BM.create(null, LOOK)(stroke(8)));
  assert.doesNotThrow(() => BM.create(null)(stroke(8)));
});

/* bell_band.js draws each pad as <g class="bell-pad" data-bell=N transform=translate(x,y)>
 * holding one <g class="bell-quiver"> with the bell's drawing, which is what moves */
function fakeDom() {
  function node(tag) {
    const n = {
      tag, attrs: {}, children: [], style: {}, listeners: {},
      setAttribute(k, v) { this.attrs[k] = String(v); },
      getAttribute(k) { return this.attrs[k]; },
      appendChild(c) { this.children.push(c); c.parent = this; return c; },
      addEventListener(ev, fn) { this.listeners[ev] = fn; },
      set innerHTML(v) { this.children = []; },
    };
    return n;
  }
  return { createElementNS: (ns, tag) => node(tag), node };
}

test("bell_band.js: each pad keeps its place on the circle and wraps its drawing in one .bell-quiver", () => {
  const dom = fakeDom();
  const win = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "static", "js", "bell_band.js"), "utf8"),
    { window: win, document: dom });
  const host = dom.node("div");
  win.BellBand.draw(host, { width: 250, height: 250, bells: [1, 2, 3, 4, 5, 6, 7, 8], onPadClick() {} });
  const svg = host.children[0];
  const pads = svg.children.filter((c) => c.attrs.class === "bell-pad");
  assert.equal(pads.length, 8);
  for (const pad of pads) {
    assert.match(pad.attrs.transform, /^translate\(/);
    assert.equal(pad.children.length, 1);
    const body = pad.children[0];
    assert.equal(body.attrs.class, "bell-quiver");
    assert.equal(body.attrs.transform, undefined, "the moving group has no placement of its own");
    const classes = body.children.map((c) => c.attrs.class);
    assert.ok(classes.includes("bell-clapper-g") && classes.includes("bell-num"), classes.join());
    assert.equal(typeof pad.listeners.click, "function", "a click on the pad still works");
  }
  const brown = pads.find((p) => p.attrs["data-bell"] === "8").children[0].children
    .find((c) => c.attrs.class === "bell-clapper-g").children.find((c) => c.attrs.class === "bell-clapper");
  assert.equal(brown.attrs.fill, "#8b0000", "bell 8 is the brown one");
});
