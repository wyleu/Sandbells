// node --test changes/bells/js_tests/  -- align.js (the sandheads page) against a fake DOM and a fake WebSocket
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

function rig(cfg, opts) {
  opts = opts || {};
  const ids = {};
  for (const id of ["align-main", "align-heads", "align-link", "align-tower"]) { ids[id] = new El("x"); ids[id].id = id; }
  const store = Object.assign({}, opts.store || {});
  const location = { hash: opts.hash || "" };
  const winListeners = {};
  const win = {
    addEventListener(ev, fn) { winListeners[ev] = fn; },
    location,
    sessionStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    history: { replaceState(a, b, url) { location.hash = url; } },
  };
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
    window: win, document, WebSocket: WS, console,
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
  return { ids, sockets, timers, document, listeners, Align, kinds, msg, store, location, winListeners,
           cards: () => ids["align-main"].find((e) => e.tag === "section"),
           tabs: () => ids["align-heads"].children,
           sel: () => ids["align-heads"].children.filter((t) => / sel\b/.test(t.className)).map((t) => t.attrs["data-ch"]),
           scopes: (s) => s.sent.filter((m) => m.cmd === "align" && "scope" in m).map((m) => m.ch + ":" + m.scope),
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

const tick = (r) => r.timers.filter((t) => t.kind === "i" && t.ms === 100).forEach((t) => t.fn());
const pressLockOver = (r) => r.timers.filter((t) => t.kind === "t" && t.ms < 1000).forEach((t) => t.fn());

test("connects to the first address, asks for info, a button per channel and ONE panel", () => {
  const r = rig();
  assert.equal(r.sockets[0].url, "ws://home/ws");
  r.sockets[0].open();
  assert.deepEqual(r.sockets[0].sent[0], { cmd: "align", info: true });
  r.sockets[0].recv(r.msg("align_info", { kinds: r.kinds, active: [1, 2], tower: "inactive" }));
  const tabs = r.tabs();
  assert.equal(tabs.length, 8);                        // every channel the survey reports
  assert.deepEqual(tabs.map((t) => /\bact\b/.test(t.className)), [true, true, false, false, false, false, false, false]);
  assert.match(tabs[2].className, /inact/);            // inactive ones are marked, and are still buttons
  assert.equal(tabs[0].tag, "button");
  assert.deepEqual(r.sel(), ["1"]);                    // the first active head is on show
  const cards = r.cards();
  assert.equal(cards.length, 1);                       // one head's panel, not a card each
  assert.equal(cards[0].attrs["data-ch"], "1");
  // only the selected head is watched
  assert.deepEqual(r.scopes(r.sockets[0]), ["1:true"]);
  assert.match(cards[0].className, /watching/);
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
  tick(r);
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
  const c1 = r.cards()[0];
  r.buttons(c1, "−")[0].click();                       // threshold -
  assert.deepEqual(s.sent.pop(), { cmd: "align", ch: 1, thr: -1 });
  pressLockOver(r);
  r.buttons(c1, "+")[1].click();                       // drive +
  assert.deepEqual(s.sent.pop(), { cmd: "align", ch: 1, drive: 1 });
  pressLockOver(r);
  s.recv(r.msg("align_ack", { what: "thr", ch: 1, ok: true, thr: 33423, drv: 65535, tower: "active" }));
  assert.equal(r.buttons(c1, "−")[0].disabled, true);  // strokes in progress
  assert.equal(r.buttons(c1, "+")[1].disabled, true);
  s.recv(r.msg("align_ack", { what: "drive", ch: 1, ok: true, thr: 33423, drv: 65535, tower: "inactive" }));
  r.tabs()[1].click();                                 // head 2: an old head
  const c2 = r.cards()[0];
  assert.equal(c2.attrs["data-ch"], "2");
  assert.equal(r.buttons(c2, "−")[0].disabled, true);  // old head: no threshold
  assert.equal(r.buttons(c2, "−")[1].disabled, false);
  r.buttons(c2, "+")[1].click();
  assert.deepEqual(s.sent.pop(), { cmd: "align", ch: 2, drive: 1 });   // the nudge goes to the head on show
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

test("keep-alive every 2 s asks for the selected head only", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  const keep = r.timers.find((t) => t.kind === "i" && t.ms === 2000);
  assert.ok(keep);
  s.sent.length = 0;
  keep.fn();
  assert.deepEqual(s.sent[0], { cmd: "align", ch: 1, scope: true });
  s.sent.length = 0;
  r.tabs()[1].click();
  s.sent.length = 0;
  keep.fn();
  assert.deepEqual(s.sent.filter((m) => m.scope !== undefined), [{ cmd: "align", ch: 2, scope: true }]);
});

test("selecting a head: stops watching the old one, watches the new one, one panel, one selected button", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  s.sent.length = 0;
  r.tabs()[1].click();                                  // head 2
  assert.deepEqual(r.scopes(s), ["1:false", "2:true"]); // old off first, then the new one on
  assert.deepEqual(r.sel(), ["2"]);
  assert.equal(r.cards().length, 1);
  assert.equal(r.cards()[0].attrs["data-ch"], "2");
  assert.match(r.cards()[0].className, /watching/);
  assert.equal(r.tabs()[1].attrs["aria-selected"], "true");
  assert.equal(r.tabs()[0].attrs["aria-selected"], "false");
  // a late frame of the head we left is ignored; the new head's frame is used
  s.recv(r.msg("align", { ch: 1, n: 16, dt: 20, bits: "f81f", ma: 9.9, rb: 1, thr: 1, drv: 1, tower: "inactive" }));
  s.recv(r.msg("align", { ch: 2, n: 16, dt: 20, bits: "f81f", ma: 3.2, rb: 500, thr: null, drv: 65535, tower: "inactive" }));
  assert.equal(r.text(r.cards()[0], "val")[0].textContent, "3.2 mA");
  // back to head 1: its trace starts afresh, 2 stops
  s.sent.length = 0;
  r.tabs()[0].click();
  assert.deepEqual(r.scopes(s), ["2:false", "1:true"]);
  // clicking the head already on show does not send a thing
  s.sent.length = 0;
  r.tabs()[0].click();
  assert.deepEqual(s.sent, []);
});

test("an inactive head can be selected: marked, nothing is watched, nothing can be nudged", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  s.sent.length = 0;
  r.tabs()[2].click();                                  // head 3: empty
  assert.deepEqual(r.sel(), ["3"]);
  assert.deepEqual(r.scopes(s), ["1:false"]);           // the old scope stops, none starts
  const c3 = r.cards()[0];
  assert.equal(c3.attrs["data-ch"], "3");
  assert.match(c3.className, /inactive/);
  assert.match(c3.className, /off/);
  assert.equal(r.text(c3, "state")[0].textContent, "not active");
  assert.match(r.text(c3, "hint")[0].textContent, /Nothing to watch or adjust/);
  for (const b of [...r.buttons(c3, "−"), ...r.buttons(c3, "+")]) assert.equal(b.disabled, true);
  s.sent.length = 0;
  r.timers.find((t) => t.kind === "i" && t.ms === 2000).fn();
  assert.deepEqual(r.scopes(s), []);                    // the keep-alive has nothing to keep alive
  tick(r);                                              // the trace draws its "not active" note, no crash
  const canvas = c3.find((e) => e.tag === "canvas")[0];
  assert.ok(canvas.ctx.calls.some((c) => c[0] === "fillText" && /not an active head/.test(c[1])));
  r.tabs()[1].click();                                  // on to head 2: watched again
  assert.deepEqual(r.scopes(s), ["2:true"]);
});

test("the selection is in the URL hash and sessionStorage, and a reload comes back to it", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  assert.equal(r.location.hash, "");                    // the default is not written down
  r.tabs()[1].click();
  assert.equal(r.location.hash, "#head=2");
  assert.equal(r.store.sandheadsHead, "2");
  // reload with the hash
  const r2 = rig(null, { hash: r.location.hash });
  r2.sockets[0].open();
  r2.sockets[0].recv(r2.msg("align_info", { kinds: r2.kinds, tower: "inactive" }));
  assert.deepEqual(r2.sel(), ["2"]);
  assert.deepEqual(r2.scopes(r2.sockets[0]), ["2:true"]);   // head 1 is never asked for
  // or with only sessionStorage (coming back from another tab, no hash)
  const r3 = rig(null, { store: r.store });
  r3.sockets[0].open();
  r3.sockets[0].recv(r3.msg("align_info", { kinds: r3.kinds, tower: "inactive" }));
  assert.deepEqual(r3.sel(), ["2"]);
  // the hash wins over the storage; an inactive head survives a reload too
  const r4 = rig(null, { hash: "#head=5", store: r.store });
  r4.sockets[0].open();
  r4.sockets[0].recv(r4.msg("align_info", { kinds: r4.kinds, tower: "inactive" }));
  assert.deepEqual(r4.sel(), ["5"]);
  assert.deepEqual(r4.scopes(r4.sockets[0]), []);        // nothing watched for an inactive head
  assert.equal(r4.cards()[0].attrs["data-ch"], "5");
});

