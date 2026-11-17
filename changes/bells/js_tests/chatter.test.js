// node --test changes/bells/js_tests/  -- chatter.js (the sandheads chatter test) inside align.js, USB path
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "static", "js");
const read = (f) => fs.readFileSync(path.join(JS, f), "utf8");
const SCHEMA = "sand.panel/v1";
const FULL = 65535;
const LINEUP = { plateau_frac: 0.05, margin_frac: 0.2, min_range_v: 0.05, slots: 8, labelMax: 8 };
const CHAT = { passes: 2, speed_dps: 4, pad_deg: 2, face: "reflector", fast_pwm_hz: 20000,
               drives_pct: [100, 52, 25], pwmMin: 200, pwmMax: 150000, pwmNow: 1000, transPerPass: 4 };
const HEADS = { "1": { angle_deg: -45, width_deg: 4 }, "2": { angle_deg: -15, width_deg: 4 } };
const FACES = { mirror: 0, reflector: 180 };
const rigReply = (mode, done) => ({ ok: true, reachable: true,
  rig: { ok: true, sweep: { mode, cycles_done: done || 0, heads: HEADS, faces: FACES } } });

class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.className = ""; this.textContent = ""; this.value = "";
    this.attrs = {}; this.handlers = {}; this.disabled = false; this.id = "";
    this.clientWidth = 400; this.clientHeight = 140; this.width = 0; this.height = 0;
  }
  appendChild(c) { this.children.push(c); if (this.tag === "select" && this.children.length === 1) this.value = c.value; return c; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(ev, fn) { (this.handlers[ev] = this.handlers[ev] || []).push(fn); }
  fire(ev) { for (const f of this.handlers[ev] || []) f(); }
  click() { this.fire("click"); }
  getContext() { const c = {}; for (const m of ["fillRect", "moveTo", "lineTo", "stroke", "beginPath", "fillText"]) c[m] = () => {}; return c; }
  set innerHTML(v) { this.children = []; }
  find(pred, out = []) { if (pred(this)) out.push(this); for (const c of this.children) c.find(pred, out); return out; }
}

function rig(withChatter = true) {
  const ids = {};
  for (const id of ["align-main", "align-heads", "align-link", "align-tower"]) ids[id] = new El("x");
  const xhrs = [];
  class XHR {
    constructor() { this.headers = {}; xhrs.push(this); this.done = false; }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(k, v) { this.headers[k] = v; }
    send(body) { this.body = body == null ? null : JSON.parse(body); }
    reply(status, obj) { this.done = true; this.status = status; this.responseText = JSON.stringify(obj); if (this.onload) this.onload(); }
  }
  const timers = [];
  const store = {};
  const win = { XMLHttpRequest: XHR, addEventListener() {}, location: { hash: "" },
                sessionStorage: { getItem: () => null, setItem() {} }, history: { replaceState() {} },
                localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } } };
  const document = { visibilityState: "visible", cookie: "csrftoken=tok", getElementById: (id) => ids[id] || null,
                     createElement: (t) => new El(t), addEventListener() {} };
  const sandbox = { window: win, document, WebSocket: function () {}, console,
    setInterval: (fn, ms) => { timers.push({ fn, ms, kind: "i" }); return timers.length; },
    setTimeout: (fn, ms) => { timers.push({ fn, ms, kind: "t" }); return timers.length; },
    clearTimeout() {}, clearInterval() {}, Date, JSON, Math, parseInt, String };
  vm.createContext(sandbox);
  vm.runInContext(read("reconnect_delay.js"), sandbox);
  vm.runInContext(read("lineup.js"), sandbox);
  if (withChatter) vm.runInContext(read("chatter.js"), sandbox);
  vm.runInContext(read("align.js"), sandbox);
  sandbox.window.Align.start({ via: "serial", activeKinds: ["head_new", "head_old"], lineup: LINEUP, chatter: CHAT,
    serial: { cmdUrl: "/c/", pollUrl: "/p/", logUrl: "/l/", sweepLogUrl: "/s/", pollMs: 400, liveMs: 3000,
              chatterLogUrl: "/cl/", chatterCsvUrl: "/cc.csv", sandtestCmdUrl: "/tc/", sandtestStatusUrl: "/ts/" } });
  const r = { ids, xhrs, timers, store, win: sandbox.window };
  r.poll = (items, extra) => {
    const gets = xhrs.filter((x) => x.method === "GET" && x.url.indexOf("/p/") === 0);
    gets[gets.length - 1].reply(200, Object.assign({ running: true, connected: true, n: 0, items: [],
      heartbeat: { schema: SCHEMA, type: "heartbeat", body: { tower: (extra || {}).tower || "inactive",
                   chan: [["head_new"], ["head_old"], ["empty"]], pt: [1, 2.1, 0.01] } },
      midi: { running: true, connected: true, n: (r.n = (r.n || 0) + (items || []).length), items: items || [] } }, {}));
    timers.filter((t) => t.ms === 400 && t.kind === "i")[0].fn();
  };
  r.open = (url) => xhrs.filter((x) => x.url.indexOf(url) === 0 && !x.done);
  r.posts = () => xhrs.filter((x) => x.method === "POST" && x.url === "/c/").map((x) => x.body);
  r.card = () => ids["align-main"].find((e) => e.tag === "section")[0];
  r.panel = () => r.card().find((e) => e.className.split(" ")[0] === "chatter")[0];
  r.btn = (label) => r.panel().find((e) => e.tag === "button" && e.textContent === label)[0];
  r.cls = (c) => r.panel().find((e) => e.className.split(" ")[0] === c)[0];
  r.msg = (type, body) => ({ schema: SCHEMA, type, body });
  r.fire = (ms) => { let n = 0; for (const t of timers) if (t.kind === "t" && t.ms === ms && !t.fired) { t.fired = true; t.fn(); n++; } return n; };
  return r;
}

