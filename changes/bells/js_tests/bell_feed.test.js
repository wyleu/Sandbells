// node --test changes/bells/js_tests/  -- bell_feed.js: the home page's bell movement, driven by the events feed
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const BF = require("../static/js/bell_feed.js");
const BM = require("../static/js/bell_motion.js");
const RD = require("../static/js/reconnect_delay.js");

// as /events/api/since/ gives them: "bell" from the channel map, null for an unmapped channel
const stroke = (id) => ({ id, type: "stroke", src: "sandswing", ch: 1, bell: 8, body: { ch: 1 } });
const trigger = (id) => ({ id, type: "stroke", src: "sandswing", ch: 1, bell: 8, body: { ch: 1, test: true, src: "trigger" } });
const unmapped = (id) => ({ id, type: "stroke", src: "sandswing", ch: 7, bell: null, body: { ch: 7 } });
const link = (id) => ({ id, type: "link", src: "sandswing", body: { what: "client" } });
const channel = (id) => ({ id, type: "channel", src: "sandswing", body: { ch: 1, kind: "trigger" } });
const ingest = (id) => ({ id, type: "ingest", src: "host", body: { what: "connected" } });

/* a fake clock, fetch and document: answers is a queue of {events, latest_id} or "fail" */
function rig(extra) {
  const urls = [];
  const answers = [];
  const timers = [];
  const moved = [];
  const listeners = {};
  const doc = { visibilityState: "visible", addEventListener: (ev, fn) => { listeners[ev] = fn; } };
  const clock = { t: 0 };
  const env = {
    document: doc,
    fetch: (url, opts) => {
      urls.push(url);
      const a = answers.shift();
      if (a === "fail") return Promise.reject(new Error("net"));
      if (a === "http") return Promise.resolve({ ok: false, status: 502 });
      if (a === "throw") throw new Error("sync");
      return Promise.resolve({ ok: true, json: () => Promise.resolve(a) });
    },
    setTimeout: (fn, ms) => { timers.push({ fn, ms, at: clock.t + ms, live: true }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].live = false; },
  };
  const feed = BF.create(Object.assign({
    url: "/events/api/since/", pollMs: 1000, limit: 50, timeoutMs: 4000, moveMs: 350,
    accept: BM.isBellStroke, move: (e) => moved.push(e.id), env,
    rd: RD.create({ random: () => 0, now: () => clock.t }),
  }, extra || {}));
  const r = { urls, answers, timers, moved, doc, listeners, feed, clock };
  // run the next live timer (earliest first), then let promises settle
  r.step = async () => {
    const live = timers.filter((t) => t.live);
    live.sort((a, b) => a.at - b.at);
    const t = live[0];
    if (!t) return null;
    t.live = false;
    clock.t = Math.max(clock.t, t.at);
    t.fn();
    for (let i = 0; i < 6; i++) await Promise.resolve();
    return t;
  };
  r.settle = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
  r.pending = () => timers.filter((t) => t.live).map((t) => t.ms);
  return r;
}

test("the first answer only learns the newest id: stored events do not play back", async () => {
  const r = rig();
  r.answers.push({ events: [stroke(41), stroke(42)], latest_id: 42 });
  r.feed.start();
  await r.settle();
  assert.deepEqual(r.urls, ["/events/api/since/?type=&limit=1"]);
  assert.deepEqual(r.moved, []);
  assert.equal(r.feed.lastId(), 42);
  assert.deepEqual(r.pending(), [1000], "next poll in the farm page's 1 s");
});

test("an empty table starts from id 0", async () => {
  const r = rig();
  r.answers.push({ events: [], latest_id: null });
  r.feed.start();
  await r.settle();
  r.answers.push({ events: [stroke(1)], latest_id: 1 });
  await r.step();
  assert.equal(r.urls[1], "/events/api/since/?type=&limit=50&after=0");
  assert.deepEqual(r.moved, [1]);
});

test("later polls ask after the highest id seen and move once per stroke or trigger event", async () => {
  const r = rig();
  r.answers.push({ events: [stroke(10)], latest_id: 10 });
  r.feed.start(); await r.settle();
  r.answers.push({ events: [stroke(11), trigger(12)], latest_id: 12 });
  await r.step();
  assert.equal(r.urls[1], "/events/api/since/?type=&limit=50&after=10");
  assert.deepEqual(r.moved, [11]);            // the first movement is at once ...
  await r.step();                              // ... the next one after the first has played
  assert.deepEqual(r.moved, [11, 12]);
  r.answers.push({ events: [], latest_id: null });
  await r.step();                              // the 1 s poll
  assert.equal(r.urls[2], "/events/api/since/?type=&limit=50&after=12", "an empty answer keeps the id");
});

test("link, ingest and channel events do nothing, but still advance the id", async () => {
  const r = rig();
  r.answers.push({ events: [], latest_id: 5 });
  r.feed.start(); await r.settle();
  r.answers.push({ events: [link(6), ingest(7), channel(8)], latest_id: 8 });
  await r.step();
  assert.deepEqual(r.moved, []);
  assert.equal(r.feed.lastId(), 8);
});

test("a stroke with no bell number (unmapped channel) does nothing and takes no movement's place", async () => {
  const r = rig();
  r.answers.push({ events: [], latest_id: 50 });
  r.feed.start(); await r.settle();
  r.answers.push({ events: [unmapped(51), unmapped(52), unmapped(53), stroke(54)], latest_id: 54 });
  await r.step();
  assert.deepEqual(r.moved, [54], "played at once, not after three empty slots");
  assert.equal(r.feed.lastId(), 54);
});