test("a stored head the survey does not have falls back to the first active head", () => {
  const r = rig(null, { hash: "#head=12", store: { sandheadsHead: "9" } });
  r.sockets[0].open();
  r.sockets[0].recv(r.msg("align_info", { kinds: r.kinds.slice(0, 4), tower: "inactive" }));
  assert.deepEqual(r.sel(), ["1"]);
  assert.equal(r.tabs().length, 4);
  const junk = rig(null, { hash: "#head=banana", store: { sandheadsHead: "-3" } });
  junk.sockets[0].open();
  junk.sockets[0].recv(junk.msg("align_info", { kinds: junk.kinds, tower: "inactive" }));
  assert.deepEqual(junk.sel(), ["1"]);
  // no head fitted at all: head 1 is shown, marked, nothing is watched
  const none = rig();
  none.sockets[0].open();
  none.sockets[0].recv(none.msg("align_info", { kinds: ["empty", "empty", "empty", "empty"], tower: "inactive" }));
  assert.deepEqual(none.sel(), ["1"]);
  assert.deepEqual(none.scopes(none.sockets[0]), []);
});

test("changing the hash by hand (hashchange) selects that head", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  s.sent.length = 0;
  r.location.hash = "#head=2";
  r.winListeners.hashchange();
  assert.deepEqual(r.sel(), ["2"]);
  assert.deepEqual(r.scopes(s), ["1:false", "2:true"]);
  r.location.hash = "#head=99";                          // not a head: ignored
  r.winListeners.hashchange();
  assert.deepEqual(r.sel(), ["2"]);
});