function ready(r) {
  r.poll([]);
  for (const x of r.open("/cl/")) x.reply(200, { rows: [] });
  for (const x of r.open("/ts/")) x.reply(200, rigReply("idle"));
  r.poll([r.msg("align", { ch: 1, n: 1, bits: "80", thr: 32768, drv: FULL, tower: "inactive" }),
          r.msg("align_ack", { what: "scope", ch: 1, ok: true, why: null, thr: 32768, drv: FULL, pwm_hz: 1000,
                               tower: "inactive" })]);
}

/* answers whatever the page is waiting for: the concentrator (acks, the
   count), sandtest (moving once, then idle) and Django (the log) */
function autopilot(r, counts, opts = {}) {
  let seen = opts.from === undefined ? r.posts().length : opts.from;
  let hz = 1000, drv = FULL;
  let moving = 0;
  const log = [];
  for (let k = 0; k < 400; k++) {
    let did = false;
    for (const x of r.open("/tc/")) {
      log.push(x.body);
      if (x.body.cmd === "sweep") moving = 1;
      x.reply(200, { ok: true, reachable: true, rig: { ok: true } }); did = true;
    }
    for (const x of r.open("/ts/")) { x.reply(200, rigReply(moving ? "sweep" : "idle")); moving = 0; did = true; }
    for (const x of r.open("/cl/")) {
      if (x.method === "POST") x.reply(200, { ok: true, row: Object.assign({ id: k, at: "2026-11-17T17:00:00Z" }, x.body) });
      did = true;
    }
    const posts = r.posts();
    if (posts.length > seen) {
      const items = [];
      for (const p of posts.slice(seen)) {
        if (p.scope) continue;
        if (p.use) {
          const why = opts.busyOnce && !opts.busied ? (opts.busied = true, "tower not quiet: strokes in progress") : null;
          if (!why) drv = p.use[0];
          items.push(r.msg("align_ack", { what: "use", ch: 1, ok: !why, why, thr: 32768, drv, pwm_hz: hz, tower: "inactive" }));
        } else if (p.pwm_hz) {
          hz = p.pwm_hz;
          items.push(r.msg("align_ack", { what: "pwm", ch: 1, ok: true, why: null, thr: 32768, drv, pwm_hz: hz, tower: "inactive" }));
        } else if (p.chatter) {
          items.push(r.msg("align_ack", { what: "chatter", ch: 1, ok: true, why: null, thr: 32768, drv, pwm_hz: hz, tower: "inactive" }));
          if (p.chatter === "stop") items.push(r.msg("align_chatter", Object.assign({ ch: 1, on: false }, counts(drv, hz))));
        }
      }
      seen = posts.length;
      if (items.length) { r.poll(items); did = true; }
    }
    if (!did) {
      for (const ms of [500, 1000, 1500]) if (r.fire(ms)) { did = true; break; }
    }
    if (!did) break;
  }
  return log;
}