test("a burst plays at most MAX_MOVES movements, 350 ms apart, and the rest are dropped", async () => {
  const r = rig();
  r.answers.push({ events: [], latest_id: 100 });
  r.feed.start(); await r.settle();
  const burst = [];
  for (let i = 101; i <= 140; i++) burst.push(stroke(i));
  r.answers.push({ events: burst, latest_id: 140 });
  await r.step();
  assert.deepEqual(r.moved, [101]);
  assert.ok(r.pending().includes(350), "the next movement moveMs (data-strike-gap-ms) later");
  await r.step(); await r.step(); await r.step();
  assert.deepEqual(r.moved, [101, 102, 103]);
  assert.equal(BF.MAX_MOVES, 3);
  assert.equal(r.feed.lastId(), 140);
});

test("a full answer is followed at once by the next poll, to catch up", async () => {
  const r = rig({ limit: 2 });
  r.answers.push({ events: [], latest_id: 1 });
  r.feed.start(); await r.settle();
  r.answers.push({ events: [link(2), link(3)], latest_id: 3 });
  await r.step();
  assert.deepEqual(r.pending(), [0]);
  r.answers.push({ events: [link(4)], latest_id: 4 });
  await r.step();
  assert.equal(r.urls[2], "/events/api/since/?type=&limit=2&after=3");
  assert.deepEqual(r.pending(), [1000]);
});

test("failures are ignored quietly and retried on the shared 1, 2, 4 ... s schedule; a good answer returns to 1 s", async () => {
  const r = rig();
  r.answers.push("fail", "http", "throw", { events: [], latest_id: 9 });
  r.feed.start(); await r.settle();
  assert.deepEqual(r.pending(), [1000]);
  await r.step();
  assert.deepEqual(r.pending(), [2000]);
  await r.step();
  assert.deepEqual(r.pending(), [4000]);
  await r.step();                              // a good answer
  assert.equal(r.feed.lastId(), 9);
  assert.deepEqual(r.pending(), [1000]);
  assert.deepEqual(r.moved, []);
});

test("an event after failures is still moved once, not lost or doubled", async () => {
  const r = rig();
  r.answers.push({ events: [], latest_id: 1 });
  r.feed.start(); await r.settle();
  r.answers.push("fail", { events: [stroke(2)], latest_id: 2 });
  await r.step(); await r.step();
  assert.deepEqual(r.moved, [2]);
  assert.equal(r.urls[2], "/events/api/since/?type=&limit=50&after=1");
});

test("a hidden tab does not poll; on return the newest id is learnt afresh, so nothing replays", async () => {
  const r = rig();
  r.answers.push({ events: [], latest_id: 20 });
  r.feed.start(); await r.settle();
  r.doc.visibilityState = "hidden";
  r.listeners.visibilitychange();
  assert.deepEqual(r.pending(), []);
  const n = r.urls.length;
  assert.equal(await r.step(), null);
  assert.equal(r.urls.length, n);
  r.doc.visibilityState = "visible";
  r.answers.push({ events: [stroke(29), stroke(30)], latest_id: 30 });
  r.listeners.visibilitychange(); await r.settle();
  assert.equal(r.urls[n], "/events/api/since/?type=&limit=1");
  assert.deepEqual(r.moved, []);
  assert.equal(r.feed.lastId(), 30);
});

test("an answer that arrives after the tab was hidden is dropped", async () => {
  const r = rig();
  r.answers.push({ events: [], latest_id: 20 });
  r.feed.start(); await r.settle();
  r.answers.push({ events: [stroke(21)], latest_id: 21 });
  const due = r.timers.filter((t) => t.live)[0];
  due.live = false;
  due.fn();                                    // poll goes out ...
  r.doc.visibilityState = "hidden";            // ... the tab hides before it answers
  r.listeners.visibilitychange();
  await r.settle();
  assert.deepEqual(r.moved, []);
  assert.deepEqual(r.pending(), []);
});

test("no fetch, or an answer that is not the expected shape: nothing breaks", async () => {
  const r = rig();
  r.answers.push("not an object");
  r.feed.start(); await r.settle();
  assert.deepEqual(r.moved, []);
  assert.equal(r.feed.lastId(), 0);
  const none = BF.create({ url: "/x", pollMs: 1, limit: 1, timeoutMs: 1, accept: () => true, move() {},
    env: { document: { visibilityState: "visible" }, setTimeout() { return 1; }, clearTimeout() {} } });
  assert.doesNotThrow(() => none.start());
});

test("the poll timeout aborts a request that never answers", async () => {
  const r = rig();
  let aborted = false;
  const env = {
    document: r.doc,
    AbortController: class { constructor() { this.signal = {}; } abort() { aborted = true; } },
    fetch: () => new Promise(() => {}),
    setTimeout: (fn, ms) => { r.timers.push({ fn, ms, at: ms, live: true }); return r.timers.length; },
    clearTimeout: () => {},
  };
  BF.create({ url: "/x", pollMs: 1000, limit: 50, timeoutMs: 4000, accept: () => true, move() {}, env }).start();
  assert.ok(r.timers.some((t) => t.ms === 4000));
  r.timers.find((t) => t.ms === 4000).fn();
  assert.equal(aborted, true);
});

test("in a browser it is window.BellFeed", () => {
  const vm = require("node:vm");
  const fs = require("node:fs");
  const path = require("node:path");
  const win = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "static", "js", "bell_feed.js"), "utf8"), { window: win });
  assert.equal(typeof win.BellFeed.create, "function");
});