test("a reconnect asks again for the selected head only; hidden stops it", () => {
  const r = rig(null, { hash: "#head=2" });
  r.sockets[0].open();
  r.sockets[0].recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  r.sockets[0].close();
  r.timers.filter((t) => t.kind === "t").pop().fn();
  const s = r.sockets[1];
  s.open();
  assert.deepEqual(r.scopes(s), ["2:true"]);
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  assert.deepEqual(r.sel(), ["2"]);
  r.document.visibilityState = "hidden";
  r.listeners.visibilitychange();
  assert.deepEqual(r.scopes(s), ["2:true", "2:false"]);
});

test("heartbeat chan kinds update the buttons when a head appears or goes; the selection stays", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  r.tabs()[2].click();                                  // head 3, empty, on show
  s.sent.length = 0;
  const chan = r.kinds.map((k) => [k, null]);
  chan[2] = ["head_new", null];                         // ch3 plugged in
  s.recv(r.msg("heartbeat", { chan, tower: "inactive" }));
  assert.deepEqual(r.tabs().map((t) => /\bact\b/.test(t.className)),
                   [true, true, true, false, false, false, false, false]);
  assert.deepEqual(r.sel(), ["3"]);
  assert.deepEqual(r.scopes(s), ["3:true"]);            // now it can be watched
  s.sent.length = 0;
  chan[2] = ["fault", "why"];                           // and it breaks
  s.recv(r.msg("heartbeat", { chan, tower: "inactive" }));
  assert.deepEqual(r.sel(), ["3"]);                     // still on show, now marked
  assert.deepEqual(r.scopes(s), ["3:false"]);
  assert.match(r.cards()[0].className, /inactive/);
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

test("frames for a head that is not on show, junk and foreign schemas are ignored", () => {
  const r = rig();
  const s = r.sockets[0];
  s.open();
  s.recv(r.msg("align_info", { kinds: r.kinds, tower: "inactive" }));
  s.recv("not json sand.panel/v1");
  s.recv({ schema: "sand.event/v1", type: "stroke" });
  s.recv(r.msg("align", { ch: 7, n: 1, bits: "80", tower: "inactive" }));
  s.recv(r.msg("align", { ch: 2, n: 1, bits: "80", ma: 8, tower: "inactive" }));
  assert.equal(r.cards().length, 1);
  assert.equal(r.text(r.cards()[0], "val")[0].textContent, "—");
});

test("before the survey answers: no buttons, a waiting line; a stored head waits for the survey", () => {
  const r = rig(null, { hash: "#head=3" });
  assert.equal(r.tabs().length, 0);
  r.sockets[0].open();
  assert.deepEqual(r.scopes(r.sockets[0]), []);          // nothing asked for before we know the head is active
});