test("helpers: the set, the vane's span from sandtest's heads and faces, its commands, the limits", () => {
  const C = rig().win.Chatter;
  assert.deepEqual(JSON.parse(JSON.stringify(C.plan(CHAT))),
                   [{ pct: 100, hz: 1000 }, { pct: 52, hz: 1000 }, { pct: 25, hz: 1000 }, { pct: 25, hz: 20000 }]);
  const span = C.rigSpan(rigReply("idle").rig, "1", "reflector", CHAT);
  assert.deepEqual(JSON.parse(JSON.stringify(span)), { from: 131, to: 139 });      // -45 + 180, +-(2 + 2)
  assert.match(C.rigSpan(rigReply("idle").rig, "7", "reflector", CHAT).error, /no position 7/);
  assert.match(C.rigSpan(rigReply("idle").rig, "1", "glass", CHAT).error, /no face/);
  // only commands sandtest's own page sends (sweep mode: from, to, speed, cycles)
  assert.deepEqual(JSON.parse(JSON.stringify(C.rigSweep(span, CHAT, 10))),
                   { cmd: "sweep", mode: "sweep", from_deg: 131, to_deg: 139, speed_dps: 4, cycles: 10 });
  assert.deepEqual(JSON.parse(JSON.stringify(C.rigPrep(span, CHAT))),
                   { cmd: "sweep", mode: "sweep", from_deg: 129, to_deg: 131, speed_dps: 4, cycles: 1 });
  assert.equal(C.runMs(span, CHAT, 10), 40000);
  // 10 round trips of 16 deg at 4 deg/s = 40 s; given up after 1.5x + 20 s
  assert.equal(C.runLimitMs(span, CHAT, 10), 80000);
  assert.equal(C.dutyOf(52), 34078);
  assert.equal(C.dutyOf(100), FULL);
  assert.equal(C.cleanPct(40, 38), 95);
  assert.equal(C.cleanPct(0, 0), null);
  assert.ok(C.retryable("tower not quiet: strokes in progress") && C.retryable("too fast"));
  assert.ok(!C.retryable("PWM speed out of range"));
  assert.equal(C.hzText(20000), "20 kHz");
  assert.equal(C.hzText(990), "990 Hz");
});

test("Run the set: 100 / 52 / 25 % at 1 kHz then 25 % at 20 kHz, sandtest sweeps each, rows kept, all put back", () => {
  const r = rig();
  ready(r);
  const pos = r.cls("lslot") && r.panel().find((e) => e.tag === "select")[2];
  assert.equal(pos.value, "1", "first sandtest position picked");
  const set = r.btn("Run the set");
  assert.equal(set.disabled, false);
  set.click();
  const counts = (drv, hz) => (drv < 40000 && hz === 1000 ?
    { trans: 8, clean: 5, max_edges: 7, mean_x10: 25, max_burst_ms: 6, spurious: 4 } :
    { trans: 8, clean: 8, max_edges: 1, mean_x10: 10, max_burst_ms: 0, spurious: 0 });
  const rigCmds = autopilot(r, counts);
  const cmds = r.posts().filter((p) => p.use || p.pwm_hz || p.chatter);
  // the Pico: drive, (PWM), start, stop per run; then PWM and drive back
  const uses = cmds.filter((p) => p.use).map((p) => p.use[0]);
  assert.deepEqual(uses, [FULL, 34078, 16384, 16384, FULL]);
  assert.deepEqual(cmds.filter((p) => p.pwm_hz).map((p) => p.pwm_hz), [20000, 1000]);
  assert.equal(cmds.filter((p) => p.chatter === "start").length, 4);
  assert.equal(cmds.filter((p) => p.chatter === "stop").length, 4);
  // sandtest: to the start, then the sweep, per run
  assert.deepEqual(rigCmds.map((c) => c.cycles), [1, 2, 1, 2, 1, 2, 1, 2]);
  assert.ok(rigCmds.every((c) => c.cmd === "sweep" && c.mode === "sweep" && !("face" in c)));
  assert.equal(rigCmds[0].to_deg, rigCmds[1].from_deg);       // the count's sweep starts where the vane waits
  // four rows logged and shown, newest first
  const logged = r.xhrs.filter((x) => x.method === "POST" && x.url === "/cl/").map((x) => x.body);
  assert.equal(logged.length, 4);
  assert.deepEqual(logged.map((l) => [l.drv, l.pwm_hz]), [[FULL, 1000], [34078, 1000], [16384, 1000], [16384, 20000]]);
  assert.equal(logged[1].clean, 5);
  assert.equal(logged[0].passes, 2);
  const rows = r.cls("ctable").children.slice(1);
  assert.equal(rows.length, 4);
  assert.match(rows[0].children[3].textContent, /20 kHz/);
  assert.equal(rows[0].className, "good");
  assert.equal(rows[2].className, "bad");                          // 52 % chattered
  assert.match(rows[2].children[5].textContent, /62.5 %/);
  assert.match(r.cls("lstatus").textContent, /Done/);
  assert.equal(r.btn("Start").disabled, false);
});

