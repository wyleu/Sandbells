// node --test changes/bells/js_tests/  -- align.js against a fake DOM and a fake WebSocket
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "static", "js", "align.js"), "utf8");
const SCHEMA = "sand.panel/v1";

class Ctx {                       // canvas 2d recorder
  constructor() { this.calls = []; }
}
for (const m of ["fillRect", "moveTo", "lineTo", "stroke", "beginPath", "fillText"]) {
  Ctx.prototype[m] = function (...a) { this.calls.push([m, ...a]); };
}

class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.className = ""; this.textContent = "";
    this.attrs = {}; this.handlers = {}; this.disabled = false; this.id = "";
    this.clientWidth = 400; this.clientHeight = 80; this.width = 0; this.height = 0;
    this.ctx = new Ctx(); this.title = "";
  }
  appendChild(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(ev, fn) { (this.handlers[ev] = this.handlers[ev] || []).push(fn); }
  click() { for (const f of this.handlers.click || []) f(); }
  getContext() { return this.ctx; }
  set innerHTML(v) { this.children = []; }
  find(pred, out = []) {
    if (pred(this)) out.push(this);
    for (const c of this.children) c.find(pred, out);
    return out;
  }
}

function rig(cfg) {
  const ids = {};
  for (const id of ["align-main", "align-link", "align-tower"]) { ids[id] = new El("x"); ids[id].id = id; }
  const sockets = [];
  class WS {
    constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this); }
    send(t) { this.sent.push(JSON.parse(t)); }
    close() { if (this.readyState === 3) return; this.readyState = 3; if (this.onclose) this.onclose(); }
    open() { this.readyState = 1; this.onopen(); }
    recv(obj) { this.onmessage({ data: typeof obj === "string" ? obj : JSON.stringify(obj) }); }
  }
  const timers = [];
  const listeners = {};
  const document = {
    visibilityState: "visible",
    getElementById: (id) => ids[id] || null,
    createElement: (t) => new El(t),
    addEventListener: (ev, fn) => { listeners[ev] = fn; },
  };
  const sandbox = {
    window: { addEventListener() {} }, document, WebSocket: WS, console,
    setInterval: (fn, ms) => { timers.push({ fn, ms, kind: "i" }); return timers.length; },
    setTimeout: (fn, ms) => { timers.push({ fn, ms, kind: "t" }); return timers.length; },
    clearTimeout() {}, clearInterval() {}, Date, JSON, Math, parseInt, String,
  };
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox);
  const Align = sandbox.window.Align;
  Align.start(Object.assign({ wsUrls: ["ws://home/ws", "ws://tower/ws"], keepAliveMs: 2000,
                              windowMs: 2000, activeKinds: ["head_new", "head_old"] }, cfg || {}));
  const kinds = ["head_new", "head_old", "empty", "trigger", "fault", "loopback", "unknown", "empty"];
  const msg = (type, body) => ({ schema: SCHEMA, type, src: "sandswing", seq: 1, body });
  return { ids, sockets, timers, document, listeners, Align, kinds, msg,
           cards: () => ids["align-main"].find((e) => e.tag === "section"),
           buttons: (card, label) => card.find((e) => e.tag === "button" && e.textContent === label),
           text: (card, cls) => card.find((e) => e.className.split(" ")[0] === cls) };
}

test("decodeRuns: oldest first, MSB first", () => {
  const { Align } = rig();
  const j = (x) => JSON.parse(JSON.stringify(x));      // arrays from the vm have another prototype
  assert.deepEqual(j(Align.decodeRuns("f81f", 16)), [[0, 4, 1], [5, 10, 0], [11, 15, 1]]);
  assert.deepEqual(j(Align.decodeRuns("80", 3)), [[0, 0, 1], [1, 2, 0]]);
  assert.deepEqual(j(Align.decodeRuns("", 0)), []);
});

test("connects to the first address, asks for info, a card per ACTIVE head only", () => {
  const r = rig();
  assert.equal(r.sockets[0].url, "ws://home/ws");
  r.sockets[0].open();
  assert.deepEqual(r.sockets[0].sent[0], { cmd: "align", info: true });
  r.sockets[0].recv(r.msg("align_info", { kinds: r.kinds, active: [1, 2], tower: "inactive" }));
  const cards = r.cards();
  assert.equal(cards.length, 2);                       // not empty/trigger/fault/loopback/unknown
  assert.deepEqual(cards.map((c) => c.attrs["data-ch"]), ["1", "2"]);
  // the first active head is watched: scope requested
  assert.ok(r.sockets[0].sent.some((m) => m.cmd === "align" && m.ch === 1 && m.scope === true));
  assert.match(cards[0].className, /watching/);
  assert.match(cards[1].className, /off/);
  assert.equal(r.ids["align-link"].textContent, "live");
  assert.equal(r.ids["align-tower"].textContent, "tower quiet");
});

