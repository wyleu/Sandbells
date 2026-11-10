// node --test changes/bells/js_tests/  -- farm_leds.js: the farm page Panel, live from /events/api/leds/
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const T = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(T, "events", "templates", "events", "led_echo.js"), "utf8") + "\n" +
            fs.readFileSync(path.join(T, "bells", "templates", "bells", "farm_leds.js"), "utf8");
const KEYS = ["led1", "led2", "led3", "led4", "led5", "led6"];
const CFG = { url: "/events/api/leds/", pollMs: 250, max: 4, timeoutMs: 4000, probeMs: 2000, keys: KEYS };
const PURPLE = [24, 0, 48], WHITE = [48, 48, 48];

function swatch(key, colour, title) {
  const attrs = { "data-key": key, "data-color": colour };
  return { style: { background: colour }, title,
           getAttribute: (k) => (k in attrs ? attrs[k] : null),
           hasAttribute: (k) => k in attrs,
           setAttribute: (k, v) => { attrs[k] = String(v); } };
}

function rig(replies) {
  let sw = [];
  const main = { querySelector: (q) => sw.find((s) => q === '.swatch[data-key="' + s.getAttribute("data-key") + '"]') || null };
  const timers = [];
  const observers = [];
  const calls = [];
  const doc = { hidden: false, getElementById: (id) => (id === "farm-main" ? main : null) };
  const ctx = {
    document: doc, console,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); },
    setInterval: (fn, ms) => { timers.push({ fn, ms, every: true }); },
    clearTimeout() {},
    MutationObserver: class { constructor(fn) { this.fn = fn; observers.push(this); } observe(t, o) { this.opts = o; } },
    fetch: (url) => { calls.push(url); const b = replies.next(); return Promise.resolve({ ok: true, json: () => Promise.resolve(b) }); },
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  const draw = () => {     // what farm_status.js render() does: new swatches, heartbeat colours
    sw = KEYS.map((k, i) => swatch(k, i === 4 ? "rgb(128,0,255)" : "rgb(0,255,0)", "hb " + k));
    observers.forEach((o) => o.fn());
  };
  draw();
  return { ctx, calls, timers, doc, observers, draw, sw: () => sw,
           async settle() { for (let i = 0; i < 10; i++) await new Promise(setImmediate); },
           async run(ms) {
             const all = timers.splice(0);
             all.filter((t) => t.every || t.ms !== ms).forEach((t) => timers.push(t));
             all.filter((t) => t.ms === ms).forEach((t) => t.fn());
             await this.settle();
           } };
}

function reply(n, recent) {
  const row = (c) => [[0, 32, 0], [0, 0, 24], PURPLE, [24, 12, 0], c, [24, 48, 0]];
  return { live: true, n, panel: row(recent[recent.length - 1]),
           panel_state: ["ws_client", "loopback", "trigger", "empty", "trigger", "ringing_down"],
           recent: recent.map((c, i) => ({ n: n - recent.length + 1 + i, p: row(c),
                                           s: ["", "", "", "", c === WHITE ? "response" : "trigger", ""] })) };
}

function seq(list) { let i = 0; return { next: () => list[Math.min(i++, list.length - 1)] }; }

test("farm Panel: the echo's colours, a flash between polls shown for one poll, same scaling", async () => {
  const r = rig(seq([reply(163, [PURPLE]), reply(165, [PURPLE, WHITE, PURPLE]), reply(165, [PURPLE, WHITE, PURPLE])]));
  r.ctx.FarmLeds.start(CFG, r.ctx.LedEcho);
  await r.settle();
  assert.equal(r.sw()[4].style.background, r.ctx.LedEcho.cssColour(PURPLE));
  assert.equal(r.sw()[5].style.background, "rgb(128,255,0)");            // not the heartbeat's green
  await r.run(250);
  assert.equal(r.sw()[4].style.background, "rgb(255,255,255)");
  assert.equal(r.sw()[4].title, "response");
  await r.run(250);
  assert.equal(r.sw()[4].style.background, "rgb(128,0,255)");
});

test("farm Panel: a status redraw gets the echo back at once (MutationObserver on #farm-main)", async () => {
  const r = rig(seq([reply(7, [WHITE])]));
  r.ctx.FarmLeds.start(CFG, r.ctx.LedEcho);
  await r.settle();
  assert.equal(JSON.stringify(r.observers[0].opts), JSON.stringify({ childList: true }));
  r.draw();
  assert.equal(r.sw()[4].style.background, "rgb(255,255,255)");
});

test("farm Panel: not live -> the heartbeat colours and titles; looked for again every probeMs", async () => {
  const r = rig(seq([reply(7, [WHITE]), { live: false, panel: null }, { live: false, panel: null }, reply(9, [WHITE])]));
  r.ctx.FarmLeds.start(CFG, r.ctx.LedEcho);
  await r.settle();
  assert.equal(r.sw()[4].style.background, "rgb(255,255,255)");
  await r.run(250);
  assert.equal(r.sw()[4].style.background, "rgb(128,0,255)");           // data-color
  assert.equal(r.sw()[4].title, "hb led5");
  await r.run(250);                                                      // stopped: no fetch
  assert.equal(r.calls.length, 2);
  await r.run(CFG.probeMs);                                              // the probe
  assert.equal(r.calls.length, 3);
  await r.run(CFG.probeMs);                                              // live again ...
  await r.run(250);                                                      // ... at the next poll
  assert.equal(r.calls.length, 4);
  assert.equal(r.sw()[4].style.background, "rgb(255,255,255)");
});

test("farm Panel: hidden page, no fetch", async () => {
  const r = rig(seq([reply(7, [WHITE])]));
  r.doc.hidden = true;
  r.ctx.FarmLeds.start(CFG, r.ctx.LedEcho);
  await r.settle();
  await r.run(CFG.probeMs);
  assert.equal(r.calls.length, 0);
  assert.equal(r.sw()[4].style.background, "rgb(128,0,255)");
});
