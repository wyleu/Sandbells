// node --test changes/bells/js_tests/  -- reconnect_delay.js, the one reconnect schedule of every page
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FILE = path.join(__dirname, "..", "static", "js", "reconnect_delay.js");
const RD = require(FILE);

function rig(random) {
  const clock = { t: 1000000 };
  const rd = RD.create({ now: () => clock.t, random: random || (() => 0) });   // 0 = no jitter cut
  return { rd, clock };
}

test("delays grow 1, 2, 4, 8, 15 s and stay at the cap", () => {
  const { rd } = rig();
  const got = [];
  for (let i = 0; i < 9; i++) got.push(rd.closed());
  assert.deepEqual(got, [1000, 2000, 4000, 8000, 15000, 15000, 15000, 15000, 15000]);
  assert.equal(rd.attempts(), 9);
});

test("jitter only shortens the delay, by at most 30 %, and never past the cap", () => {
  const lo = rig(() => 0.999);
  const hi = rig(() => 0);
  for (let i = 0; i < 8; i++) {
    const a = lo.rd.closed();
    const b = hi.rd.closed();
    assert.ok(a <= b && a >= Math.floor(b * 0.7), `${a} vs ${b}`);
    assert.ok(b <= 15000);
  }
  const r = rig(Math.random);
  for (let i = 0; i < 200; i++) {
    r.rd.reset();
    const d = r.rd.closed();
    assert.ok(d >= 700 && d <= 1000, d);          // never an instant retry
  }
});

test("a connection that dies at once does not restart the climb (the 10 s Pico replay storm)", () => {
  const { rd, clock } = rig();
  const got = [];
  for (let i = 0; i < 5; i++) {
    rd.opened();
    clock.t += 1500;                               // up 1.5 s, then dropped by the Pico
    got.push(rd.closed());
  }
  assert.deepEqual(got, [1000, 2000, 4000, 8000, 15000]);
});

test("a connection that stayed up 30 s starts again at 1 s", () => {
  const { rd, clock } = rig();
  rd.closed(); rd.closed(); rd.closed();
  rd.opened();
  clock.t += 29999;
  assert.equal(rd.closed(), 8000);                 // 29.999 s is not stable
  rd.opened();
  clock.t += 30000;
  assert.equal(rd.closed(), 1000);
  assert.equal(rd.closed(), 2000);
});

test("a socket that never opened (503, no route) keeps climbing", () => {
  const { rd, clock } = rig();
  clock.t += 100000;                               // lots of idle time proves nothing
  assert.deepEqual([rd.closed(), rd.closed(), rd.closed()], [1000, 2000, 4000]);
});

test("reset (page visible again) goes back to the first delay", () => {
  const { rd } = rig();
  rd.closed(); rd.closed(); rd.closed();
  rd.reset();
  assert.equal(rd.closed(), 1000);
});

test("options override the defaults; instances do not share state", () => {
  const a = RD.create({ baseMs: 500, capMs: 2000, random: () => 0 });
  const b = RD.create({ random: () => 0 });
  assert.deepEqual([a.closed(), a.closed(), a.closed(), a.closed()], [500, 1000, 2000, 2000]);
  assert.equal(b.closed(), 1000);
  assert.equal(RD.DEFAULTS.capMs, 15000);
});

test("in a browser it is window.ReconnectDelay", () => {
  const win = {};
  vm.runInNewContext(fs.readFileSync(FILE, "utf8"), { window: win });
  assert.equal(typeof win.ReconnectDelay.create, "function");
});

test("every page that reconnects uses it, none keeps its own delay", () => {
  const dir = path.join(__dirname, "..", "static", "js");
  for (const f of ["farm_status.js", "align.js", "kiosk_bells.js", "tick-ws.js"]) {
    const src = fs.readFileSync(path.join(dir, f), "utf8");
    assert.match(src, /ReconnectDelay\.create\(\)/, f);
    assert.doesNotMatch(src, /Math\.min\([^)]*15000\)/, f + " has its own backoff");
    assert.doesNotMatch(src, /setTimeout\([^,]+,\s*2000\)/, f + " has a fixed delay");
  }
});