test("a frame fills the readouts and draws the trace", () => {
  const r = rig();
  r.sockets[0].open();
  r.sockets[0].recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  r.sockets[0].recv(r.msg("align", { ch: 1, n: 16, dt: 20, gap: 20, bits: "f81f", ma: 4.9,
                                     rb: 23500, thr: 23500, drv: 63000, tower: "inactive", busy: false }));
  const card = r.cards()[0];
  const vals = r.text(card, "val").map((e) => e.textContent);
  assert.deepEqual(vals, ["4.9 mA", "23500", "35.9 %", "96.1 %"]);
  assert.deepEqual(r.text(card, "sub").map((e) => e.textContent), ["", "1.18 V", "23500", "63000"]);
  const canvas = card.find((e) => e.tag === "canvas")[0];
  for (const t of r.timers.filter((t) => t.kind === "i" && t.ms === 100)) t.fn();   // redraw
  const fills = canvas.ctx.calls.filter((c) => c[0] === "fillRect");
  assert.ok(fills.length >= 2, "background + a low run");
  assert.ok(canvas.ctx.calls.some((c) => c[0] === "lineTo"));
  // a stale reading is dimmed, not hidden
  r.sockets[0].recv(r.msg("align", { ch: 1, n: 16, dt: 20, bits: "f81f", ma: 4.9, rb: 1, thr: null,
                                     drv: 65535, tower: "active", busy: true }));
  assert.match(r.text(card, "val")[0].className, /stale/);
  assert.equal(r.text(card, "val")[2].textContent, "—");
  assert.equal(r.ids["align-tower"].textContent, "strokes in progress: adjusting paused");
});

test("the buttons send the commands; paused while strokes are in progress; old head has no threshold", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  const [c1, c2] = r.cards();
  r.buttons(c1, "−")[0].click();                       // threshold -
  assert.deepEqual(s.sent.pop(), { cmd: "align", ch: 1, thr: -1 });
  r.timers.filter((t) => t.kind === "t" && t.ms < 1000).forEach((t) => t.fn());   // press lock over
  r.buttons(c1, "+")[1].click();                       // drive +
  assert.deepEqual(s.sent.pop(), { cmd: "align", ch: 1, drive: 1 });
  assert.equal(r.buttons(c2, "−")[0].disabled, true);  // old head: no threshold
  assert.equal(r.buttons(c2, "−")[1].disabled, false);
  r.timers.filter((t) => t.kind === "t" && t.ms < 1000).forEach((t) => t.fn());
  s.recv(r.msg("align_ack", { what: "thr", ch: 1, ok: true, thr: 33423, drv: 65535, tower: "active" }));
  assert.equal(r.buttons(c1, "−")[0].disabled, true);  // strokes in progress
  assert.equal(r.buttons(c1, "+")[1].disabled, true);
});

test("acks: a change says live and not saved; a refusal says why, in the gold, never red", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  const c1 = r.cards()[0];
  const msg = () => r.text(c1, "msg")[0];
  s.recv(r.msg("align_ack", { what: "drive", ch: 1, ok: true, thr: null, drv: 63689, tower: "inactive" }));
  assert.match(msg().textContent, /Laser drive now 97\.2 %.*not saved/);
  assert.doesNotMatch(msg().className, /refused/);
  s.recv(r.msg("align_ack", { what: "thr", ch: 1, ok: false, why: "tower not quiet (active): strokes in progress",
                              thr: null, drv: 63689, tower: "active" }));
  assert.match(msg().textContent, /Not changed: tower not quiet/);
  assert.match(msg().className, /refused/);
});

test("keep-alive every 2 s for the watched head; Watch switches head", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  const keep = r.timers.find((t) => t.kind === "i" && t.ms === 2000);
  assert.ok(keep);
  s.sent.length = 0;
  keep.fn();
  assert.deepEqual(s.sent[0], { cmd: "align", ch: 1, scope: true });
  const c2 = r.cards()[1];
  r.buttons(c2, "Watch")[0].click();
  assert.deepEqual(s.sent.pop(), { cmd: "align", ch: 2, scope: true });
  assert.match(c2.className, /watching/);
});

test("heartbeat chan kinds update the cards when a head appears or goes", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  const chan = r.kinds.map((k) => [k, null]);
  chan[2] = ["head_new", null];                        // ch3 plugged in
  s.recv(r.msg("heartbeat", { chan, tower: "inactive" }));
  assert.deepEqual(r.cards().map((c) => c.attrs["data-ch"]), ["1", "2", "3"]);
  chan[0] = ["fault", "why"];
  s.recv(r.msg("heartbeat", { chan, tower: "inactive" }));
  assert.deepEqual(r.cards().map((c) => c.attrs["data-ch"]), ["2", "3"]);
  assert.ok(s.sent.some((m) => m.ch === 2 && m.scope === true));   // watch moved on
});

test("a lost socket retries on the other address; hidden stops the scope and closes", () => {
  const r = rig();
  r.sockets[0].open();
  r.sockets[0].recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  r.sockets[0].close();
  const retry = r.timers.filter((t) => t.kind === "t").pop();
  retry.fn();
  assert.equal(r.sockets[1].url, "ws://tower/ws");     // alt address
  assert.equal(r.ids["align-link"].textContent, "connecting…");
  r.sockets[1].open();
  r.sockets[1].recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  r.document.visibilityState = "hidden";
  r.listeners.visibilitychange();
  assert.ok(r.sockets[1].sent.some((m) => m.scope === false && m.ch === 1));
  assert.equal(r.sockets[1].readyState, 3);
});

test("frames for a head that has no card, junk and foreign schemas are ignored", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  s.recv("not json sand.panel/v1");
  s.recv({ schema: "sand.event/v1", type: "stroke" });
  s.recv(r.msg("align", { ch: 7, n: 1, bits: "80", tower: "inactive" }));
  assert.equal(r.cards().length, 2);
});