test("a single run waits for a quiet tower, and Stop by hand records the run and puts the drive back", () => {
  const r = rig();
  ready(r);
  const sel = r.panel().find((e) => e.tag === "select");
  sel[0].value = "25";
  sel[2].value = "0";                                                 // vane by hand
  sel[2].fire("change");
  assert.equal(r.btn("Run the set").disabled, true);
  const from = r.posts().length;
  r.btn("Start").click();
  const counts = () => ({ trans: 3, clean: 3, max_edges: 1, mean_x10: 10, max_burst_ms: 0, spurious: 0 });
  autopilot(r, counts, { busyOnce: true, from });
  const cmds = r.posts().filter((p) => p.use || p.pwm_hz || p.chatter);
  assert.deepEqual(cmds.slice(0, 3), [{ cmd: "align", ch: 1, use: [16384, null] },
                                      { cmd: "align", ch: 1, use: [16384, null] },    // asked again
                                      { cmd: "align", ch: 1, chatter: "start" }]);
  assert.match(r.cls("lstatus").textContent, /press Stop/);
  assert.equal(r.btn("Stop").disabled, false);
  const from2 = r.posts().length;
  r.btn("Stop").click();
  autopilot(r, counts, { from: from2 });
  const after = r.posts().filter((p) => p.use || p.pwm_hz || p.chatter).slice(3);
  assert.deepEqual(after, [{ cmd: "align", ch: 1, chatter: "stop" }, { cmd: "align", ch: 1, use: [FULL, null] }]);
  const logged = r.xhrs.filter((x) => x.method === "POST" && x.url === "/cl/").map((x) => x.body);
  assert.equal(logged.length, 1);
  assert.equal(logged[0].passes, null);
  assert.equal(logged[0].trans, 3);
  assert.match(r.cls("lstatus").textContent, /Stopped/);
});

test("a refusal that is not about a busy tower stops the test and still puts things back", () => {
  const r = rig();
  ready(r);
  r.panel().find((e) => e.tag === "select")[1].value = "20000";
  r.panel().find((e) => e.tag === "select")[2].value = "0";
  r.btn("Start").click();
  r.poll([r.msg("align_ack", { what: "use", ch: 1, ok: true, why: null, drv: 65535, pwm_hz: 1000 })]);
  assert.deepEqual(r.posts().pop(), { cmd: "align", ch: 1, pwm_hz: 20000 });
  r.poll([r.msg("align_ack", { what: "pwm", ch: 1, ok: false, why: "PWM speed not changed", drv: 65535, pwm_hz: 1000 })]);
  assert.match(r.cls("msg").textContent, /Not changed: PWM speed not changed/);
  assert.deepEqual(r.posts().pop(), { cmd: "align", ch: 1, use: [FULL, null] });      // drive back
  r.poll([r.msg("align_ack", { what: "use", ch: 1, ok: true, why: null, drv: 65535, pwm_hz: 1000 })]);
  assert.equal(r.btn("Start").disabled, false);
});

test("no answer from the concentrator: given up after a while, not stuck busy", () => {
  const r = rig();
  ready(r);
  r.panel().find((e) => e.tag === "select")[2].value = "0";
  r.btn("Start").click();
  r.fire(6000);                                                       // the use ack never came
  assert.match(r.cls("msg").textContent, /No answer from the concentrator/);
  r.fire(6000);                                                       // nor the restore's
  assert.equal(r.btn("Start").disabled, false);
});

test("the page without chatter.js still works (older static files)", () => {
  const r = rig(false);
  r.poll([]);
  assert.equal(r.card().find((e) => e.className.split(" ")[0] === "chatter").length, 0);
});
